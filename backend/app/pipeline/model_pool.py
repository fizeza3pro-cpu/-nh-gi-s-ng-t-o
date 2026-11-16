"""Điều phối BytePlus và sổ token: giữ chỗ trước mạng, quyết toán trước khi parse JSON."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import threading
import uuid
from weakref import WeakKeyDictionary

from sqlalchemy import inspect, select
from app.config import settings
from app.db import SessionLocal
from app.models.model_pool import ManagedModel, ModelPoolEvent, ModelPoolSettings, ModelQuota, ModelTokenRequest
from app.pipeline.pool_errors import ModelPoolChanged, ModelPoolWait

_local_lock = threading.RLock()
_schema_cache = WeakKeyDictionary()
_scoring_group = ContextVar("byteplus_scoring_group", default=None)
_response_context = ContextVar("byteplus_response_context", default=None)


def now():
    return datetime.now(timezone.utc)


def schema_available(db):
    """Code mới vẫn chạy chế độ cũ nếu migration chưa được áp dụng."""
    bind = db.get_bind()
    if _schema_cache.get(bind):
        return True
    ready = inspect(bind).has_table("model_pool_settings")
    if ready:
        _schema_cache[bind] = True
    return ready


def get_settings(db, *, lock=False):
    if not settings.byteplus_model_pool_available or not schema_available(db):
        return None
    query = select(ModelPoolSettings).where(ModelPoolSettings.id == 1)
    return db.scalar(query.with_for_update() if lock else query)


def event(db, kind, payload, actor_id=None):
    db.add(ModelPoolEvent(event=kind, payload=payload, actor_id=actor_id))


def initialize(db):
    """Nhập model .env đúng một lần; chưa xác nhận số dư thì chưa bật điều phối."""
    config = get_settings(db, lock=True)
    if config is None:
        config = ModelPoolSettings(id=1)
        db.add(config)
        db.flush()
    for slot in range(1, 6):
        if db.get(ManagedModel, slot) is None:
            db.add(ManagedModel(slot=slot, label=f"Model {slot}"))
    db.flush()
    if config.revision == 0:
        quota = ModelQuota(quota_key=settings.byteplus_model)
        db.add(quota)
        db.flush()
        first = db.get(ManagedModel, 1)
        first.model_id = settings.byteplus_model
        first.quota_id = quota.id
        first.label = settings.byteplus_model
        config.revision = 1
        event(db, "INITIALIZED", {"model_id": settings.byteplus_model})
    return config


def remaining(quota):
    return None if quota.confirmed_remaining is None else quota.confirmed_remaining - quota.spent_tokens


def available(quota):
    value = remaining(quota)
    return None if value is None else max(0, value - quota.reserved_tokens)


def expire_reservations(db):
    """Request chết chuyển UNKNOWN; không hoàn token khi chưa rõ provider đã xử lý chưa."""
    rows = db.scalars(select(ModelTokenRequest).where(
        ModelTokenRequest.status.in_(["IN_FLIGHT", "GROUP"]), ModelTokenRequest.lease_until < now(),
    )).all()
    for row in rows:
        row.status = "UNKNOWN"
        row.error_code = "LEASE_EXPIRED"
        row.updated_at = now()


def estimate_tokens(request):
    """Dự phòng theo số byte UTF-8 và output tối đa; không giả là tokenizer chính xác."""
    input_bound = len(json.dumps(request.get("messages", []), ensure_ascii=False).encode("utf-8")) + 512
    return input_bound + int(request.get("max_tokens") or 4096)


@dataclass
class Reservation:
    id: str
    slot: int
    model_id: str
    thinking_mode: str


def reserve(request, stage, call_id, *, excluded=(), group_size=1):
    with _local_lock, SessionLocal() as db:
        config = get_settings(db, lock=True)
        parent = _scoring_group.get()
        if config is None or (not config.enabled and parent is None):
            return None
        expire_reservations(db)
        if config.blocked_reason:
            db.commit()
            raise ModelPoolWait(config.blocked_reason)
        estimate = estimate_tokens(request)
        budget = estimate * group_size
        models = db.scalars(select(ManagedModel).order_by(ManagedModel.slot)).all()
        if parent:
            models = [row for row in models if row.slot == parent.slot]
        elif not config.auto_switch:
            models = ([row for row in models if row.slot == config.active_slot] if config.active_slot
                      else [row for row in models if row.enabled and row.model_id][:1])
        selected = None
        for model in models:
            if model.slot in excluded or not model.enabled or not model.model_id or model.blocked_reason or not model.quota_id:
                continue
            quota = db.get(ModelQuota, model.quota_id)
            if quota.exhausted or estimate > model.context_window:
                continue
            if parent:
                held = db.get(ModelTokenRequest, parent.id)
                if held is None or held.status != "GROUP" or held.reserved_tokens < budget:
                    continue
                held.reserved_tokens -= budget
            elif available(quota) is None or available(quota) - budget < config.threshold:
                continue
            else:
                quota.reserved_tokens += budget
            selected = model
            break
        if selected is None:
            db.commit()
            if parent:
                raise ModelPoolChanged(parent.slot)
            raise ModelPoolWait()
        if config.active_slot != selected.slot:
            old = db.get(ManagedModel, config.active_slot) if config.active_slot else None
            event(db, "MODEL_SWITCH", {"from_slot": config.active_slot, "to_slot": selected.slot,
                "from_model": old.model_id if old else None, "to_model": selected.model_id,
                "reason": "INITIAL_SELECTION" if old is None else "BUDGET_OR_AVAILABILITY"})
            config.active_slot = selected.slot
        row = ModelTokenRequest(id=str(uuid.uuid4()), model_slot=selected.slot, model_id=selected.model_id,
            quota_id=selected.quota_id, call_id=call_id, stage=stage,
            parent_id=parent.id if parent else None,
            response_id=_response_context.get(), reserved_tokens=budget,
            status="GROUP" if group_size > 1 else "IN_FLIGHT",
            lease_until=now() + timedelta(seconds=max(180, (settings.llm_timeout_seconds + 60) * group_size)))
        db.add(row)
        db.commit()
        return Reservation(row.id, selected.slot, selected.model_id, selected.thinking_mode)


def error_code(error):
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        nested = body.get("error") if isinstance(body.get("error"), dict) else body
        return str(nested.get("code") or nested.get("type") or "")[:64]
    return ""


def model_quota_exhausted(error):
    code = error_code(error).casefold()
    message = str(error).casefold()
    return code == "setlimitexceeded" or "setlimitexceeded" in message


def settle(reservation, *, completion=None, error=None, release_group=False):
    with _local_lock, SessionLocal() as db:
        config = get_settings(db, lock=True)
        row = db.get(ModelTokenRequest, reservation.id)
        if row is None or row.status not in {"IN_FLIGHT", "GROUP", "UNKNOWN"}:
            return
        quota = db.get(ModelQuota, row.quota_id)
        usage = getattr(completion, "usage", None)
        raw = usage.model_dump() if hasattr(usage, "model_dump") else usage
        raw = raw if isinstance(raw, dict) else {}
        known = usage is not None and raw.get("total_tokens") is not None
        code = error_code(error) if error else ""
        status = getattr(error, "status_code", None)
        rejected = error is not None and (status in {400, 401, 402, 403, 404, 422, 429} or model_quota_exhausted(error))
        provider_id = getattr(completion, "id", None)
        duplicate = provider_id and db.scalar(select(ModelTokenRequest.id).where(
            ModelTokenRequest.id != row.id, ModelTokenRequest.quota_id == row.quota_id,
            ModelTokenRequest.provider_request_id == provider_id, ModelTokenRequest.status == "SETTLED",
        ).limit(1))
        if known or rejected or release_group:
            held_budget = row.reserved_tokens
            quota.reserved_tokens -= held_budget
            row.reserved_tokens = 0
            charged = max(0, int(raw.get("total_tokens") or 0)) if known and not duplicate else 0
            quota.spent_tokens += charged
            if row.parent_id:
                parent = db.get(ModelTokenRequest, row.parent_id)
                if parent is not None and parent.status == "GROUP":
                    unused = max(0, held_budget - charged)
                    parent.reserved_tokens += unused
                    quota.reserved_tokens += unused
            row.total_tokens = charged
            row.input_tokens = int(raw.get("prompt_tokens") or 0) if known else 0
            row.output_tokens = int(raw.get("completion_tokens") or 0) if known else 0
            row.status = "DUPLICATE" if duplicate else "RELEASED" if release_group else "SETTLED" if known else "REJECTED"
        else:
            row.status = "UNKNOWN"
        row.error_code = code or (type(error).__name__ if error else "")
        row.provider_request_id = provider_id
        row.updated_at = now()
        if error and model_quota_exhausted(error):
            quota.exhausted = True
            event(db, "QUOTA_EXHAUSTED", {"slot": row.model_slot, "model_id": row.model_id})
        elif error and (status in {401, 402, 403} or any(marker in (code + " " + str(error)).casefold()
                for marker in ("insufficient_quota", "insufficient_balance", "insufficient balance", "accountoverdue"))):
            config.blocked_reason = "ACCOUNT_OR_KEY_ERROR"
            event(db, "ACCOUNT_BLOCKED", {"error_code": code, "status": status})
        elif status == 404:
            db.get(ManagedModel, row.model_slot).blocked_reason = "MODEL_NOT_FOUND"
        db.commit()


def complete(client, request, *, provider, stage, call_id):
    """Mỗi request thực đi qua sổ token, kể cả fallback tham số và output JSON lỗi."""
    if provider != "byteplus" or settings.mock_mode or not settings.byteplus_model_pool_available:
        return client.chat.completions.create(**request), {"model": request["model"]}
    excluded = set()
    while len(excluded) < 5:
        reservation = reserve(request, stage, call_id, excluded=excluded)
        if reservation is None:
            return client.chat.completions.create(**request), {"model": request["model"]}
        actual = {**request, "model": reservation.model_id}
        if actual.get("max_tokens") is None:
            actual["max_tokens"] = 4096
        if reservation.thinking_mode == "unsupported":
            actual.pop("extra_body", None)
            actual.pop("reasoning_effort", None)
        elif reservation.thinking_mode in {"enabled", "disabled"}:
            actual["extra_body"] = {"thinking": {"type": reservation.thinking_mode}}
            if reservation.thinking_mode == "disabled":
                actual.pop("reasoning_effort", None)
        elif not reservation.model_id.startswith("deepseek-v4"):
            actual.pop("extra_body", None)
        try:
            completion = client.chat.completions.create(**actual)
        except Exception as exc:
            settle(reservation, error=exc)
            if model_quota_exhausted(exc) or getattr(exc, "status_code", None) == 404:
                if _scoring_group.get():
                    raise ModelPoolChanged(reservation.slot) from exc
                excluded.add(reservation.slot)
                continue
            exc.pool_metadata = {"model": reservation.model_id, "pool_request_id": reservation.id}
            if getattr(exc, "status_code", None) in {401, 402, 403} or any(marker in (error_code(exc) + " " + str(exc)).casefold()
                    for marker in ("insufficient_quota", "insufficient_balance", "insufficient balance", "accountoverdue")):
                raise ModelPoolWait("ACCOUNT_OR_KEY_ERROR") from exc
            raise
        settle(reservation, completion=completion)
        return completion, {"model": reservation.model_id, "pool_request_id": reservation.id,
                            "thinking_type": (actual.get("extra_body") or {}).get("thinking", {}).get("type")}
    raise ModelPoolWait()


@contextmanager
def response_context(response_id):
    token = _response_context.set(response_id)
    try:
        yield
    finally:
        _response_context.reset(token)


@contextmanager
def scoring_group(prompt, output_tokens, runs, *, excluded=()):
    """Giữ một model và ngân sách cho cả nhóm đa số; không trộn model giữa các lượt."""
    request = {"messages": [{"role": "user", "content": prompt}], "max_tokens": output_tokens}
    reservation = None
    if settings.llm_provider == "byteplus" and not settings.mock_mode:
        reservation = reserve(request, "scoring_group", str(uuid.uuid4()), excluded=excluded,
                              group_size=runs * (settings.llm_max_retries + 2) + 1)
    token = _scoring_group.set(reservation)
    try:
        yield reservation
    finally:
        _scoring_group.reset(token)
        if reservation:
            settle(reservation, release_group=True)


def has_capacity():
    """Không nhận job LLM mới khi pool đang chờ quota; không tiêu lượt retry của bài."""
    if settings.mock_mode or settings.llm_provider != "byteplus":
        return True
    with _local_lock, SessionLocal() as db:
        config = get_settings(db, lock=True)
        if config is None or not config.enabled:
            return True
        expire_reservations(db)
        candidates = db.scalars(select(ManagedModel).where(ManagedModel.enabled.is_(True))).all()
        if not config.auto_switch and config.active_slot:
            candidates = [row for row in candidates if row.slot == config.active_slot]
        ready = not config.blocked_reason and any(
            row.model_id and not row.blocked_reason and row.quota_id
            and not (quota := db.get(ModelQuota, row.quota_id)).exhausted
            and available(quota) is not None and available(quota) > config.threshold + 512
            for row in candidates)
        db.commit()
        return bool(ready)

"""Quản trị cấu hình và đối chiếu số dư; mọi thay đổi có revision và nhật ký."""
from fastapi import HTTPException
from sqlalchemy import func, select
from app.config import settings
from app.models.model_pool import ManagedModel, ModelPoolEvent, ModelQuota, ModelTokenRequest
from app.pipeline import model_pool as pool


def _ready(db):
    if not settings.byteplus_model_pool_available or not pool.schema_available(db):
        raise HTTPException(status_code=503, detail="Bộ quản lý model chưa sẵn sàng. Cần áp dụng migration c5b7d9e1f236 trước.")


def _locked(db, expected_revision):
    _ready(db)
    if settings.llm_provider != "byteplus":
        raise HTTPException(status_code=409, detail="Chức năng này chỉ quản lý model BytePlus. Cần LLM_PROVIDER=byteplus.")
    config = pool.initialize(db)
    if config.revision != expected_revision:
        raise HTTPException(status_code=409, detail="Cấu hình vừa thay đổi. Hãy tải lại trước khi lưu.")
    pool.expire_reservations(db)
    return config


def _changed(db, config, kind, payload, actor):
    config.revision += 1
    config.updated_at = pool.now()
    pool.event(db, kind, payload, getattr(actor, "id", None))
    db.commit()
    return get_models(db)


def get_models(db):
    _ready(db)
    with pool._local_lock:
        config = pool.initialize(db)
        pool.expire_reservations(db)
        db.commit()
        models = db.scalars(select(ManagedModel).order_by(ManagedModel.slot)).all()
        views = []
        for model in models:
            quota = db.get(ModelQuota, model.quota_id) if model.quota_id else None
            balance = pool.remaining(quota) if quota else None
            available = pool.available(quota) if quota else None
            status = ("NOT_CONFIGURED" if not model.model_id else "DISABLED" if not model.enabled
                else "BLOCKED" if model.blocked_reason else "NOT_CONFIRMED" if balance is None
                else "EXHAUSTED" if quota.exhausted else "LOW_BALANCE" if available <= config.threshold
                else "ACTIVE" if config.enabled and config.active_slot == model.slot else "READY")
            views.append({"slot": model.slot, "label": model.label, "model_id": model.model_id,
                "quota_key": quota.quota_key if quota else None, "enabled": model.enabled,
                "context_window": model.context_window, "thinking_mode": model.thinking_mode, "status": status,
                "quota_limit": quota.quota_limit if quota else 500000, "remaining_tokens": balance,
                "used_tokens": quota.quota_limit - balance if balance is not None else None,
                "reserved_tokens": quota.reserved_tokens if quota else 0, "available_tokens": available,
                "unknown_requests": int(db.scalar(select(func.count(ModelTokenRequest.id)).where(
                    ModelTokenRequest.quota_id == model.quota_id, ModelTokenRequest.status == "UNKNOWN")) or 0),
                "balance_confirmed_at": quota.confirmed_at if quota else None,
                "last_request_at": db.scalar(select(func.max(ModelTokenRequest.created_at)).where(
                    ModelTokenRequest.model_slot == model.slot, ModelTokenRequest.stage != "scoring_group"))})
        events = [{"id": row.id, "event": row.event, "actor_id": row.actor_id,
                   "created_at": row.created_at, "payload": row.payload}
                  for row in db.scalars(select(ModelPoolEvent).order_by(ModelPoolEvent.created_at.desc(), ModelPoolEvent.id.desc()).limit(50))]
        requests = [{"id": row.id, "slot": row.model_slot, "model_id": row.model_id, "stage": row.stage,
                     "response_id": row.response_id, "status": row.status, "input_tokens": row.input_tokens,
                     "output_tokens": row.output_tokens, "total_tokens": row.total_tokens,
                     "reserved_tokens": row.reserved_tokens, "created_at": row.created_at, "error_code": row.error_code}
                    for row in db.scalars(select(ModelTokenRequest).where(ModelTokenRequest.stage != "scoring_group")
                    .order_by(ModelTokenRequest.created_at.desc(), ModelTokenRequest.id.desc()).limit(50))]
        return {"enabled": config.enabled, "auto_switch": config.auto_switch, "threshold": config.threshold,
                "revision": config.revision, "active_slot": config.active_slot, "blocked_reason": config.blocked_reason,
                "provider": settings.llm_provider, "api_key_configured": bool(settings.byteplus_api_key),
                "models": views, "events": events, "requests": requests}


def update_settings(db, payload, actor):
    with pool._local_lock:
        config = _locked(db, payload.expected_revision)
        if config.enabled and not payload.enabled and db.scalar(select(ModelTokenRequest.id).where(
                ModelTokenRequest.status.in_(["IN_FLIGHT", "GROUP"])).limit(1)):
            raise HTTPException(status_code=409, detail="Còn request đang chạy; hãy chờ hoàn tất trước khi tắt quản lý.")
        if payload.enabled:
            if not settings.byteplus_api_key:
                raise HTTPException(status_code=422, detail="BYTEPLUS_API_KEY chưa được cấu hình ở backend.")
            candidates = db.scalars(select(ManagedModel).where(ManagedModel.enabled.is_(True))).all()
            if not any(row.model_id and row.quota_id and not row.blocked_reason
                       and (quota := db.get(ModelQuota, row.quota_id)).confirmed_remaining is not None
                       and not quota.exhausted and pool.available(quota) > payload.threshold for row in candidates):
                raise HTTPException(status_code=422, detail="Cần ít nhất một model đã bật, xác nhận số dư và còn trên ngưỡng.")
        config.enabled = payload.enabled
        config.auto_switch = payload.auto_switch
        config.threshold = payload.threshold
        config.blocked_reason = ""
        return _changed(db, config, "SETTINGS_UPDATED", payload.model_dump(exclude={"expected_revision"}), actor)


def update_model(db, slot, payload, actor):
    with pool._local_lock:
        config = _locked(db, payload.expected_revision)
        model = db.get(ManagedModel, slot)
        if model is None:
            raise HTTPException(status_code=404, detail="Chỉ có 5 vị trí model (1–5).")
        if db.scalar(select(ModelTokenRequest.id).where(ModelTokenRequest.model_slot == slot,
                ModelTokenRequest.status.in_(["IN_FLIGHT", "GROUP"])).limit(1)):
            raise HTTPException(status_code=409, detail="Model đang xử lý request. Hãy chờ hoàn tất trước khi sửa.")
        if db.scalar(select(ManagedModel.slot).where(ManagedModel.slot != slot, ManagedModel.model_id == payload.model_id)):
            raise HTTPException(status_code=409, detail="Model ID đã có ở vị trí khác.")
        quota = db.scalar(select(ModelQuota).where(ModelQuota.quota_key == payload.quota_key))
        if quota is None:
            quota = ModelQuota(quota_key=payload.quota_key)
            db.add(quota)
            db.flush()
        if payload.enabled and quota.confirmed_remaining is None:
            raise HTTPException(status_code=422, detail="Lưu model ở trạng thái tắt, xác nhận số dư rồi mới bật model.")
        for field in ("label", "model_id", "enabled", "context_window", "thinking_mode"):
            setattr(model, field, getattr(payload, field))
        model.quota_id = quota.id
        model.blocked_reason = ""
        if not model.enabled and config.active_slot == slot:
            config.active_slot = None
        return _changed(db, config, "MODEL_UPDATED", {"slot": slot, **payload.model_dump(exclude={"expected_revision"})}, actor)


def update_balance(db, slot, payload, actor):
    with pool._local_lock:
        config = _locked(db, payload.expected_revision)
        model = db.get(ManagedModel, slot)
        if model is None or not model.quota_id:
            raise HTTPException(status_code=404, detail="Cần khai báo model trước khi xác nhận số dư.")
        if db.scalar(select(ModelTokenRequest.id).where(ModelTokenRequest.quota_id == model.quota_id,
                ModelTokenRequest.status.in_(["IN_FLIGHT", "GROUP"])).limit(1)):
            raise HTTPException(status_code=409, detail="Nhóm quota đang có request chạy; chưa thể đối chiếu số dư.")
        quota = db.get(ModelQuota, model.quota_id)
        before = pool.remaining(quota)
        unknown = db.scalars(select(ModelTokenRequest).where(ModelTokenRequest.quota_id == quota.id,
            ModelTokenRequest.status == "UNKNOWN")).all()
        for row in unknown:
            row.status = "RECONCILED"
            row.reserved_tokens = 0
            row.updated_at = pool.now()
        quota.quota_limit = payload.quota_limit
        quota.confirmed_remaining = payload.remaining_tokens
        quota.spent_tokens = 0
        quota.reserved_tokens = 0
        quota.confirmed_at = pool.now()
        quota.exhausted = payload.remaining_tokens == 0
        return _changed(db, config, "BALANCE_CONFIRMED", {"slot": slot, "quota_key": quota.quota_key,
            "before": before, "remaining_tokens": payload.remaining_tokens, "note": payload.note,
            "reconciled_requests": len(unknown)}, actor)

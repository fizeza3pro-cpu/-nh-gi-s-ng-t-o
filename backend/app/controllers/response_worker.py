"""Worker đọc bài đã commit; mọi lời gọi LLM nằm ngoài khóa mã theo đồ vật."""

from __future__ import annotations

import logging
import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.models import Item, ItemCode, ItemCalibrationStatus, Response, ResponseIdea, ResponseScoringStatus, PipelineAudit
from app.pipeline.centroid import rebuild_confirmed_members
from app.pipeline.codebook_service import (
    calibration_source_filter,
    item_is_ready_for_scoring,
    list_curator_codes,
    originality_for_response,
    persist_mapping,
    synchronize_response_mappings,
    refresh_item_scoring_state,
    current_mapping,
)
from app.pipeline.dynamic_mapping import run_code_mapping, run_idea_extraction
from app.pipeline.scoring import run_scoring
from app.schemas.schemas import Item as ItemSchema
from app.schemas.schemas import CuratorResult, ScoringResult, IdeaExtractionResult

from app.pipeline import mock as mock_pipeline
from app.pipeline.clients import chat_client, embedding_client as make_embedding_client


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _release_claim(row: Response) -> None:
    """Kết thúc một bước thành công; không nhầm DONE với đã có điểm FINAL."""
    row.processing_state = "DONE"
    row.processing_claim_token = None
    row.processing_lease_until = None
    row.processing_attempts = 0
    row.processing_error = ""


def _claim(kind: str) -> tuple[str, str] | None:
    """Nhận một công việc bằng khóa hàng ngắn; token ngăn worker cũ ghi đè."""
    with SessionLocal() as db:
        now = _now()
        available = or_(Response.processing_lease_until.is_(None), Response.processing_lease_until <= now)
        if kind == "mapping":
            query = select(Response).where(
                Response.processing_state.in_(["QUEUED", "RUNNING"]),
                Response.scoring_status != ResponseScoringStatus.PENDING_REVIEW,
                available,
                Response.processing_attempts < settings.processing_max_attempts,
            )
        elif kind == "resolution":
            query = select(Response).where(
                Response.processing_state.in_(["DONE", "RUNNING"]),
                Response.scoring_status == ResponseScoringStatus.PENDING_REVIEW,
                available,
                Response.resolution_attempts < settings.resolver_max_attempts,
                or_(Response.resolution_next_at.is_(None), Response.resolution_next_at <= now),
                Response.processing_attempts < settings.processing_max_attempts,
            )
        else:
            query = (
                select(Response)
                .join(Item, Item.id == Response.item_id)
                .where(
                    Response.processing_state.in_(["DONE", "SCORING"]),
                    Response.scoring_status == ResponseScoringStatus.COLLECTING,
                    calibration_source_filter(),
                    Item.calibration_status == ItemCalibrationStatus.ACTIVE,
                    available,
                    Response.processing_attempts < settings.processing_max_attempts,
                )
            )
        row = db.scalar(query.order_by(Response.created_at, Response.id).limit(1).with_for_update(of=Response, skip_locked=True))
        if row is None:
            return None
        token = str(uuid.uuid4())
        row.processing_state = "RUNNING" if kind in {"mapping", "resolution"} else "SCORING"
        row.processing_claim_token = token
        row.processing_attempts += 1
        row.processing_lease_until = now + timedelta(seconds=settings.processing_lease_seconds)
        db.add(PipelineAudit(item_id=row.item_id, response_id=row.id, event="JOB_STARTED", payload={
            "attempt_id": token, "stage": kind, "technical_attempt": row.processing_attempts,
            "resolution_attempt": row.resolution_attempts,
        }))
        db.commit()
        return row.id, token


def _heartbeat(response_id: str, token: str, stop: threading.Event) -> None:
    """Duy trì lease khi provider chậm; worker chết thì lease tự hết hạn."""
    interval = min(60, max(10, settings.processing_lease_seconds // 3))
    while not stop.wait(interval):
        try:
            with SessionLocal() as db:
                row = db.scalar(select(Response).where(Response.id == response_id).with_for_update())
                if row is None or row.processing_claim_token != token:
                    return
                row.processing_lease_until = _now() + timedelta(seconds=settings.processing_lease_seconds)
                db.commit()
        except Exception:  # noqa: BLE001 - lease sẽ tự hết hạn và công việc được nhận lại
            logger.exception("Không thể gia hạn lease của response %s", response_id)


def _guard_stale_creations(curator: CuratorResult, new_code_ids: set[str]) -> CuratorResult:
    """Không chấp nhận CREATE_NEW nếu mã vừa xuất hiện chưa được đối chiếu rõ."""
    if not new_code_ids:
        return curator
    guarded = []
    for decision in curator.decisions:
        if decision.decision != "CREATE_NEW":
            guarded.append(decision)
            continue
        if new_code_ids.issubset(set(decision.compared_code_ids)):
            guarded.append(decision)
            continue
        evaluations = {
            row.get("code_id"): row
            for row in decision.existing_code_evaluations
            if isinstance(row, dict)
        }
        distinct = all(
            code_id in evaluations
            and evaluations[code_id].get("relation") == "DIFFERENT"
            and evaluations[code_id].get("verdict") == "NO_MATCH"
            and not all(
                evaluations[code_id].get(flag) is True
                for flag in ("goal_match", "role_match", "mechanism_match")
            )
            for code_id in new_code_ids
        )
        if distinct:
            guarded.append(decision)
        else:
            guarded.append(decision.model_copy(update={
                "decision": "UNCERTAIN",
                "code_relation": "UNCERTAIN",
                "reason": "Mã mới xuất hiện trong lúc xử lý chưa được phân biệt chắc chắn.",
            }))
    return CuratorResult(decisions=guarded)


def _run_mapping(response_id: str, token: str, *, resolving: bool = False) -> None:
    """Chỉ giữ khóa item lúc kiểm tra epoch và ghi quyết định cuối."""
    with SessionLocal() as db: #mở một phiên làm việc (Session) với cơ sở dữ liệu và tự động đóng kết nối đó lại sau khi các câu lệnh bên trong chạy xong.
        row = db.get(Response, response_id)
        if row is None or row.processing_claim_token != token or row.scoring_status == ResponseScoringStatus.FINAL:
            return
        item_row = db.get(Item, row.item_id) #lấy item từ item_id của res (join)
        item = ItemSchema(id=item_row.id, name=item_row.name, description=item_row.description) #khởi tạo object Item
        raw = row.raw_input #chính là các ý đc nối với nhau
        input_lines = row.input_lines or raw.splitlines()
        checkpoint = row.mapping_checkpoint or {} #ở đây nó là dạng có nhiều phần tử bên trong
        pending_indices = set(db.scalars(select(ResponseIdea.line_index).where(
            ResponseIdea.response_id == row.id, ResponseIdea.mapping_status == "VALID",
            ResponseIdea.code_id.is_(None),
        )).all()) if resolving else None
        epoch = item_row.codebook_epoch or 0
        codes = list_curator_codes(db, item.id)
    original_code_ids = {code["id"] for code in codes}
    new_code_ids: set[str] = set()

    client = None if settings.mock_mode else chat_client() #khởi tạo đối tượng OpenAI (gọi api đến llm)
    embedding_client = None if settings.mock_mode else make_embedding_client() #khởi tạo đối tượng OpenAI (gọi api đến llm embeding)
    if settings.mock_mode:
        extraction, curator = mock_pipeline.run_mapping(item, raw, codes)
        extraction_meta = {"mock": True}
        curator_meta = {"mock": True}
    else:
        input_digest = hashlib.sha256(json.dumps(input_lines, ensure_ascii=False).encode()).hexdigest() # tạo sig
        if (checkpoint.get("extraction") and checkpoint.get("input_digest") == input_digest #đã extraction và sig phải giống nhau
                and not checkpoint.get("needs_extraction_repair")
                and not any(idea.get("status") == "DUPLICATE" for idea in checkpoint["extraction"].get("ideas", []))):
            extraction = IdeaExtractionResult.model_validate(checkpoint["extraction"])
            extraction_meta = checkpoint.get("extraction_meta", {})
        else:
            saved_verification = checkpoint.get("pre_verification") if checkpoint.get("input_digest") == input_digest else None
            extraction, extraction_meta = run_idea_extraction(item, input_lines, client, embedding_client,
                **({"checkpoint": saved_verification} if saved_verification else {}))
            with SessionLocal() as db:
                saved = db.scalar(select(Response).where(Response.id == response_id).with_for_update())
                if saved.processing_claim_token != token:
                    return
                saved.mapping_checkpoint = {
                    **(saved.mapping_checkpoint or {}), "input_digest": input_digest,
                    "extraction": extraction.model_dump(), "extraction_meta": extraction_meta,
                    "needs_extraction_repair": any(idea.review_required for idea in extraction.ideas),
                }
                db.commit()
        curator, curator_meta = run_code_mapping(
            item, extraction, codes, client, embedding_client, idea_indices=pending_indices,
        )

    for recheck in range(settings.codebook_recheck_limit):
        from app.pipeline.scope_audit import verify_expansions, guard_members
        curator, scope_meta, scope_guards = verify_expansions(SessionLocal, item, extraction, curator, codes, client)
        if scope_meta:
            curator_meta = {**curator_meta, "scope_audits": scope_meta}
        with SessionLocal() as db:
            item_row = db.scalar(select(Item).where(Item.id == item.id).with_for_update())
            row = db.scalar(select(Response).where(Response.id == response_id).with_for_update())
            if item_row is None or row is None or row.processing_claim_token != token:
                return
            if (item_row.codebook_epoch or 0) == epoch:
                curator = _guard_stale_creations(curator, new_code_ids) #ngăn tạo code mới nếu có code mới xuất hiện mà quyết định chưa phân biệt rõ.
                curator = guard_members(db, curator, scope_guards) #áp các điều kiện bảo vệ cho quyết định liên quan đến phạm vi code.
                mapping, has_uncertain = persist_mapping(
                    db,
                    item=item_row,
                    response=row,
                    extraction=extraction,
                    curator=curator,
                    code_snapshots=codes,
                    replace_indices=pending_indices,
                )
                row.mapping = mapping.model_dump()
                attempt_metadata = {
                    "attempt_id": token,
                    "idea_extraction": extraction_meta,
                    "code_curator": curator_meta,
                    "codebook_epoch_read": epoch,
                    "codebook_epoch_committed": item_row.codebook_epoch,
                    "stale_rechecks": recheck,
                }
                audit = PipelineAudit(item_id=item.id, response_id=row.id, event="PIPELINE_ATTEMPT", payload=attempt_metadata)
                db.add(audit)
                db.flush()
                row.mapping_meta = {
                    "latest_audit_id": audit.id, "attempt_id": token,
                    "codebook_epoch_read": epoch, "codebook_epoch_committed": item_row.codebook_epoch,
                    "stale_rechecks": recheck,
                }
                row.scoring_status = (
                    ResponseScoringStatus.PENDING_REVIEW
                    if has_uncertain else ResponseScoringStatus.COLLECTING
                )
                _release_claim(row)
                row.mapping_completed_at = None if has_uncertain else _now()
                row.resolution_epoch = item_row.codebook_epoch
                row.mapping_checkpoint = {**(row.mapping_checkpoint or {}),
                    "compared_code_ids": [code["id"] for code in codes]}
                if resolving:
                    row.resolution_attempts += 1
                row.resolution_next_at = _now() + timedelta(seconds=settings.resolver_retry_seconds)
                if has_uncertain and row.resolution_attempts >= settings.resolver_max_attempts:
                    for pending in db.scalars(select(ResponseIdea).where(
                        ResponseIdea.response_id == row.id, ResponseIdea.code_id.is_(None),
                        ResponseIdea.mapping_status == "VALID",
                    )).all():
                        pending.coding_state = "UNRESOLVED"
                    db.flush()
                    synchronize_response_mappings(db, item.id, row.id)
                db.flush()
                refresh_item_scoring_state(db, item_row)
                db.commit()
                return
            epoch = item_row.codebook_epoch or 0
            codes = list_curator_codes(db, item.id)
            new_code_ids.update(code["id"] for code in codes if code["id"] not in original_code_ids)

        # Kết luận "ngoài codebook" ở epoch cũ không còn giá trị.
        if settings.mock_mode:
            extraction, curator = mock_pipeline.run_mapping(item, raw, codes)
            curator_meta = {"mock": True, "rechecked_epoch": epoch}
        else:
            curator, curator_meta = run_code_mapping(
                item, extraction, codes, client, embedding_client, idea_indices=pending_indices,
            )
    raise RuntimeError("Codebook đổi liên tục; sẽ thử lại từ bản mới.")


def _recount_one_item() -> bool:
    """Gộp các thay đổi tần suất thành một lần tính, không gọi LLM trong khóa."""
    with SessionLocal() as db:
        item = db.scalar(select(Item).where(Item.calibration_dirty.is_(True)).order_by(Item.id).limit(1).with_for_update(skip_locked=True))
        if item is None:
            return False
        refresh_item_scoring_state(db, item)
        item.calibration_dirty = False
        db.commit()
        return True


def _refresh_one_centroid() -> bool:
    """Gom cập nhật vector ở nền, không quét mọi member trong transaction lưu bài."""
    with SessionLocal() as db:
        code = db.scalar(select(ItemCode).where(ItemCode.centroid_dirty.is_(True))
                         .order_by(ItemCode.id).limit(1).with_for_update(skip_locked=True))
        if code is None:
            return False
        members = db.execute(select(ResponseIdea.embedding, ResponseIdea.embedding_model)
            .join(Response, Response.id == ResponseIdea.response_id)
            .where(ResponseIdea.code_id == code.id, ResponseIdea.mapping_status == "VALID",
                   Response.scoring_status != ResponseScoringStatus.EXCLUDED)).all()
        rebuild_confirmed_members(code, [(vector or [], model or "") for vector, model in members],
                                  drift_cosine_floor=settings.centroid_drift_cosine_floor)
        code.centroid_dirty = False
        db.commit()
        return True


def _wake_one_unresolved() -> bool:
    """Thử thêm tối đa một lần khi có mã mới liên quan; không quét lại toàn bộ mapping."""
    from app.pipeline.code_retrieval import signature_similarity
    with SessionLocal() as db:
        rows = db.scalars(select(Response).join(Item, Item.id == Response.item_id).where(
            Response.scoring_status == ResponseScoringStatus.PENDING_REVIEW,
            Response.processing_state == "DONE",
            Response.resolution_attempts >= settings.resolver_max_attempts,
            Response.resolution_epoch < Item.codebook_epoch,
        ).order_by(Response.created_at).limit(50).with_for_update(of=Response, skip_locked=True)).all()
        for row in rows:
            checkpoint = row.mapping_checkpoint or {}
            if checkpoint.get("context_wakeup_used"):
                continue
            compared = set(checkpoint.get("compared_code_ids", []))
            new_codes = [code for code in list_curator_codes(db, row.item_id) if code["id"] not in compared]
            pending = db.scalars(select(ResponseIdea).where(ResponseIdea.response_id == row.id,
                ResponseIdea.mapping_status == "VALID", ResponseIdea.code_id.is_(None))).all()
            related = any(signature_similarity(idea.functional_signature, code["functional_signature"])["weighted"] >= 0.25
                          for idea in pending for code in new_codes)
            row.resolution_epoch = row.item.codebook_epoch
            if not related:
                continue
            row.mapping_checkpoint = {**checkpoint, "context_wakeup_used": True}
            row.resolution_attempts = settings.resolver_max_attempts - 1
            row.resolution_next_at = _now()
            for idea in pending:
                idea.coding_state = "RESOLVING"
            db.add(PipelineAudit(item_id=row.item_id, response_id=row.id, event="CONTEXT_WAKEUP",
                                 payload={"new_code_ids": [code["id"] for code in new_codes]}))
            db.commit()
            return True
        db.commit()
        return False


def _run_scoring(response_id: str, token: str) -> None:
    """Gọi LLM ngoài transaction; khi lưu dùng tần suất mới nhất."""
    with SessionLocal() as db:
        row = db.get(Response, response_id)
        if row is None or row.processing_claim_token != token or row.scoring_status == ResponseScoringStatus.FINAL:
            return
        if not item_is_ready_for_scoring(db, row.item):
            _release_claim(row)
            refresh_item_scoring_state(db, row.item)
            db.commit()
            return
        fluency, flexibility, codes, initial_ideas, _ = originality_for_response(db, row)
        item = ItemSchema(id=row.item.id, name=row.item.name, description=row.item.description)

    if settings.mock_mode:
        scoring, scoring_meta = mock_pipeline.run_scoring(fluency, flexibility, codes, initial_ideas)
    else:
        scoring, scoring_meta = run_scoring(
            item, fluency, flexibility, codes, initial_ideas, chat_client()
        )

    with SessionLocal() as db:
        row = db.scalar(select(Response).where(Response.id == response_id).with_for_update())
        if row is None or row.processing_claim_token != token or row.scoring_status == ResponseScoringStatus.FINAL:
            return
        if not item_is_ready_for_scoring(db, row.item):
            _release_claim(row)
            refresh_item_scoring_state(db, row.item)
            db.commit()
            return
        fluency, flexibility, codes, current_ideas, basis = originality_for_response(db, row)
        old_scores = {(idea.idea_id or (idea.original, idea.normalized)): idea for idea in scoring.per_idea_scores}
        current_keys = {(idea.idea_id or (idea.original, idea.normalized)) for idea in current_ideas}
        if current_keys != set(old_scores):
            # Mapping đổi trong lúc LLM chấm: lượt kế tiếp sẽ chấm lại từ đầu.
            _release_claim(row)
            db.commit()
            return
        merged_ideas = [
            idea.model_copy(update={
                "elaboration": old_scores[idea.idea_id or (idea.original, idea.normalized)].elaboration,
                "meaningful_word_count": old_scores[idea.idea_id or (idea.original, idea.normalized)].meaningful_word_count,
                "elaboration_details": old_scores[idea.idea_id or (idea.original, idea.normalized)].elaboration_details,
                "note": old_scores[idea.idea_id or (idea.original, idea.normalized)].note,
            })
            for idea in current_ideas
        ]
        final = ScoringResult(
            fluency=fluency,
            flexibility=flexibility,
            flexibility_codes=codes,
            originality=sum(idea.originality for idea in merged_ideas),
            elaboration=sum(idea.elaboration for idea in merged_ideas),
            per_idea_scores=merged_ideas,
            summary_vi=scoring.summary_vi,
        )
        scored_at = _now()
        row.scoring = final.model_dump()
        row.scoring_meta = {
            **scoring_meta,
            "calculated_at": scored_at.isoformat(),
            "frequency_basis": basis,
            "score_policy": "FINAL_FROZEN_V1",
            "mapping_snapshot": current_mapping(row),
            "codebook_epoch": row.item.codebook_epoch,
            "history": list((row.scoring_meta or {}).get("history", [])),
        }
        row.fluency = final.fluency
        row.flexibility = final.flexibility
        row.originality = final.originality
        row.elaboration = final.elaboration
        row.scoring_status = ResponseScoringStatus.FINAL
        row.scored_at = scored_at
        row.mapping_checkpoint = {}
        db.add(PipelineAudit(item_id=row.item_id, response_id=row.id, event="SCORING_COMMIT", payload={
            "attempt_id": token, "score_policy": "FINAL_FROZEN_V1", "scored_at": scored_at.isoformat(),
        }))
        _release_claim(row)
        db.commit()


def _record_failure(response_id: str, token: str, kind: str, error: Exception) -> None:
    """Không lưu nội dung exception vì provider có thể lặp lại câu trả lời cá nhân."""
    logger.exception("Xử lý %s thất bại cho response %s", kind, response_id)
    with SessionLocal() as db:
        row = db.scalar(select(Response).where(Response.id == response_id).with_for_update())
        if row is None or row.processing_claim_token != token:
            return
        metadata = getattr(error, "metadata", {}) or {}
        extraction_checkpoint = getattr(error, "extraction_checkpoint", None)
        if extraction_checkpoint:
            input_lines = row.input_lines or row.raw_input.splitlines()
            row.mapping_checkpoint = {**(row.mapping_checkpoint or {}),
                "input_digest": hashlib.sha256(json.dumps(input_lines, ensure_ascii=False).encode()).hexdigest(),
                "pre_verification": extraction_checkpoint}
        exhausted = row.processing_attempts >= settings.processing_max_attempts or metadata.get("retryable") is False
        row.processing_state = "FAILED" if exhausted else ("QUEUED" if kind == "mapping" else "DONE")
        row.processing_error = type(error).__name__
        failure_meta = getattr(error, "metadata", None)
        if not isinstance(failure_meta, dict):
            failure_meta = {}
        failure_meta = {"stage": kind, "error_type": type(error).__name__, **(failure_meta or {})}
        if failure_meta:
            audit = PipelineAudit(item_id=row.item_id, response_id=row.id, event="PIPELINE_FAILURE",
                                  payload={"kind": kind, "attempt_id": token, **failure_meta})
            db.add(audit)
            db.flush()
            target = dict(row.mapping_meta or {}) if kind in {"mapping", "resolution"} else dict(row.scoring_meta or {})
            failures = list(target.get("llm_failures", []))
            failures.append({"audit_id": audit.id, "attempt_id": token,
                             **{key: failure_meta.get(key) for key in ("stage", "error_type", "error_category", "retryable")}})
            target["llm_failures"] = failures[-5:]
            if kind in {"mapping", "resolution"}:
                row.mapping_meta = target
            else:
                row.scoring_meta = target
        row.processing_claim_token = None
        row.processing_lease_until = (
            None if exhausted else _now() + timedelta(seconds=min(60 * row.processing_attempts, 300))
        )
        db.commit()


def _expire_exhausted() -> bool:
    """Job chết sau lần thử cuối không được kẹt mãi ở RUNNING/SCORING."""
    with SessionLocal() as db:
        row = db.scalar(
            select(Response).where(
                Response.processing_state.in_(["RUNNING", "SCORING"]),
                Response.processing_lease_until <= _now(),
                Response.processing_attempts >= settings.processing_max_attempts,
            ).order_by(Response.created_at).limit(1).with_for_update(of=Response, skip_locked=True)
        )
        if row is None:
            return False
        row.processing_state = "FAILED"
        row.processing_claim_token = None
        row.processing_lease_until = None
        row.processing_error = "WorkerLeaseExpired"
        db.commit()
        return True


def run_one_job(*, prefer_scoring: bool = False) -> bool:
    """Một bước của worker; trả False khi không có việc."""
    # Luân phiên ưu tiên để dòng bài mới không làm các bài đã mapping chờ điểm mãi.
    if prefer_scoring:
        _recount_one_item()
        _refresh_one_centroid()
    kinds = ("resolution", "scoring", "mapping") if prefer_scoring else ("mapping", "scoring", "resolution")
    claimed = None
    for kind in kinds:
        claimed = _claim(kind)
        if claimed is not None:
            break
    if claimed is None:
        from app.controllers.code_audit_worker import run_one_audit
        return _recount_one_item() or _expire_exhausted() or _wake_one_unresolved() or _refresh_one_centroid() or run_one_audit()
    response_id, token = claimed
    heartbeat_stop = threading.Event()
    heartbeat = None
    heartbeat = threading.Thread(
        target=_heartbeat, args=(response_id, token, heartbeat_stop), daemon=True
    )
    heartbeat.start()
    try:
        if kind in {"mapping", "resolution"}:
            _run_mapping(response_id, token, resolving=kind == "resolution")
        else:
            _run_scoring(response_id, token)
    except Exception as error:  # noqa: BLE001 - retry có giới hạn và audit trạng thái
        _record_failure(response_id, token, kind, error)
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=1)
    return True


def start_workers(stop: threading.Event) -> list[threading.Thread]:
    """Khởi động worker polling; job vẫn nằm trong DB khi tiến trình restart."""
    def loop(index: int) -> None:
        prefer_scoring = bool(index % 2)  #worker chẵn mapping, lẻ chấm điểm
        while not stop.is_set():
            try:
                worked = run_one_job(prefer_scoring=prefer_scoring)
                prefer_scoring = not prefer_scoring
                if worked:
                    continue
            except Exception:  # noqa: BLE001 - một lỗi DB không được giết worker
                logger.exception("Worker không thể nhận công việc")
            stop.wait(settings.processing_poll_seconds)

    workers = [
        threading.Thread(target=loop, args=(index,), name=f"aut-response-worker-{index}", daemon=True)
        for index in range(settings.processing_worker_count)
    ]
    for worker in workers:
        worker.start()
    return workers

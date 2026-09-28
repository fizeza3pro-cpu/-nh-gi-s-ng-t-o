"""Audit mã mới xuyên lượt: chỉ gộp khi ý thật và ranh giới đều đã được kiểm chứng."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models.models import Item, ItemCode, Response, ResponseIdea, PipelineAudit
from app.pipeline.codebook_service import list_curator_codes, _expand_existing_code, synchronize_response_mappings
from app.pipeline.code_retrieval import cosine, signature_similarity
from app.pipeline.centroid import rebuild_confirmed_members
from app.pipeline.scope_audit import verify_expansions, guard_members
from app.pipeline.semantic_verifier import verify_pair
from app.schemas.schemas import Item as ItemSchema, CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult


def _claim():
    """Khóa item ngắn để chỉ một worker nhận cùng cặp; lease giới hạn lần phục hồi."""
    with SessionLocal() as db:
        for item in db.scalars(select(Item).order_by(Item.id).with_for_update(skip_locked=True)).all():
            codes = sorted(list_curator_codes(db, item.id), key=lambda code: code["id"])
            audits = db.scalars(select(PipelineAudit).where(
                PipelineAudit.item_id == item.id, PipelineAudit.event == "AUTO_CODE_AUDIT"
            )).all()
            for index, source in enumerate(codes):
                if not source.get("positive_examples"):
                    continue
                source_prefix = f'{source["id"]}:{source["scope_revision"]}:'
                if len([audit for audit in audits if audit.payload.get("key", "").startswith(source_prefix)]) >= 3:
                    continue
                for target in codes[:index]:
                    similarity = signature_similarity(source["functional_signature"], target["functional_signature"])["weighted"]
                    semantic = cosine(source["embedding"], target["embedding"]) if source["embedding_model"] == target["embedding_model"] else 0
                    if similarity < 0.45 and semantic < 0.85:
                        continue
                    key = f'{source["id"]}:{source["scope_revision"]}:{target["id"]}:{target["scope_revision"]}'
                    history = [audit for audit in audits if audit.payload.get("key") == key]
                    now = datetime.now(timezone.utc)
                    if any(audit.payload.get("status") == "DONE" for audit in history) or len(history) >= 2:
                        continue
                    if any(audit.payload.get("status") == "RUNNING" and datetime.fromisoformat(audit.payload["lease_until"]) > now for audit in history):
                        continue
                    event = PipelineAudit(item_id=item.id, event="AUTO_CODE_AUDIT", payload={
                        "key": key, "source_id": source["id"], "target_id": target["id"],
                        "status": "RUNNING", "lease_until": (now + timedelta(seconds=settings.processing_lease_seconds)).isoformat(),
                    })
                    db.add(event)
                    db.flush()
                    result = (event.id, ItemSchema(id=item.id, name=item.name, description=item.description),
                              item.codebook_epoch, source, target, codes)
                    db.commit()
                    return result
        return None


def run_one_audit():
    """Tối đa một cặp mỗi bước; gọi LLM ngoài khóa và chỉ đổi mã sau audit toàn member."""
    if settings.mock_mode or not settings.auto_code_audit_enabled:
        return False
    job = _claim()
    if job is None:
        return False
    audit_id, item, epoch, source, target, codes = job
    metadata, reason = {}, "Không đủ bằng chứng để gộp."
    accepted = None
    guards = {}
    try:
        from app.controllers.response_controller import _client
        client = _client()
        original = source["positive_examples"][0]
        verdict, metadata = verify_pair(item, original, target, client)
        if verdict.relation in {"SAME_CATEGORY", "IDEA_NARROWER_THAN_CODE"} and verdict.goal_match and verdict.role_match and not verdict.exclusion_hit:
            decision = CuratorDecision(idea_index=0, decision="EXPAND_EXISTING", existing_code_id=target["id"],
                code_relation="IDEA_BROADER_THAN_CODE", code_name=target["name"], code_description=target["description"],
                functional_signature=target["functional_signature"], inclusion_rules=target["inclusion_rules"],
                exclusion_rules=target["exclusion_rules"], positive_examples=[original], absorbed_code_ids=[source["id"]],
                confidence=0.9, reviewed_by_challenger=True,
                existing_code_evaluations=[{"code_id": code_id, "relation": "IDEA_BROADER_THAN_CODE"} for code_id in [source["id"], target["id"]]],
                reason="Audit tự động xác nhận các member cùng phạm vi mã đích; giữ canonical ID và redirect mã nguồn.")
            extraction = IdeaExtractionResult(ideas=[ExtractedIdea(original=original, normalized=original, status="VALID")])
            accepted, checks, guards = verify_expansions(SessionLocal, item, extraction,
                CuratorResult(decisions=[decision]), codes, client)
            metadata = {"pair": metadata, "scope_audits": checks}
    except Exception as exc:
        metadata = {"error_type": type(exc).__name__, "metadata": getattr(exc, "metadata", {})}
        reason = "Lỗi kỹ thuật audit; không thay đổi mã."
    with SessionLocal() as db:
        current = db.scalar(select(Item).where(Item.id == item.id).with_for_update())
        event = db.get(PipelineAudit, audit_id)
        if current.codebook_epoch == epoch and accepted is not None:
            guarded = guard_members(db, accepted, guards).decisions[0]
            if guarded.decision == "EXPAND_EXISTING":
                response = db.scalar(select(Response).join(ResponseIdea, ResponseIdea.response_id == Response.id)
                                     .where(ResponseIdea.code_id == source["id"]).limit(1))
                allowed = {code.id: code for code in db.scalars(select(ItemCode).where(ItemCode.item_id == item.id)).all()}
                if response:
                    target_row, changed, reason = _expand_existing_code(db, item=current, response=response, decision=guarded, allowed_codes=allowed)
                    if target_row:
                        for code_id in changed:
                            members = db.execute(select(ResponseIdea.embedding, ResponseIdea.embedding_model)
                                .where(ResponseIdea.code_id == code_id, ResponseIdea.mapping_status == "VALID")).all()
                            rebuild_confirmed_members(allowed[code_id], [(vector or [], model or "") for vector, model in members],
                                                      drift_cosine_floor=settings.centroid_drift_cosine_floor)
                        synchronize_response_mappings(db, item.id)
                        current.scores_dirty = True
                        reason = "MERGED"
        elif current.codebook_epoch != epoch:
            reason = "STALE_EPOCH"
        event.payload = {**event.payload, "status": "RETRY" if reason == "STALE_EPOCH" or "error_type" in metadata else "DONE",
                         "reason": reason, "metadata": metadata}
        db.commit()
    return True

"""Xuất một mốc phân tích nhất quán; không tạo phiên bản codebook vận hành."""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.models.models import Item, Response, Participant
from app.pipeline.codebook_service import (
    _eligible_query, _code_live_counts, list_curator_codes,
    refresh_final_frequency_scores, refresh_item_scoring_state,
)


def prepare_export(db):
    """Giữ khóa item và đồng bộ các điểm trước khi đọc bảng xuất."""
    items = db.scalars(select(Item).order_by(Item.id).with_for_update()).all()
    if any(db.scalar(select(Response.id).where(
        Response.item_id == item.id, Response.processing_state.in_(["QUEUED", "RUNNING", "SCORING"])
    ).limit(1)) for item in items):
        raise HTTPException(status_code=409, detail="Còn bài đang xử lý. Hãy xuất lại khi hàng đợi hoàn tất để có một mốc nhất quán.")
    for item in items:
        refresh_item_scoring_state(db, item)
        refresh_final_frequency_scores(db, item.id)
        item.scores_dirty = False
    return items


def export_analysis(db):
    """Không xuất email, tên hay token; văn bản trả lời vẫn là dữ liệu nghiên cứu thô."""
    items = prepare_export(db)
    salt = secrets.token_bytes(32)
    def pseudonym(value):
        return hashlib.sha256(salt + value.encode()).hexdigest()[:20]
    snapshots = []
    for item in items:
        eligible = set(db.scalars(_eligible_query(item.id, Response.id)).all())
        counts = _code_live_counts(db, item.id)
        rows = db.scalars(select(Response).where(Response.item_id == item.id).order_by(Response.created_at, Response.id)).all()
        responses = []
        for row in rows:
            participant = db.get(Participant, row.participant_id)
            responses.append({
                "id": row.id, "participant": pseudonym(row.participant_id),
                "group": participant.ai_usage_group, "data_source": row.data_source,
                "protocol": row.protocol, "created_at": row.created_at.isoformat(),
                "eligible": row.id in eligible, "status": row.scoring_status.value,
                "input_lines": row.input_lines or row.raw_input.splitlines(),
                "mapping": row.mapping, "scoring": row.scoring,
                "mapping_metadata": row.mapping_meta, "scoring_metadata": row.scoring_meta,
            })
        codes = [{key: value for key, value in code.items() if key not in {
            "embedding", "centroid", "prototype_vectors"}} for code in list_curator_codes(db, item.id)]
        snapshots.append({"item_id": item.id, "name": item.name, "codes": codes,
                          "valid_idea_denominator": sum(value[2] for value in counts.values()),
                          "counts": counts, "responses": responses})
    prompts = Path(__file__).parents[1] / "pipeline/prompts"
    payload = {"created_at": datetime.now(timezone.utc).isoformat(),
               "data_source": settings.survey_data_source,
               "rubric": "AUT_TOP10_180S; originality <=1%:2, <=5%:1, else:0; elaboration 1+4 evidence groups",
               "prompt_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(prompts.glob("*.txt"))},
               "items": snapshots}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result = {"sha256": hashlib.sha256(serialized.encode()).hexdigest(), "payload": payload}
    db.commit()
    return result

"""Kiểm tra chỉ đọc các người nhóm HIGH đã nộp nhưng chưa có lượt FINAL."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, exists, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Participant, Response, ResponseIdea, Item


def failure_summary(value, path=""):
    result = []
    if isinstance(value, dict):
        if value.get("error_category"):
            result.append({"path": path, "stage": value.get("stage"),
                           "type": value.get("error_type"), "category": value.get("error_category"),
                           "model": value.get("model"), "reason": str(value.get("reason", ""))[:240]})
        for key, child in value.items():
            result.extend(failure_summary(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(failure_summary(child, f"{path}[{index}]"))
    return result


def main():
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    with Session(engine) as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        submitted = exists(select(Response.id).where(
            Response.participant_id == Participant.id, Response.data_source == settings.survey_data_source))
        final = exists(select(Response.id).where(
            Response.participant_id == Participant.id, Response.data_source == settings.survey_data_source,
            Response.scoring_status == "FINAL"))
        participants = db.scalars(select(Participant).where(
            Participant.ai_usage_group == "HIGH", submitted, ~final).order_by(Participant.created_at)).all()
        output = {"current_source": settings.survey_data_source, "mock_mode": settings.mock_mode, "participants": []}
        for person in participants:
            entries = []
            for row in db.scalars(select(Response).where(
                Response.participant_id == person.id, Response.data_source == settings.survey_data_source).order_by(Response.created_at)).all():
                item = db.get(Item, row.item_id)
                entries.append({
                    "id": row.id, "item_id": row.item_id, "item_name": item.name,
                    "status": row.scoring_status.value, "state": row.processing_state,
                    "error": row.processing_error, "resolution_attempts": row.resolution_attempts,
                    "processing_attempts": row.processing_attempts,
                    "lease_until": row.processing_lease_until.isoformat() if row.processing_lease_until else None,
                    "item_status": item.calibration_status.value,
                    "errors": failure_summary(row.mapping_meta) + failure_summary(row.scoring_meta),
                    "checkpoint_keys": list((row.mapping_checkpoint or {}).keys()),
                    "ideas": [{"id": idea.id, "status": idea.mapping_status,
                               "coding_state": idea.coding_state, "code_id": idea.code_id,
                               "decision": idea.curator_decision, "reason": idea.reason,
                               "review_status": idea.review_status}
                              for idea in db.scalars(select(ResponseIdea).where(
                                  ResponseIdea.response_id == row.id, ResponseIdea.mapping_status == "VALID",
                                  ResponseIdea.code_id.is_(None))).all()],
                })
            output["participants"].append({"id": person.id, "responses": entries})
        print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

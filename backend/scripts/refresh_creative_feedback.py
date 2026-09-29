"""Cập nhật riêng nhận xét cho bài đã chấm; không chạy lại mapping hoặc thay điểm."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.db import SessionLocal
from app.config import settings
from app.models.models import Response, Item, PipelineAudit, ResponseScoringStatus
from app.schemas.schemas import ScoringResult, Item as ItemSchema
from app.pipeline.creative_feedback import generate_creative_feedback
from app.pipeline.llm import aggregate_usage
from app.controllers.response_controller import _client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    with SessionLocal() as db:
        candidates = db.scalars(select(Response).where(
            Response.processing_state == "DONE", Response.scoring_status == ResponseScoringStatus.FINAL,
            Response.data_source != "SYNTHETIC",
        ).order_by(Response.created_at)).all()
        ids = [row.id for row in candidates if row.scoring and
               (row.scoring_meta or {}).get("creative_feedback", {}).get("status") != "GENERATED"][:args.limit]
    print(json.dumps({"candidates": len(ids), "ids": ids}), flush=True)
    if not args.apply or not ids:
        return
    if settings.mock_mode:
        raise RuntimeError("Cần provider thật để viết nhận xét cho bài đã chấm.")
    artifact = Path(__file__).resolve().parents[2] / ".artifacts"
    artifact.mkdir(exist_ok=True)
    report = []
    client = _client()
    for key in ids:
        with SessionLocal() as db:
            row = db.get(Response, key)
            item_row = db.get(Item, row.item_id)
            item = ItemSchema(id=item_row.id, name=item_row.name, description=item_row.description)
            before = row.scoring
            before_meta = row.scoring_meta or {}
            scores = ScoringResult.model_validate(before)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (artifact / f"feedback-before-{key}-{stamp}.json").write_text(
            json.dumps({"id": key, "scoring": before, "scoring_meta": before_meta}, ensure_ascii=False, indent=2), encoding="utf-8")
        text, meta = generate_creative_feedback(item, scores.per_idea_scores, client, fallback=scores.summary_vi)
        with SessionLocal() as db, db.begin():
            row = db.scalar(select(Response).where(Response.id == key).with_for_update())
            if row.scoring != before or row.scoring_meta != before_meta or row.processing_state != "DONE":
                report.append({"id": key, "status": "SKIPPED_CONCURRENT_CHANGE"})
                continue
            row.scoring = {**before, "summary_vi": text}
            row.scoring_meta = {**before_meta, "creative_feedback": meta,
                                "usage": aggregate_usage([before_meta, meta])}
            db.add(PipelineAudit(item_id=row.item_id, response_id=row.id, event="CREATIVE_FEEDBACK_REFRESHED",
                                 payload={"status": meta["status"], "prompt_hash": meta.get("prompt_hash"),
                                          "scores_changed": False}))
        report.append({"id": key, "status": meta["status"], "summary": text})
        print(json.dumps({"id": key, "status": meta["status"]}), flush=True)
    (artifact / "creative-feedback-refresh.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

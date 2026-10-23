"""Chạy lại đúng các response được chỉ định có ý thiếu quyết định do lỗi LLM."""

import argparse
import json
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import settings
from app.controllers import response_worker
from app.db import SessionLocal
from app.models.models import Item, PipelineAudit, Response, ResponseIdea, ResponseScoringStatus
from app.pipeline.codebook_service import refresh_item_scoring_state


def has_curator_failure(value):
    if isinstance(value, dict):
        if value.get("error_category") and str(value.get("stage", "")).startswith("code_curator"):
            return True
        return any(has_curator_failure(child) for child in value.values())
    return isinstance(value, list) and any(has_curator_failure(child) for child in value)


def claim(response_id, *, kind):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = db.scalar(select(Response).where(Response.id == response_id).with_for_update(skip_locked=True))
        if row is None:
            raise RuntimeError("Không tìm thấy response hoặc đang bị worker khác khóa.")
        expected = ResponseScoringStatus.PENDING_REVIEW if kind == "resolution" else ResponseScoringStatus.COLLECTING
        if row.scoring_status != expected or row.processing_state != "DONE":
            # Worker nền có thể nhận bước chấm điểm ngay sau khi mapping hoàn tất.
            return None
        if row.processing_lease_until and row.processing_lease_until > now:
            raise RuntimeError("Response đang trong thời gian chờ thử lại; chưa nhận lại.")
        if kind == "resolution":
            missing = db.scalar(select(ResponseIdea.id).where(
                ResponseIdea.response_id == row.id, ResponseIdea.code_id.is_(None),
                ResponseIdea.mapping_status == "VALID", ResponseIdea.curator_decision == "MISSING_DECISION").limit(1))
            if not missing or not has_curator_failure(row.mapping_meta):
                raise RuntimeError("Response không có bằng chứng thiếu quyết định do lỗi Curator LLM.")
            if row.participant.ai_usage_group != "HIGH":
                raise RuntimeError("Response nằm ngoài nhóm HIGH được yêu cầu.")
        token = str(uuid.uuid4())
        db.add(PipelineAudit(item_id=row.item_id, response_id=row.id, event="MANUAL_CURATOR_RETRY" if kind == "resolution" else "MANUAL_RETRY_SCORING",
            payload={"model": settings.active_curator_model if kind == "resolution" else settings.active_llm_model,
                     "previous_status": row.scoring_status.value, "previous_resolution_attempts": row.resolution_attempts,
                     "previous_metadata": row.mapping_meta if kind == "resolution" else row.scoring_meta}))
        row.processing_claim_token = token
        row.processing_state = "RUNNING" if kind == "resolution" else "SCORING"
        row.processing_lease_until = now + timedelta(seconds=settings.processing_lease_seconds)
        row.processing_attempts += 1
        db.commit()
        return token


def run_claimed(response_id, token, kind):
    stop = threading.Event()
    heartbeat = threading.Thread(target=response_worker._heartbeat, args=(response_id, token, stop), daemon=True)
    heartbeat.start()
    try:
        if kind == "resolution":
            response_worker._run_mapping(response_id, token, resolving=True)
        else:
            response_worker._run_scoring(response_id, token)
    except Exception as error:
        response_worker._record_failure(response_id, token, kind, error)
        print(json.dumps({"response_id": response_id, "stage": kind, "error": type(error).__name__}), flush=True)
        raise
    finally:
        stop.set()
        heartbeat.join(timeout=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if settings.mock_mode:
        raise RuntimeError("Không chạy bảo trì dữ liệu thật với MOCK_MODE=true.")
    for response_id in dict.fromkeys(args.response_id):
        with SessionLocal() as db:
            row = db.get(Response, response_id)
            if row is None:
                raise RuntimeError("Không tìm thấy response.")
            print(json.dumps({"response_id": response_id, "before": row.scoring_status.value,
                              "model": settings.active_curator_model, "apply": args.apply}), flush=True)
        if not args.apply:
            continue
        token = claim(response_id, kind="resolution")
        if token:
            run_claimed(response_id, token, "resolution")
        with SessionLocal() as db:
            row = db.get(Response, response_id)
            item = db.scalar(select(Item).where(Item.id == row.item_id).with_for_update())
            refresh_item_scoring_state(db, item)
            item.calibration_dirty = False
            db.commit()
        token = claim(response_id, kind="scoring")
        if token:
            run_claimed(response_id, token, "scoring")
        with SessionLocal() as db:
            row = db.get(Response, response_id)
            print(json.dumps({"response_id": response_id, "after": row.scoring_status.value,
                              "state": row.processing_state, "scores": {key: getattr(row, key) for key in
                                  ("fluency", "flexibility", "originality", "elaboration")}}), flush=True)


if __name__ == "__main__":
    main()

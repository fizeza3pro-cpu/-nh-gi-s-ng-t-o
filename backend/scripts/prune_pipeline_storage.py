"""Dọn dữ liệu tạm theo hạn lưu; mặc định chỉ thống kê, thêm --apply để thực hiện."""
import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, func, select, update

from app.db import SessionLocal
from app.models.models import PipelineAudit, Response, ResponseScoringStatus, SurveySession


def prune_storage(db, *, before: datetime, apply: bool = False) -> dict:
    """Giữ audit mới nhất, quyết định mapping/admin và mọi căn cứ điểm FINAL."""
    latest = Response.mapping_meta["latest_audit_id"].as_string()
    retained = select(latest).where(latest.is_not(None))
    audit_filter = (
        PipelineAudit.created_at < before,
        PipelineAudit.event.in_(["JOB_STARTED", "PIPELINE_ATTEMPT", "PIPELINE_FAILURE"]),
        PipelineAudit.id.not_in(retained),
    )
    session_filter = (
        SurveySession.deadline_at < before,
        SurveySession.submitted_at.is_(None),
        ~exists(select(Response.id).where(Response.survey_session_id == SurveySession.id)),
    )
    checkpoint_filter = (
        Response.scoring_status == ResponseScoringStatus.FINAL,
        Response.mapping_checkpoint != {},
    )
    counts = {
        "technical_audits": db.scalar(select(func.count()).select_from(PipelineAudit).where(*audit_filter)),
        "abandoned_sessions": db.scalar(select(func.count()).select_from(SurveySession).where(*session_filter)),
        "final_checkpoints": db.scalar(select(func.count()).select_from(Response).where(*checkpoint_filter)),
        "applied": apply,
    }
    if apply:
        db.execute(delete(PipelineAudit).where(*audit_filter).execution_options(synchronize_session=False))
        db.execute(delete(SurveySession).where(*session_filter).execution_options(synchronize_session=False))
        db.execute(update(Response).where(*checkpoint_filter).values(mapping_checkpoint={}).execution_options(synchronize_session=False))
        db.commit()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90, help="Giữ tối thiểu số ngày dữ liệu kỹ thuật này")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days phải từ 1 trở lên")
    with SessionLocal() as db:
        print(prune_storage(db, before=datetime.now(timezone.utc) - timedelta(days=args.days), apply=args.apply))


if __name__ == "__main__":
    main()

"""Phiên khảo sát AUT 3 phút, chọn tối đa 10 ý sáng tạo nhất."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models.models import SurveySession, Item, Participant
from app.schemas.schemas import SurveySessionOut


def start_session(db, participant, payload):
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Cần đồng ý tham gia trước khi bắt đầu.")
    if db.get(Item, payload.item_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    # Khóa hồ sơ để hai lần bấm bắt đầu không tạo hai đồng hồ song song.
    db.scalar(select(Participant).where(Participant.id == participant.id).with_for_update())
    now = datetime.now(timezone.utc)
    row = db.scalar(select(SurveySession).where(
        SurveySession.participant_id == participant.id, SurveySession.item_id == payload.item_id,
        SurveySession.submitted_at.is_(None), SurveySession.deadline_at > now,
    ).order_by(SurveySession.started_at.desc()).limit(1))
    if row is None:
        row = SurveySession(participant_id=participant.id, item_id=payload.item_id,
                            started_at=now, deadline_at=now + timedelta(seconds=180), consent=True)
        db.add(row)
        db.commit()
        db.refresh(row)
    return SurveySessionOut(id=row.id, started_at=row.started_at, deadline_at=row.deadline_at, server_now=now)

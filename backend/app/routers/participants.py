"""API công khai để khởi tạo hồ sơ người tham gia khảo sát."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import participant_controller
from app.db import get_db
from app.schemas.schemas import (
    ParticipantCreate,
    ParticipantIdentify,
    ParticipantIdentifyResult,
    ParticipantIdentityOut,
)

router = APIRouter(prefix="/api/participants", tags=["participants"])


@router.post("/identify", response_model=ParticipantIdentifyResult)
def identify_participant(
    payload: ParticipantIdentify, db: Session = Depends(get_db)
) -> ParticipantIdentifyResult:
    return participant_controller.identify_participant(db, payload)


@router.post("", response_model=ParticipantIdentityOut, status_code=201)
def create_participant(
    payload: ParticipantCreate, db: Session = Depends(get_db)
) -> ParticipantIdentityOut:
    return participant_controller.create_participant(db, payload)

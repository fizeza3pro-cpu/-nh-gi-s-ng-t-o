"""API công khai để khởi tạo hồ sơ người tham gia khảo sát."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import participant_controller, response_controller
from app.core.deps import get_participant
from app.db import get_db
from app.models.models import Participant
from app.schemas.schemas import (
    ParticipantCreate,
    ParticipantIdentify,
    ParticipantIdentifyResult,
    ParticipantIdentityOut,
    ResponseSummary,
)

router = APIRouter(prefix="/api/participants", tags=["participants"])


@router.get("/me/responses", response_model=list[ResponseSummary])
def participant_responses(
    participant: Participant = Depends(get_participant),
    db: Session = Depends(get_db),
) -> list[ResponseSummary]:
    return response_controller.list_participant_responses(db, participant.id)


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

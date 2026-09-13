from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.controllers import response_controller
from app.core.deps import get_participant, require_admin
from app.db import get_db
from app.models.models import Participant as ParticipantModel
from app.schemas.schemas import ResponseSummary, ScoreRequest, ScoreResponse

router = APIRouter(tags=["responses"])


@router.post("/api/score", response_model=ScoreResponse)
def score(
    req: ScoreRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    participant: ParticipantModel = Depends(get_participant),
) -> ScoreResponse:
    return response_controller.create_response(db, req, participant, background_tasks)


@router.get("/api/responses", response_model=list[ResponseSummary])
def responses(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> list[ResponseSummary]:
    return response_controller.list_responses(db)


@router.get("/api/responses/{response_id}", response_model=ScoreResponse)
def response_detail(
    response_id: str,
    db: Session = Depends(get_db),
) -> ScoreResponse:
    return response_controller.get_response_detail(db, response_id)

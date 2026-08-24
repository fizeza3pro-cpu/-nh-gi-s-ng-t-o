from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import response_controller
from app.core.deps import get_current_user
from app.db import get_db
from app.models.models import User as UserModel
from app.schemas.schemas import ResponseSummary, ScoreRequest, ScoreResponse

router = APIRouter(tags=["responses"], dependencies=[Depends(get_current_user)])


@router.post("/api/score", response_model=ScoreResponse)
def score(
    req: ScoreRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ScoreResponse:
    return response_controller.create_response(db, req, current_user)


@router.get("/api/responses", response_model=list[ResponseSummary])
def responses(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> list[ResponseSummary]:
    # admin -> tất cả; user thường -> chỉ của chính mình (logic nằm trong controller)
    return response_controller.list_responses_for_user(db, current_user)


@router.get("/api/responses/{response_id}", response_model=ScoreResponse)
def response_detail(
    response_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ScoreResponse:
    return response_controller.get_response_detail(db, response_id, current_user)
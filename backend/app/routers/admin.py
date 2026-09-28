from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.controllers import admin_controller, participant_controller, analysis_export
from app.core.deps import require_admin
from app.db import get_db
from app.models.models import User as UserModel
from app.schemas.schemas import (
    AdminClusterAudit,
    AdminCodebookOverview,
    AdminCodebookSummary,
    AdminCuratorAudit,
    AdminDashboardStats,
    AdminExtractionAudit,
    AdminMappingReviewList,
    AdminMappingReviewResolution,
    AdminMappingReviewResult,
    AdminParticipantDetail,
    AdminParticipantSummary,
    ScoreResponse,
    ParticipantIdentityOut,
)

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get("/dashboard", response_model=AdminDashboardStats)
def dashboard(db: Session = Depends(get_db)) -> AdminDashboardStats:
    return admin_controller.get_dashboard_stats(db)


@router.get("/exports/responses.csv", response_class=Response)
def export_responses(db: Session = Depends(get_db)) -> Response:
    content = "\ufeff" + admin_controller.export_response_scores_csv(db)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="aut-response-scores.csv"'
        },
    )


@router.get("/participants", response_model=list[AdminParticipantSummary])
def participants(db: Session = Depends(get_db)) -> list[AdminParticipantSummary]:
    return admin_controller.list_participants_with_stats(db)


@router.get("/exports/analysis.json")
def export_analysis(db: Session = Depends(get_db)) -> dict:
    return analysis_export.export_analysis(db)


@router.get("/items/{item_id}/pipeline-audits")
def pipeline_audits(item_id: str, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return admin_controller.pipeline_audits(db, item_id, limit)


@router.get("/participants/{participant_id}", response_model=AdminParticipantDetail)
def participant_detail(
    participant_id: str, db: Session = Depends(get_db)
) -> AdminParticipantDetail:
    return admin_controller.get_participant_detail(db, participant_id)


@router.post("/participants/{participant_id}/access-token", response_model=ParticipantIdentityOut)
def issue_participant_token(participant_id: str, db: Session = Depends(get_db)):
    return participant_controller.issue_participant_token(db, participant_id)


@router.get("/items/codebooks", response_model=list[AdminCodebookOverview])
def codebooks(db: Session = Depends(get_db)) -> list[AdminCodebookOverview]:
    return admin_controller.list_codebooks(db)


@router.get("/items/{item_id}/codebook", response_model=AdminCodebookSummary)
def codebook(
    item_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    code_filter: Literal["ALL", "ACCEPTED", "UNCERTAIN", "REJECTED"] = "ALL",
    db: Session = Depends(get_db),
) -> AdminCodebookSummary:
    return admin_controller.get_codebook(
        db,
        item_id,
        page=page,
        page_size=page_size,
        code_filter=code_filter,
    )


@router.get("/items/{item_id}/extraction-audit", response_model=AdminExtractionAudit)
def extraction_audit(
    item_id: str, db: Session = Depends(get_db)
) -> AdminExtractionAudit:
    return admin_controller.get_extraction_audit(db, item_id)


@router.get("/items/{item_id}/curator-audit", response_model=AdminCuratorAudit)
def curator_audit(
    item_id: str, db: Session = Depends(get_db)
) -> AdminCuratorAudit:
    return admin_controller.get_curator_audit(db, item_id)


@router.get(
    "/items/{item_id}/mapping-reviews", response_model=AdminMappingReviewList
)
def mapping_reviews(
    item_id: str,
    review_status: Literal["PENDING", "RESOLVED"] = Query(default="PENDING"),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AdminMappingReviewList:
    return admin_controller.get_mapping_reviews(
        db, item_id, status=review_status, limit=limit
    )


@router.post(
    "/items/{item_id}/mapping-reviews/{idea_id}/resolve",
    response_model=AdminMappingReviewResult,
)
def resolve_mapping_review(
    item_id: str,
    idea_id: str,
    payload: AdminMappingReviewResolution,
    db: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin),
) -> AdminMappingReviewResult:
    return admin_controller.resolve_mapping_review(db, item_id, idea_id, payload, admin)


@router.get("/items/{item_id}/cluster-audit", response_model=AdminClusterAudit)
def cluster_audit(
    item_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AdminClusterAudit:
    return admin_controller.get_cluster_audit(db, item_id, limit=limit)


@router.post("/responses/{response_id}/retry")
def retry_response(response_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    return admin_controller.retry_failed_response(db, response_id)




@router.get("/responses/{response_id}", response_model=ScoreResponse)
def admin_response_detail(response_id: str, db: Session = Depends(get_db)) -> ScoreResponse:
    return admin_controller.get_response_detail(db, response_id)

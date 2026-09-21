from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import admin_controller
from app.core.deps import require_admin
from app.db import get_db
from app.schemas.schemas import (
    AdminCodeMerge,
    AdminCodeOption,
    AdminCodePatch,
    AdminCodebookOverview,
    AdminCodebookSummary,
    AdminCuratorAudit,
    AdminDashboardStats,
    AdminExtractionAudit,
    AdminParticipantDetail,
    AdminParticipantSummary,
)

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get("/dashboard", response_model=AdminDashboardStats)
def dashboard(db: Session = Depends(get_db)) -> AdminDashboardStats:
    return admin_controller.get_dashboard_stats(db)


@router.get("/participants", response_model=list[AdminParticipantSummary])
def participants(db: Session = Depends(get_db)) -> list[AdminParticipantSummary]:
    return admin_controller.list_participants_with_stats(db)


@router.get("/participants/{participant_id}", response_model=AdminParticipantDetail)
def participant_detail(
    participant_id: str, db: Session = Depends(get_db)
) -> AdminParticipantDetail:
    return admin_controller.get_participant_detail(db, participant_id)


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


@router.get("/items/{item_id}/code-options", response_model=list[AdminCodeOption])
def code_options(item_id: str, db: Session = Depends(get_db)) -> list[AdminCodeOption]:
    return admin_controller.list_code_options(db, item_id)


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


@router.patch("/items/{item_id}/codes/{code_id}", response_model=AdminCodebookSummary)
def update_code(
    item_id: str,
    code_id: str,
    patch: AdminCodePatch,
    db: Session = Depends(get_db),
) -> AdminCodebookSummary:
    return admin_controller.patch_code(db, item_id, code_id, patch)


@router.post("/items/{item_id}/codes/{code_id}/merge", response_model=AdminCodebookSummary)
def merge_code(
    item_id: str,
    code_id: str,
    payload: AdminCodeMerge,
    db: Session = Depends(get_db),
) -> AdminCodebookSummary:
    return admin_controller.merge_code(db, item_id, code_id, payload.target_code_id)


@router.delete("/items/{item_id}/codes/{code_id}", response_model=AdminCodebookSummary)
def delete_code(item_id: str, code_id: str, db: Session = Depends(get_db)) -> AdminCodebookSummary:
    return admin_controller.delete_code(db, item_id, code_id)


@router.delete("/items/{item_id}/codes", response_model=AdminCodebookSummary)
def delete_all_codes(item_id: str, db: Session = Depends(get_db)) -> AdminCodebookSummary:
    return admin_controller.delete_all_codes(db, item_id)


@router.post("/items/{item_id}/remap")
def remap(item_id: str, db: Session = Depends(get_db)) -> dict:
    return {"processed": admin_controller.remap_item(item_id)}

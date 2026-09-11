from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import admin_controller
from app.core.deps import require_admin
from app.db import get_db
from app.models.models import User as UserModel
from app.schemas.schemas import AdminDashboardStats, AdminUserDetail, AdminUserSummary

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get("/dashboard", response_model=AdminDashboardStats)
def dashboard(db: Session = Depends(get_db)) -> AdminDashboardStats:
    return admin_controller.get_dashboard_stats(db)


@router.get("/users", response_model=list[AdminUserSummary])
def users(db: Session = Depends(get_db)) -> list[AdminUserSummary]:
    return admin_controller.list_users_with_stats(db)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def user_detail(user_id: str, db: Session = Depends(get_db)) -> AdminUserDetail:
    return admin_controller.get_user_detail(db, user_id)
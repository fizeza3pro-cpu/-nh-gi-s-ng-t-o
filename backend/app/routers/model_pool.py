"""Route quản trị model BytePlus; nghiệp vụ ở model_controller."""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from app.controllers import model_controller
from app.core.deps import require_admin
from app.db import get_db
from app.models.models import User
from app.schemas.model_pool import ManagedModelUpdate, ModelBalanceUpdate, ModelPoolView, PoolSettingsUpdate

router = APIRouter(prefix="/api/admin/models", tags=["models"], dependencies=[Depends(require_admin)])


@router.get("", response_model=ModelPoolView)
def list_models(db: Session = Depends(get_db)):
    return model_controller.get_models(db)


@router.patch("/settings", response_model=ModelPoolView)
def update_settings(payload: PoolSettingsUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return model_controller.update_settings(db, payload, admin)


@router.put("/{slot}", response_model=ModelPoolView)
def update_model(payload: ManagedModelUpdate, slot: int = Path(ge=1, le=5),
                 db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return model_controller.update_model(db, slot, payload, admin)


@router.post("/{slot}/balance", response_model=ModelPoolView)
def update_balance(payload: ModelBalanceUpdate, slot: int = Path(ge=1, le=5),
                   db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return model_controller.update_balance(db, slot, payload, admin)

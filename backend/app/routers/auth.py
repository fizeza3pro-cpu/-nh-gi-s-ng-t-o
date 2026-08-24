from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import auth_controller
from app.core.deps import get_current_user
from app.db import get_db
from app.models.models import User as UserModel
from app.schemas.schemas import Token, UserLogin, UserOut, UserRegister

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> UserOut:
    return auth_controller.register_user(db, payload)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    return auth_controller.login_user(db, payload)


@router.get("/me", response_model=UserOut)
def me(current_user: UserModel = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
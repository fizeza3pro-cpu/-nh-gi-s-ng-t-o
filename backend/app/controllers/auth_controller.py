"""Nghiệp vụ đăng ký / đăng nhập."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import User as UserModel
from app.schemas.schemas import Token, UserLogin, UserOut, UserRegister


def register_user(db: Session, payload: UserRegister) -> UserOut:
    existing = db.scalar(select(UserModel).where(UserModel.username == payload.username))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email đã được đăng ký."
        )

    user = UserModel(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role="user",  # đăng ký công khai luôn là "user" — không cho tự nhận admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


def login_user(db: Session, payload: UserLogin) -> Token:
    user = db.scalar(select(UserModel).where(UserModel.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="username hoặc mật khẩu không đúng.",
        )
    token = create_access_token(user_id=user.id, role=user.role)
    return Token(access_token=token)
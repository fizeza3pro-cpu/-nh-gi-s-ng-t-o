"""Nghiệp vụ đăng nhập dành riêng cho quản trị viên."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.models import User as UserModel
from app.schemas.schemas import Token, UserLogin


def login_user(db: Session, payload: UserLogin) -> Token:
    user = db.scalar(select(UserModel).where(UserModel.username == payload.username))
    if (
        user is None
        or user.role != "admin"
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="username hoặc mật khẩu không đúng.",
        )
    token = create_access_token(user_id=user.id, role=user.role)
    return Token(access_token=token)

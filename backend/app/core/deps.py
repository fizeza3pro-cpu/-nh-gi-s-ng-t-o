"""Dependency dùng chung cho các route cần đăng nhập / cần quyền admin.

Tương đương middleware `authMiddleware` / `requireAdmin` trong Express.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models.models import User as UserModel

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> UserModel:
    """Đọc header `Authorization: Bearer <token>`, trả về user tương ứng.

    Ném 401 nếu thiếu token, token sai/hết hạn, hoặc user không còn tồn tại.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập."
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn.",
        )

    user = db.get(UserModel, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Người dùng không tồn tại."
        )
    return user


def require_admin(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """Dùng thêm sau get_current_user, chặn nếu không phải admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ admin mới có quyền truy cập.",
        )
    return current_user
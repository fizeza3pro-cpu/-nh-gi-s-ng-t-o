"""Dependency dùng chung cho các route cần đăng nhập / cần quyền admin.

Tương đương middleware `authMiddleware` / `requireAdmin` trong Express.
"""

import jwt
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models.models import Participant as ParticipantModel
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


def get_participant(
    participant_id: str | None = Header(default=None, alias="X-Participant-Id"),
    db: Session = Depends(get_db),
) -> ParticipantModel:
    """Đọc participant UUID từ header và đảm bảo hồ sơ đã được tạo."""
    if participant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bạn cần điền thông tin người tham gia trước khi làm bài.",
        )
    try:
        normalized_id = str(UUID(participant_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã người tham gia không hợp lệ.",
        ) from exc

    participant = db.get(ParticipantModel, normalized_id)
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy hồ sơ người tham gia. Vui lòng điền lại thông tin.",
        )
    return participant

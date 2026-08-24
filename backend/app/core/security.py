"""Hash mật khẩu và tạo/giải mã JWT token."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt giới hạn tối đa 72 byte cho mỗi mật khẩu — cắt bớt nếu vượt quá,
    # tương tự khuyến nghị chính thức của thư viện bcrypt.
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Ném jwt.PyJWTError (hoặc lớp con) nếu token sai/hết hạn — caller tự bắt."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
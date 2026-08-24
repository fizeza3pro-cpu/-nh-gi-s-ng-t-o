"""

Quan hệ: User (1) --- (N) Response (N) --- (1) Item
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
import enum
from sqlalchemy import Enum as SAEnum

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

class User(Base):
    """Người dùng. role = 'admin' | 'user'."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    responses: Mapped[list["Response"]] = relationship(back_populates="user")


class Item(Base):
    """Đồ vật dùng trong bài test AUT (đũa, nón lá, chai nhựa...)."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    codes: Mapped[list] = mapped_column(JSON, default=list)

    responses: Mapped[list["Response"]] = relationship(back_populates="item")


class Response(Base):
    """Một lượt làm bài: input thô + kết quả mapping + kết quả chấm điểm."""

    __tablename__ = "responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), nullable=False, index=True)

    raw_input: Mapped[str] = mapped_column(Text, nullable=False)

    mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    scoring: Mapped[dict] = mapped_column(JSON, nullable=False)
    mapping_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    fluency: Mapped[int] = mapped_column(Integer, default=0)
    flexibility: Mapped[int] = mapped_column(Integer, default=0)
    originality: Mapped[int] = mapped_column(Integer, default=0)
    elaboration: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    user: Mapped["User | None"] = relationship(back_populates="responses")
    item: Mapped["Item"] = relationship(back_populates="responses")
"""

Quan hệ: User (1) --- (N) Response (N) --- (1) Item
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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


class ItemCodeCount(Base):
    """Đếm số lần mỗi Code xuất hiện trong các response HỢP LỆ của 1 item,
    tính từ cả dữ liệu pilot đã seed lẫn user thật submit sau này. Dùng để
    tính % tần suất -> Originality (xem app/pipeline/compute_scores.py)."""

    __tablename__ = "item_code_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("items.id"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("item_id", "code", name="uq_item_code"),)


class ItemStat(Base):
    """Tổng số ý hợp lệ tích lũy + phiên bản chuẩn (norm_version) đang
    dùng cho mỗi item — dùng làm mẫu số khi tính % tần suất Originality."""

    __tablename__ = "item_stats"

    item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("items.id"), primary_key=True
    )
    total_valid_responses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    norm_version: Mapped[str] = mapped_column(String(255), default="unseeded", nullable=False)
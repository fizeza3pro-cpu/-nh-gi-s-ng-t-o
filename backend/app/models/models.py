"""

Quan hệ: Participant (1) --- (N) Response (N) --- (1) Item
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
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


class ItemCalibrationStatus(str, enum.Enum):
    COLLECTING = "COLLECTING"
    CALIBRATING = "CALIBRATING"
    ACTIVE = "ACTIVE"
    RECALIBRATING = "RECALIBRATING"
    PAUSED = "PAUSED"


class CodeValidationStatus(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    UNCERTAIN = "UNCERTAIN"
    REJECTED = "REJECTED"


class CodeMaturityStatus(str, enum.Enum):
    EMERGING = "EMERGING"
    STABLE = "STABLE"
    MERGED = "MERGED"
    ARCHIVED = "ARCHIVED"


class ResponseScoringStatus(str, enum.Enum):
    COLLECTING = "COLLECTING"
    PENDING_REVIEW = "PENDING_REVIEW"
    PROVISIONAL = "PROVISIONAL"
    FINAL = "FINAL"
    EXCLUDED = "EXCLUDED"


class CodebookVersionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"

class User(Base):
    """Tài khoản quản trị. Người tham gia khảo sát không dùng bảng này."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)



class Participant(Base):
    """Người tham gia khảo sát, định danh bằng email khai báo chưa xác thực OTP."""

    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    email_masked: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    responses: Mapped[list["Response"]] = relationship(back_populates="participant")


class Item(Base):
    """Đồ vật dùng trong bài test AUT (đũa, nón lá, chai nhựa...)."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    calibration_status: Mapped[ItemCalibrationStatus] = mapped_column(
        SAEnum(ItemCalibrationStatus, name="item_calibration_status"),
        default=ItemCalibrationStatus.COLLECTING,
        nullable=False,
    )
    calibration_min_participants: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    originality_min_participants: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_version_participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_codebook_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    responses: Mapped[list["Response"]] = relationship(back_populates="item")
    dynamic_codes: Mapped[list["ItemCode"]] = relationship(
        back_populates="item", foreign_keys="ItemCode.item_id"
    )


class Response(Base):
    """Một lượt làm bài: input thô + kết quả mapping + kết quả chấm điểm."""

    __tablename__ = "responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), nullable=False, index=True)

    raw_input: Mapped[str] = mapped_column(Text, nullable=False)

    mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    scoring: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    mapping_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    fluency: Mapped[int] = mapped_column(Integer, default=0)
    flexibility: Mapped[int] = mapped_column(Integer, default=0)
    originality: Mapped[int] = mapped_column(Integer, default=0)
    elaboration: Mapped[int] = mapped_column(Integer, default=0)
    scoring_status: Mapped[ResponseScoringStatus] = mapped_column(
        SAEnum(ResponseScoringStatus, name="response_scoring_status"),
        default=ResponseScoringStatus.COLLECTING,
        nullable=False,
        index=True,
    )
    codebook_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("codebook_versions.id"), nullable=True, index=True
    )
    calibration_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    participant: Mapped["Participant"] = relationship(back_populates="responses")
    item: Mapped["Item"] = relationship(back_populates="responses")
    ideas: Mapped[list["ResponseIdea"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )


class ItemCode(Base):
    """Danh mục ngữ nghĩa do AI tự xây dựng cho một đồ vật."""

    __tablename__ = "item_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    validation_status: Mapped[CodeValidationStatus] = mapped_column(
        SAEnum(CodeValidationStatus, name="code_validation_status"),
        default=CodeValidationStatus.ACCEPTED,
        nullable=False,
        index=True,
    )
    maturity_status: Mapped[CodeMaturityStatus] = mapped_column(
        SAEnum(CodeMaturityStatus, name="code_maturity_status"),
        default=CodeMaturityStatus.EMERGING,
        nullable=False,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    relevance_reason: Mapped[str] = mapped_column(Text, default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    source_response_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("responses.id"), nullable=True
    )
    merged_into_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("item_codes.id"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(32), default="LLM", nullable=False)
    admin_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    item: Mapped["Item"] = relationship(back_populates="dynamic_codes", foreign_keys=[item_id])

    __table_args__ = (
        UniqueConstraint("item_id", "normalized_name", name="uq_item_code_normalized_name"),
    )


class ResponseIdea(Base):
    """Một ý tưởng đã tách, kèm quyết định mapping có thể kiểm toán."""

    __tablename__ = "response_ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    response_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("responses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("item_codes.id"), nullable=True)
    original: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(16), nullable=False)
    curator_decision: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    response: Mapped["Response"] = relationship(back_populates="ideas")
    code: Mapped["ItemCode | None"] = relationship(foreign_keys=[code_id])


class CodebookVersion(Base):
    """Snapshot bất biến dùng để tái lập điểm tại một thời điểm."""

    __tablename__ = "codebook_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("items.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CodebookVersionStatus] = mapped_column(
        SAEnum(CodebookVersionStatus, name="codebook_version_status"),
        default=CodebookVersionStatus.ACTIVE,
        nullable=False,
    )
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    codes: Mapped[list["CodebookVersionCode"]] = relationship(
        back_populates="version_row", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("item_id", "version", name="uq_codebook_item_version"),)


class CodebookVersionCode(Base):
    """Tần suất cố định của một code bên trong một snapshot."""

    __tablename__ = "codebook_version_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("codebook_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_id: Mapped[str] = mapped_column(String(36), ForeignKey("item_codes.id"), nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idea_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frequency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    version_row: Mapped["CodebookVersion"] = relationship(back_populates="codes")
    code: Mapped["ItemCode"] = relationship()

    __table_args__ = (UniqueConstraint("version_id", "code_id", name="uq_version_code"),)

# Hết phần khai báo ORM.

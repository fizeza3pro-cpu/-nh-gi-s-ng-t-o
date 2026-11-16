"""Cấu hình năm model BytePlus và sổ token độc lập với dữ liệu khảo sát."""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def _now():
    return datetime.now(timezone.utc)


def _id():
    return str(uuid.uuid4())


class ModelPoolSettings(Base):
    __tablename__ = "model_pool_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_switch: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, default=10000, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocked_reason: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ModelQuota(Base):
    __tablename__ = "model_quotas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    quota_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    quota_limit: Mapped[int] = mapped_column(Integer, default=500000, nullable=False)
    confirmed_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spent_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exhausted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagedModel(Base):
    __tablename__ = "managed_models"
    __table_args__ = (CheckConstraint("slot >= 1 AND slot <= 5", name="ck_managed_model_slot"),)
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    quota_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("model_quotas.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=131072, nullable=False)
    thinking_mode: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    blocked_reason: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class ModelTokenRequest(Base):
    __tablename__ = "model_token_requests"
    __table_args__ = (Index("ix_model_token_requests_provider_request", "quota_id", "provider_request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    quota_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_quotas.id"), index=True)
    model_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    call_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    response_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="IN_FLIGHT", index=True)
    reserved_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ModelPoolEvent(Base):
    __tablename__ = "model_pool_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

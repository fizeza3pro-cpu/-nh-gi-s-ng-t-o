"""Contract quản trị model; không đưa API key hoặc prompt vào phản hồi."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PoolSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    enabled: bool
    auto_switch: bool = True
    threshold: int = Field(default=10000, ge=0, le=1000000)


class ManagedModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=160)
    model_id: str = Field(min_length=2, max_length=255)
    quota_key: str = Field(min_length=2, max_length=160)
    enabled: bool = False
    context_window: int = Field(default=131072, ge=2048, le=2000000)
    thinking_mode: Literal["auto", "enabled", "disabled", "unsupported"] = "auto"


class ModelBalanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=0)
    remaining_tokens: int = Field(ge=0, le=1000000000)
    quota_limit: int = Field(default=500000, ge=1, le=1000000000)
    note: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def check_balance(self):
        if self.remaining_tokens > self.quota_limit:
            raise ValueError("Số dư không được lớn hơn hạn mức.")
        return self


class ManagedModelView(BaseModel):
    slot: int
    label: str
    model_id: str | None
    quota_key: str | None
    enabled: bool
    context_window: int
    thinking_mode: str
    status: str
    quota_limit: int
    remaining_tokens: int | None
    used_tokens: int | None
    reserved_tokens: int
    available_tokens: int | None
    unknown_requests: int
    balance_confirmed_at: datetime | None
    last_request_at: datetime | None


class ModelPoolView(BaseModel):
    enabled: bool
    auto_switch: bool
    threshold: int
    revision: int
    active_slot: int | None
    blocked_reason: str
    provider: str
    api_key_configured: bool
    models: list[ManagedModelView]
    events: list[dict]
    requests: list[dict]

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


from datetime import datetime


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    role: Literal["admin"]
    created_at: datetime

    model_config = {"from_attributes": True}  # cho phép tạo trực tiếp từ models.User


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _normalize_email(value: str) -> str:
    """Chuẩn hoá email vừa đủ, không áp dụng quy tắc riêng của từng nhà cung cấp."""
    normalized = value.strip().casefold()
    if len(normalized) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ValueError("Email không hợp lệ.")
    return normalized


class ParticipantIdentify(BaseModel):
    email: str
    participant_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class ParticipantCreate(ParticipantIdentify):
    age: int = Field(ge=10, le=100)
    gender: Literal["male", "female", "other", "prefer_not_to_say"]
    occupation: str = Field(min_length=2, max_length=255)

    @field_validator("occupation")
    @classmethod
    def normalize_occupation(cls, value: str) -> str:
        """Loại khoảng trắng thừa trước khi lưu thông tin ngành/nghề."""
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Ngành học hoặc nghề nghiệp phải có ít nhất 2 ký tự.")
        return normalized


class ParticipantOut(BaseModel):
    id: str
    email_masked: str | None
    email_verified_at: datetime | None
    age: int | None
    gender: str | None
    occupation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParticipantIdentityOut(BaseModel):
    """Thông tin tối thiểu được phép trả về khi chỉ mới đối chiếu email."""

    id: str
    email_masked: str | None
    email_verified_at: datetime | None

    model_config = {"from_attributes": True}


class ParticipantIdentifyResult(BaseModel):
    profile_required: bool
    participant: ParticipantIdentityOut | None = None



class Item(BaseModel):
    id: str
    name: str
    description: str




class MappedIdea(BaseModel):
    original: str
    normalized: str
    code: str | None = None
    status: Literal["VALID", "INVALID", "DUPLICATE"]
    is_valid: bool  # suy từ status, không tin trực tiếp trường do LLM trả về
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def derive_is_valid(cls, data):
        """Tương thích JSON legacy chưa lưu trường dẫn xuất `is_valid`."""
        if isinstance(data, dict) and "is_valid" not in data:
            return {**data, "is_valid": data.get("status") == "VALID"}
        return data


class MappingResult(BaseModel):
    ideas: list[MappedIdea]


class PerIdeaScore(BaseModel):
    normalized: str
    code: str
    originality: int = Field(ge=0, le=2)
    elaboration: int = Field(ge=1, le=5)
    note: str = ""


class ScoringResult(BaseModel):
    fluency: int
    flexibility: int
    flexibility_codes: list[str]
    originality: int
    elaboration: int
    per_idea_scores: list[PerIdeaScore]
    summary_vi: str


class ScoreRequest(BaseModel):
    item_id: str
    raw_input: str


class ScoreResponse(BaseModel):
    response_id: str
    item: Item
    raw_input: str
    mapping: MappingResult
    scoring: ScoringResult | None = None
    scoring_status: Literal[
        "COLLECTING", "PENDING_REVIEW", "PROVISIONAL", "FINAL", "EXCLUDED"
    ]
    codebook_version_id: str | None = None
    status_message: str = ""


class ResponseSummary(BaseModel):
    response_id: str
    created_at: str
    item_id: str
    item_name: str
    fluency: int
    flexibility: int
    originality: int
    elaboration: int
    scoring_status: str = "FINAL"


class ExtractedIdea(BaseModel):
    """Ý sau tầng tách/chuẩn hoá, trước khi Code Curator quyết định code."""

    original: str
    normalized: str
    status: Literal["VALID", "INVALID", "DUPLICATE"]
    uses_target_object: bool = False
    object_used: str = ""
    target_object_role: str = ""
    reason: str = ""

    @field_validator("object_used", "target_object_role", "reason", mode="before")
    @classmethod
    def normalize_nullable_reason(cls, value):
        """LLM đôi khi trả JSON null thay vì chuỗi rỗng cho trường không áp dụng."""
        return "" if value is None else value


class IdeaExtractionResult(BaseModel):
    ideas: list[ExtractedIdea]


class CuratorDecision(BaseModel):
    idea_index: int = Field(ge=0)
    decision: Literal["MATCH_EXISTING", "CREATE_NEW", "INVALID"]
    existing_code_id: str | None = None
    code_name: str | None = None
    code_description: str = ""
    target_object_confirmed: bool = False
    target_object_role: str = ""
    confidence: float = Field(ge=0, le=1)
    reason: str = ""

    @field_validator("code_description", "target_object_role", "reason", mode="before")
    @classmethod
    def normalize_nullable_text(cls, value):
        """Chấp nhận `null` ở các mô tả tuỳ chọn do LLM sinh."""
        return "" if value is None else value


class CuratorResult(BaseModel):
    decisions: list[CuratorDecision]


# ---------- ADMIN ----------
class AdminItemBreakdown(BaseModel):
    item_id: str
    item_name: str
    response_count: int
    calibration_status: str = "COLLECTING"
    eligible_response_count: int = 0
    eligible_participant_count: int = 0
    calibration_min_participants: int
    originality_min_participants: int
    accepted_code_count: int = 0
    uncertain_code_count: int = 0
    rejected_code_count: int = 0
    active_version: int | None = None


class AdminDailyStat(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class AdminScoringStatusCounts(BaseModel):
    collecting: int = 0
    pending_review: int = 0
    provisional: int = 0
    final: int = 0
    excluded: int = 0


class AdminDashboardStats(BaseModel):
    total_participants: int
    total_responses: int
    eligible_response_count: int
    responses_last_7_days: int
    responses_previous_7_days: int
    accepted_code_count: int
    uncertain_code_count: int
    rejected_code_count: int
    scoring_status_counts: AdminScoringStatusCounts
    daily_stats: list[AdminDailyStat]
    by_item: list[AdminItemBreakdown]
    recent_responses: list["AdminRecentResponse"]


class AdminParticipantSummary(BaseModel):
    id: str
    email_masked: str | None
    email_verified_at: datetime | None
    age: int | None
    gender: str | None
    occupation: str | None
    created_at: datetime
    response_count: int
    last_submitted_at: str | None = None

    model_config = {"from_attributes": True}


class AdminParticipantDetail(BaseModel):
    participant: ParticipantOut
    responses: list[ResponseSummary]


class AdminRecentResponse(BaseModel):
    response_id: str
    created_at: str
    participant_id: str
    item_id: str
    item_name: str
    fluency: int
    flexibility: int
    originality: int
    elaboration: int
    scoring_status: str = "FINAL"


class AdminCodebookCode(BaseModel):
    id: str
    name: str
    description: str
    validation_status: str
    maturity_status: str
    confidence: float
    relevance_reason: str
    rejection_reason: str
    created_by: str
    admin_locked: bool
    merged_into_id: str | None
    response_count: int
    participant_count: int
    idea_count: int
    eligible_response_count: int
    eligible_participant_count: int
    eligible_idea_count: int
    frequency: float
    created_at: datetime


class AdminExtractionExcludedIdea(BaseModel):
    idea_id: str
    response_id: str
    participant_id: str
    original: str
    normalized: str
    status: Literal["INVALID", "DUPLICATE"]
    reason: str
    created_at: datetime


class AdminExtractionAudit(BaseModel):
    item_id: str
    item_name: str
    invalid_count: int
    duplicate_count: int
    total_count: int
    displayed_count: int
    ideas: list[AdminExtractionExcludedIdea]


class AdminCuratorDecisionIdea(BaseModel):
    idea_id: str
    response_id: str
    participant_id: str
    original: str
    normalized: str
    mapping_status: Literal["VALID", "INVALID", "DUPLICATE"]
    decision: str
    code_id: str | None
    code_name: str | None
    confidence: float
    reason: str
    created_at: datetime


class AdminCuratorAudit(BaseModel):
    item_id: str
    item_name: str
    match_existing_count: int
    create_new_count: int
    invalid_count: int
    guarded_count: int
    total_count: int
    displayed_count: int
    decisions: list[AdminCuratorDecisionIdea]


class AdminCodebookSummary(BaseModel):
    item_id: str
    item_name: str
    calibration_status: str
    eligible_response_count: int
    eligible_participant_count: int
    eligible_idea_count: int
    calibration_min_participants: int
    originality_min_participants: int
    active_version: int | None
    pending_idea_count: int
    extraction_invalid_count: int
    extraction_duplicate_count: int
    accepted_code_count: int
    rejected_code_count: int
    codes: list[AdminCodebookCode]


class AdminCodePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    validation_status: Literal["ACCEPTED", "UNCERTAIN", "REJECTED"] | None = None
    admin_locked: bool | None = None


class AdminCodeMerge(BaseModel):
    target_code_id: str


# AdminDashboardStats tham chiếu tới AdminRecentResponse định nghĩa phía sau.
AdminDashboardStats.model_rebuild()

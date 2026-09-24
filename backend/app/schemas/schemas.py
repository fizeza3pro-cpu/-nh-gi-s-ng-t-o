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
    full_name: str = Field(min_length=2, max_length=255)
    age: int = Field(ge=10, le=100)
    gender: Literal["male", "female", "other", "prefer_not_to_say"]
    occupation: str = Field(min_length=2, max_length=255)
    ai_usage_group: Literal["LOW", "HIGH"]

    @field_validator("full_name", "occupation")
    @classmethod
    def normalize_profile_text(cls, value: str) -> str:
        """Loại khoảng trắng thừa trước khi lưu họ tên và ngành/nghề."""
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Thông tin phải có ít nhất 2 ký tự.")
        return normalized


class ParticipantOut(BaseModel):
    id: str
    full_name: str | None
    email_masked: str | None
    email_verified_at: datetime | None
    age: int | None
    gender: str | None
    occupation: str | None
    ai_usage_group: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ParticipantIdentityOut(BaseModel):
    """Thông tin tối thiểu được phép trả về khi chỉ mới đối chiếu email."""

    id: str
    full_name: str | None
    email_masked: str | None
    email_verified_at: datetime | None
    ai_usage_group: str | None

    model_config = {"from_attributes": True}


class ParticipantIdentifyResult(BaseModel):
    profile_required: bool
    participant: ParticipantIdentityOut | None = None



class Item(BaseModel):
    id: str
    name: str
    description: str




class FunctionalSignature(BaseModel):
    """Mô tả chức năng chuẩn, độc lập với cách diễn đạt bề mặt của response."""

    goal: str = ""
    object_role: str = ""
    mechanism: str = ""
    transformation: str = ""
    target: str = ""
    context: str = ""

    @field_validator(
        "goal", "object_role", "mechanism", "transformation", "target", "context", mode="before"
    )
    @classmethod
    def normalize_nullable_text(cls, value):
        return "" if value is None else " ".join(str(value).split())


class MappedIdea(BaseModel):
    original: str
    normalized: str
    code: str | None = None
    status: Literal["VALID", "INVALID", "DUPLICATE"]
    is_valid: bool  # suy từ status, không tin trực tiếp trường do LLM trả về
    reason: str = ""
    line_index: int = 0
    functional_signature: FunctionalSignature = Field(default_factory=FunctionalSignature)
    curator_decision: str = ""

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
    original: str = ""
    normalized: str
    code: str
    originality: int = Field(ge=0, le=2)
    elaboration: int = Field(ge=1, le=5)
    meaningful_word_count: int = Field(default=0, ge=0)
    elaboration_details: dict[str, str] = Field(default_factory=dict)
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
    responses: list[str] = Field(default_factory=list, max_length=10)
    raw_input: str = ""

    @model_validator(mode="after")
    def normalize_responses(self):
        """Nhận giao diện 10 dòng mới và vẫn đọc request cũ trong thời gian chuyển đổi."""
        values = self.responses or self.raw_input.splitlines()
        cleaned = [" ".join(value.split()) for value in values if value and value.strip()]
        if not cleaned:
            raise ValueError("Cần nhập ít nhất một ý tưởng.")
        if len(cleaned) > 10:
            raise ValueError("Mỗi lượt chỉ được gửi tối đa 10 ý tưởng.")
        self.responses = cleaned
        self.raw_input = "\n".join(cleaned)
        return self


class ScoreResponse(BaseModel):
    response_id: str
    item: Item
    raw_input: str
    mapping: MappingResult
    scoring: ScoringResult | None = None
    scoring_status: Literal[
        "COLLECTING", "PENDING_REVIEW", "PROVISIONAL", "FINAL", "EXCLUDED"
    ]
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
    line_index: int = Field(default=0, ge=0, le=9)
    duplicate_of_index: int | None = Field(default=None, ge=0, le=9)
    functional_signature: FunctionalSignature = Field(default_factory=FunctionalSignature)

    @field_validator("object_used", "target_object_role", "reason", mode="before")
    @classmethod
    def normalize_nullable_reason(cls, value):
        """LLM đôi khi trả JSON null thay vì chuỗi rỗng cho trường không áp dụng."""
        return "" if value is None else value


class IdeaExtractionResult(BaseModel):
    ideas: list[ExtractedIdea]


class CuratorDecision(BaseModel):
    idea_index: int = Field(ge=0)
    decision: Literal[
        "MATCH_EXISTING", "OUT_OF_CODEBOOK", "CREATE_NEW", "INVALID", "UNCERTAIN"
    ]
    existing_code_id: str | None = None
    code_name: str | None = None
    code_description: str = ""
    target_object_confirmed: bool = False
    target_object_role: str = ""
    confidence: float = Field(ge=0, le=1)
    reason: str = ""
    functional_signature: FunctionalSignature = Field(default_factory=FunctionalSignature)
    existing_code_evaluations: list[dict] = Field(default_factory=list)
    inclusion_rules: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    positive_examples: list[str] = Field(default_factory=list)
    nearest_code_ids: list[str] = Field(default_factory=list)
    policy_gates: dict[str, bool] = Field(default_factory=dict)
    challenge_reason: str = ""

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
    qualifying_response_count: int = 0
    qualifying_idea_count: int = 0
    qualifying_participant_count: int = 0
    scoring_min_participants: int
    scoring_min_ideas: int
    accepted_code_count: int = 0
    uncertain_code_count: int = 0
    rejected_code_count: int = 0


class AdminDailyStat(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class AdminScoringStatusCounts(BaseModel):
    collecting: int = 0
    pending_review: int = 0
    provisional: int = 0
    final: int = 0
    excluded: int = 0


class AdminAiGroupStats(BaseModel):
    group: Literal["LOW", "HIGH"]
    participant_count: int = 0
    response_count: int = 0
    final_response_count: int = 0
    mean_fluency: float | None = None
    mean_flexibility: float | None = None
    mean_originality: float | None = None
    mean_elaboration: float | None = None


class AdminDashboardStats(BaseModel):
    total_participants: int
    total_responses: int
    qualifying_response_count: int
    responses_last_7_days: int
    responses_previous_7_days: int
    accepted_code_count: int
    uncertain_code_count: int
    rejected_code_count: int
    scoring_status_counts: AdminScoringStatusCounts
    daily_stats: list[AdminDailyStat]
    by_item: list[AdminItemBreakdown]
    recent_responses: list["AdminRecentResponse"]
    ai_group_stats: list[AdminAiGroupStats]


class AdminParticipantSummary(BaseModel):
    id: str
    full_name: str | None
    email_masked: str | None
    email_verified_at: datetime | None
    age: int | None
    gender: str | None
    occupation: str | None
    ai_usage_group: str | None
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
    merged_into_name: str | None
    response_count: int
    participant_count: int
    idea_count: int
    contributing_response_count: int
    contributing_participant_count: int
    contributing_idea_count: int
    frequency: float
    created_at: datetime
    functional_key: str = ""
    functional_signature: FunctionalSignature = Field(default_factory=FunctionalSignature)
    inclusion_rules: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    positive_examples: list[str] = Field(default_factory=list)


class AdminCodeOption(BaseModel):
    id: str
    name: str


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
    functional_signature: FunctionalSignature = Field(default_factory=FunctionalSignature)
    mapping_evidence: dict = Field(default_factory=dict)


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


class AdminCodebookOverview(BaseModel):
    item_id: str
    item_name: str
    calibration_status: str
    qualifying_response_count: int
    qualifying_participant_count: int
    contributing_idea_count: int
    scoring_min_participants: int
    scoring_min_ideas: int
    pending_idea_count: int
    extraction_invalid_count: int
    extraction_duplicate_count: int
    accepted_code_count: int
    rejected_code_count: int


class AdminCodebookSummary(AdminCodebookOverview):
    code_page: int
    code_page_size: int
    code_total: int
    code_page_count: int
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

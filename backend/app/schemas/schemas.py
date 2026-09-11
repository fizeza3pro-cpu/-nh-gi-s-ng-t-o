from typing import Literal
from pydantic import BaseModel, Field


from datetime import datetime


class UserRegister(BaseModel):
    username: str
    password: str = Field(min_length=8)
    full_name: str = ""


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    role: Literal["user", "admin"]
    created_at: datetime

    model_config = {"from_attributes": True}  # cho phép tạo trực tiếp từ models.User


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"



class Item(BaseModel):
    id: str
    name: str
    description: str
    codes: list[str]




class MappedIdea(BaseModel):
    original: str
    normalized: str
    code: str | None = None
    status: Literal["VALID", "INVALID", "DUPLICATE"]
    is_valid: bool  # suy từ status trong mapping.py, KHÔNG do LLM trả về —
                     # tách biệt khỏi status để logic tính điểm không phải
                     # so string "VALID" rải rác nhiều nơi
    reason: str = ""


class MappingResult(BaseModel):
    ideas: list[MappedIdea]


# Trạng thái tần suất code của 1 item, đọc từ bảng item_code_counts/item_stats.
class ItemCodeStats(BaseModel):
    item_id: str
    total_valid_responses: int
    code_counts: dict[str, int]


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
    scoring: ScoringResult


class ResponseSummary(BaseModel):
    response_id: str
    created_at: str
    item_id: str
    item_name: str
    fluency: int
    flexibility: int
    originality: int
    elaboration: int


# ---------- ADMIN ----------
class AdminItemBreakdown(BaseModel):
    item_id: str
    item_name: str
    response_count: int
    avg_fluency: float
    avg_flexibility: float
    avg_originality: float
    avg_elaboration: float


class AdminDashboardStats(BaseModel):
    total_users: int
    total_responses: int
    responses_last_7_days: int
    responses_previous_7_days: int
    daily_stats: list["AdminDailyStat"]
    by_item: list[AdminItemBreakdown]
    recent_responses: list["AdminRecentResponse"]
    top_users_by_total: list["AdminTopUserByTotal"]
    top_users_by_dimension: "AdminTopUsersByDimension"


class AdminDailyStat(BaseModel):
    date: str  # YYYY-MM-DD
    count: int
    avg_score: float  # TB (fluency+flexibility+originality+elaboration)/4 trong ngày đó, 0 nếu không có lượt nào


class AdminUserSummary(BaseModel):
    id: str
    username: str
    full_name: str
    role: Literal["user", "admin"]
    created_at: datetime
    response_count: int
    last_submitted_at: str | None = None

    model_config = {"from_attributes": True}


class AdminUserDetail(BaseModel):
    user: UserOut
    responses: list[ResponseSummary]


class AdminTopUserByTotal(BaseModel):
    user_id: str
    username: str
    full_name: str
    total_score: int
    submit_count: int
    last_submitted_at: str


class AdminTopUserByDimension(BaseModel):
    user_id: str
    username: str
    full_name: str
    avg_value: float


class AdminTopUsersByDimension(BaseModel):
    fluency: list[AdminTopUserByDimension]
    flexibility: list[AdminTopUserByDimension]
    originality: list[AdminTopUserByDimension]
    elaboration: list[AdminTopUserByDimension]


class AdminRecentResponse(BaseModel):
    response_id: str
    created_at: str
    username: str
    item_id: str
    item_name: str
    fluency: int
    flexibility: int
    originality: int
    elaboration: int


# AdminDashboardStats tham chiếu tới các class định nghĩa SAU nó bằng
# forward-ref chuỗi ("AdminDailyStat"...) — phải rebuild lại sau khi toàn
# bộ module đã load xong thì pydantic mới resolve được các tên đó.
AdminDashboardStats.model_rebuild()
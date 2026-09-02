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
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
    code: str
    status: Literal["VALID", "INVALID", "DUPLICATE"]
    reason: str = ""


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

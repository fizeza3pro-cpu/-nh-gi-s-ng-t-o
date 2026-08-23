from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.pipeline.mapping import run_mapping
from app.pipeline.scoring import run_scoring
from app.schemas import Item, ResponseSummary, ScoreRequest, ScoreResponse
from app.storage import (
    list_responses,
    load_items,
    load_response,
    new_response_id,
    save_response,
)


app = FastAPI(title="AUT tiếng Việt — API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client() -> genai.Client:
    if not settings.google_api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY chưa được cấu hình.")
    return genai.Client(api_key=settings.google_api_key)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": settings.llm_model}


@app.get("/api/items", response_model=list[Item])
def list_items(db: Session = Depends(get_db)) -> list[Item]:
    return list(load_items(db).values())


@app.get("/api/items/{item_id}", response_model=Item)
def get_item(item_id: str, db: Session = Depends(get_db)) -> Item:
    items = load_items(db)
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    return items[item_id]


def _mock_score(item: Item, raw: str) -> tuple:
    from app.schemas import MappedIdea, MappingResult, PerIdeaScore, ScoringResult
    lines = [l.strip() for l in raw.replace(",", "\n").splitlines() if l.strip()]
    ideas = []
    for i, line in enumerate(lines[:12]):
        ideas.append(MappedIdea(
            original=line,
            normalized=line,
            code=item.codes[i % len(item.codes)] if item.codes else "Khác",
            status="VALID",
            reason="",
        ))
    unique_codes = list(dict.fromkeys(i.code for i in ideas if i.status == "VALID"))
    per = [PerIdeaScore(normalized=i.normalized, code=i.code, originality=1, elaboration=2) for i in ideas]
    mapping = MappingResult(ideas=ideas)
    scoring = ScoringResult(
        fluency=len(ideas),
        flexibility=len(unique_codes),
        flexibility_codes=unique_codes,
        originality=len(ideas),
        elaboration=len(ideas) * 2,
        per_idea_scores=per,
        summary_vi="[MOCK] Đây là kết quả thử nghiệm — chưa kết nối Gemini.",
    )
    return mapping, {}, scoring, {}


@app.post("/api/score", response_model=ScoreResponse)
def score(req: ScoreRequest, db: Session = Depends(get_db)) -> ScoreResponse:
    items = load_items(db)
    if req.item_id not in items:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    raw = req.raw_input.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Câu trả lời rỗng.")

    item = items[req.item_id]

    if settings.mock_mode:
        mapping, mapping_meta, scoring, scoring_meta = _mock_score(item, raw)
    else:
        client = _client()
        mapping, mapping_meta = run_mapping(item, raw, client)
        scoring, scoring_meta = run_scoring(item, mapping, client)

    response_id = new_response_id()
    save_response(
        db,
        response_id,
        {
            "response_id": response_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "item": item.model_dump(),
            "raw_input": raw,
            "mapping": mapping.model_dump(),
            "scoring": scoring.model_dump(),
            "mapping_meta": mapping_meta,
            "scoring_meta": scoring_meta,
        },
        user_id=None,  # tạm None — bước thêm đăng nhập sẽ truyền user hiện tại vào đây
    )
    return ScoreResponse(
        response_id=response_id,
        item=item,
        raw_input=raw,
        mapping=mapping,
        scoring=scoring,
    )


@app.get("/api/responses", response_model=list[ResponseSummary])
def responses(db: Session = Depends(get_db)) -> list[ResponseSummary]:
    return [ResponseSummary(**s) for s in list_responses(db)]


@app.get("/api/responses/{response_id}", response_model=ScoreResponse)
def response_detail(response_id: str, db: Session = Depends(get_db)) -> ScoreResponse:
    data = load_response(db, response_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả.")
    return ScoreResponse(
        response_id=data["response_id"],
        item=Item(**data["item"]),
        raw_input=data["raw_input"],
        mapping=data["mapping"],
        scoring=data["scoring"],
    )
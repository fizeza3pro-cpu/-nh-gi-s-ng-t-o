from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, auth, items, participants, responses
from app.controllers.response_worker import start_workers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Worker đọc hàng đợi DB; restart không làm mất bài đã xác nhận."""
    stop = threading.Event()
    workers = start_workers(stop) if settings.async_processing_enabled or settings.survey_session_required else []
    try:
        yield
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=2)


app = FastAPI(title="AUT tiếng Việt — API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(participants.router)
app.include_router(responses.router)
app.include_router(admin.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "model": settings.active_llm_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": (
            settings.cloudflare_embedding_model
            if settings.embedding_provider == "cloudflare"
            else "local-hash-v1"
        ),
        "reference_cases_enabled": settings.reference_cases_enabled,
    }

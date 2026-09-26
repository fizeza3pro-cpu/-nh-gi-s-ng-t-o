from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, auth, items, participants, responses

app = FastAPI(title="AUT tiếng Việt — API")

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

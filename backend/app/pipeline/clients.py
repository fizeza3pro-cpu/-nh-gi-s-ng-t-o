"""Khởi tạo client LLM và embedding dùng chung cho worker và công cụ vận hành."""
from fastapi import HTTPException
from openai import OpenAI
from app.config import settings


def chat_client() -> OpenAI:
    """Khởi tạo client OpenAI-compatible theo provider được chọn trong môi trường."""
    if not settings.active_llm_api_key:
        env_name = {
            "groq": "GROQ_API_KEY",
            "cloudflare": "CLOUDFLARE_API_TOKEN",
            "byteplus": "BYTEPLUS_API_KEY",
        }[settings.llm_provider]
        raise HTTPException(status_code=500, detail=f"{env_name} chưa được cấu hình.")
    if settings.llm_provider == "cloudflare" and not settings.cloudflare_account_id:
        raise HTTPException(
            status_code=500,
            detail="CLOUDFLARE_ACCOUNT_ID chưa được cấu hình.",
        )
    return OpenAI(
        base_url=settings.active_llm_base_url.rstrip("/"),
        api_key=settings.active_llm_api_key,
        # Tự quản lý retry trong chat_json để tôn trọng Retry-After và tránh retry lồng nhau.
        max_retries=0,
        timeout=settings.llm_timeout_seconds,#thời gian chờ tối đa
    )



def embedding_client() -> OpenAI | None:
    """Tạo client Cloudflare riêng cho embedding; local chỉ dùng khi cấu hình rõ."""
    if settings.embedding_provider == "local":
        return None
    if not settings.cloudflare_api_token or not settings.cloudflare_account_id:
        raise HTTPException(
            status_code=500,
            detail=(
                "Semantic embedding cần CLOUDFLARE_API_TOKEN và "
                "CLOUDFLARE_ACCOUNT_ID."
            ),
        )
    return OpenAI(
        base_url=(
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{settings.cloudflare_account_id}/ai/v1"
        ),
        api_key=settings.cloudflare_api_token,
        max_retries=0,
        timeout=settings.embedding_timeout_seconds,
    )


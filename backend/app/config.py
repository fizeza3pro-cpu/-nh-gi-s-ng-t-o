from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    # Luôn đọc backend/.env, kể cả khi uvicorn được khởi chạy từ thư mục gốc hoặc từ IDE.
    # Biến môi trường thật của hệ điều hành/Render vẫn có độ ưu tiên cao hơn file này.
    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Nhà cung cấp LLM ---
    # Bắt buộc chọn rõ provider để tránh âm thầm quay về BytePlus khi thiếu cấu hình.
    llm_provider: Literal["byteplus", "groq", "cloudflare"]

    # --- BytePlus ModelArk ---
    byteplus_api_key: str = ""
    byteplus_base_url: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
    byteplus_model: str = "deepseek-v4-flash-260731"
    byteplus_code_curator_model: str | None = None

    # --- Groq ---
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "meta-llama/llama-prompt-guard-2-86m"
    groq_code_curator_model: str | None = None
    groq_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"

    # --- Cloudflare Workers AI ---
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    cloudflare_code_curator_model: str | None = None
    cloudflare_max_tokens: int = Field(default=4096, ge=256, le=8192)

    # --- Pipeline ---
    mapping_temperature: float = 0.1
    scoring_temperature: float = 0.4
    scoring_runs: int = 1
    code_curator_temperature: float = 0.1
    code_match_review_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    reference_cases_enabled: bool = True
    reference_cases_limit: int = Field(default=2, ge=0, le=8)
    scoring_min_participants: int = 24
    scoring_min_ideas: int = 150
    cors_origins: str = "http://localhost:5173"
    mock_mode: bool = False

    # --- Database ---
    database_url: str

    # --- Auth (dùng ở bước tiếp theo: đăng nhập / phân quyền) ---
    jwt_secret: str = "change-me-in-env"
    jwt_expire_minutes: int = 60 * 24
    participant_email_secret: str | None = None

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, value: str) -> str:
        """Cho phép cấu hình provider không phân biệt hoa thường."""
        return str(value).strip().casefold()

    @property
    def active_llm_api_key(self) -> str:
        """API key của provider đang được chọn."""
        if self.llm_provider == "groq":
            return self.groq_api_key
        if self.llm_provider == "cloudflare":
            return self.cloudflare_api_token
        return self.byteplus_api_key

    @property
    def active_llm_base_url(self) -> str:
        """Base URL OpenAI-compatible của provider đang được chọn."""
        if self.llm_provider == "groq":
            return self.groq_base_url
        if self.llm_provider == "cloudflare":
            return (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{self.cloudflare_account_id}/ai/v1"
            )
        return self.byteplus_base_url

    @property
    def active_llm_model(self) -> str:
        """Model mặc định cho Extraction và Scoring."""
        if self.llm_provider == "groq":
            return self.groq_model
        if self.llm_provider == "cloudflare":
            return self.cloudflare_model
        return self.byteplus_model

    @property
    def active_curator_model(self) -> str:
        """Model Curator/Challenger; rỗng thì dùng model mặc định của provider."""
        if self.llm_provider == "groq":
            return self.groq_code_curator_model or self.groq_model
        if self.llm_provider == "cloudflare":
            return self.cloudflare_code_curator_model or self.cloudflare_model
        return self.byteplus_code_curator_model or self.byteplus_model

    @property
    def active_reasoning_effort(self) -> str | None:
        """Chỉ gửi mức suy luận khi model Groq được cấu hình có hỗ trợ."""
        if self.llm_provider != "groq" or self.groq_reasoning_effort == "none":
            return None
        return self.groq_reasoning_effort

    @property
    def active_max_tokens(self) -> int | None:
        """Cloudflare mặc định chỉ sinh 256 token nên cần cấp đủ chỗ cho JSON AUT."""
        return self.cloudflare_max_tokens if self.llm_provider == "cloudflare" else None


settings = Settings()

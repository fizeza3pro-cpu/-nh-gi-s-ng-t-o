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
    byteplus_model: str = "glm-5-3-flash-260828"
    byteplus_code_curator_model: str | None = None
    byteplus_challenger_model: str | None = None
    # DeepSeek V4 260425 mặc định suy luận sâu nếu bỏ trống. `minimal` tắt
    # reasoning cho tác vụ JSON ngắn, tránh trả tiền cho chuỗi suy luận ẩn.
    byteplus_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "minimal"

    # --- Groq ---
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "meta-llama/llama-prompt-guard-2-86m"
    groq_code_curator_model: str | None = None
    groq_challenger_model: str | None = None
    groq_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"

    # --- Cloudflare Workers AI ---
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    cloudflare_code_curator_model: str | None = None
    cloudflare_challenger_model: str | None = None
    cloudflare_max_tokens: int = Field(default=4096, ge=256, le=8192)

    # --- Semantic embedding ---
    # Embedding chạy độc lập với model chat để không chiếm context của Curator.
    embedding_provider: Literal["cloudflare", "local"] = "cloudflare"
    cloudflare_embedding_model: str = "@cf/qwen/qwen3-embedding-0.6b"
    embedding_batch_size: int = Field(default=64, ge=1, le=100)
    embedding_timeout_seconds: float = Field(default=20.0, ge=1.0, le=60.0)

    # --- Pipeline ---
    mapping_temperature: float = 0.1
    scoring_temperature: float = 0.4
    scoring_runs: int = 1
    code_curator_temperature: float = 0.1
    # Chỉ đưa vài code gần nhất vào prompt. Quét toàn bộ codebook làm kích thước
    # output tăng theo tích số ý × số code dù model chỉ cần chọn một kết quả.
    code_candidate_limit: int = Field(default=3, ge=1, le=8)
    # Giữ trường cũ để cấu hình triển khai không bị lỗi khi nâng cấp; retrieval
    # không còn dùng nó để ép full-scan trong prompt.
    codebook_full_scan_limit: int = Field(default=20, ge=1, le=100)
    # Cổng tạm thời cho auto-MATCH, cần hiệu chỉnh lại bằng dữ liệu chuyên gia.
    auto_match_retrieval_floor: float = Field(default=0.60, ge=0.0, le=1.0)
    auto_match_semantic_floor: float = Field(default=0.70, ge=0.0, le=1.0)
    auto_match_margin_floor: float = Field(default=0.08, ge=0.0, le=1.0)
    auto_match_goal_floor: float = Field(default=0.20, ge=0.0, le=1.0)
    auto_match_structural_floor: float = Field(default=0.20, ge=0.0, le=1.0)
    # Challenger có thể xác nhận cách diễn đạt đồng nghĩa dù token cấu trúc ít giao nhau,
    # nhưng vẫn phải chọn top-1 với semantic và margin đủ rõ.
    challenged_match_retrieval_floor: float = Field(default=0.50, ge=0.0, le=1.0)
    challenged_match_semantic_floor: float = Field(default=0.70, ge=0.0, le=1.0)
    challenged_match_margin_floor: float = Field(default=0.08, ge=0.0, le=1.0)
    reference_cases_enabled: bool = True
    reference_cases_limit: int = Field(default=2, ge=0, le=8)
    reference_cases_max_chars: int = Field(default=2200, ge=400, le=8000)
    scoring_min_participants: int = 24
    scoring_min_ideas: int = 150
    async_processing_enabled: bool = True
    processing_worker_count: int = Field(default=2, ge=1, le=16)
    processing_poll_seconds: float = Field(default=2.0, ge=0.2, le=60.0)
    processing_lease_seconds: int = Field(default=600, ge=60, le=14400)
    processing_max_attempts: int = Field(default=3, ge=1, le=10)
    submit_wait_seconds: float = Field(default=240.0, ge=0.0, le=900.0)
    submit_wait_poll_seconds: float = Field(default=0.5, ge=0.1, le=5.0)
    codebook_recheck_limit: int = Field(default=3, ge=1, le=10)
    resolver_max_attempts: int = Field(default=3, ge=1, le=6)
    resolver_retry_seconds: int = Field(default=15, ge=1, le=600)
    mapping_batch_size: int = Field(default=3, ge=1, le=10)
    novelty_candidate_limit: int = Field(default=12, ge=3, le=30)
    llm_timeout_seconds: float = Field(default=60, ge=5, le=180)
    survey_grace_seconds: int = Field(default=60, ge=0, le=300)
    survey_session_required: bool = True
    participant_token_required: bool = True
    survey_data_source: Literal["PILOT", "SURVEY"] = "PILOT"
    auto_code_audit_enabled: bool = True
    scope_audit_max_cases: int = Field(default=80, ge=8, le=500)
    llm_extraction_max_tokens: int = Field(default=3072, ge=512, le=16384)
    llm_curator_max_tokens: int = Field(default=3072, ge=512, le=16384)
    llm_challenger_max_tokens: int = Field(default=3072, ge=512, le=16384)
    llm_scoring_max_tokens: int = Field(default=3072, ge=512, le=16384)
    llm_aux_max_tokens: int = Field(default=3072, ge=512, le=16384)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    store_raw_llm_response: bool = False
    centroid_retrieval_enabled: bool = False
    centroid_drift_cosine_floor: float = Field(default=0.7, ge=-1.0, le=1.0)
    cluster_proposal_similarity_floor: float = Field(default=0.9, ge=0.0, le=1.0)
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
    def active_challenger_model(self) -> str:
        """Model phản biện có thể tách khỏi Curator để giảm lỗi tự xác nhận."""
        if self.llm_provider == "groq":
            return self.groq_challenger_model or self.active_curator_model
        if self.llm_provider == "cloudflare":
            return self.cloudflare_challenger_model or self.active_curator_model
        return self.byteplus_challenger_model or self.active_curator_model

    @property
    def active_reasoning_effort(self) -> str | None:
        """Mức suy luận của provider; BytePlus phải gửi rõ để không dùng mặc định cao."""
        if self.llm_provider == "byteplus":
            return self.byteplus_reasoning_effort
        if self.llm_provider == "groq" and self.groq_reasoning_effort != "none":
            return self.groq_reasoning_effort
        return None

    @property
    def active_max_tokens(self) -> int | None:
        """Cloudflare mặc định chỉ sinh 256 token nên cần cấp đủ chỗ cho JSON AUT."""
        return self.cloudflare_max_tokens if self.llm_provider == "cloudflare" else None

    def max_tokens_for(self, stage: str) -> int:
        """Giới hạn output theo stage, đồng thời tôn trọng trần của Cloudflare."""
        configured = {
            "idea_extraction": self.llm_extraction_max_tokens,
            "code_curator": self.llm_curator_max_tokens,
            "code_challenger": self.llm_challenger_max_tokens,
            "scoring": self.llm_scoring_max_tokens,
        }.get(stage, self.llm_aux_max_tokens)
        if self.llm_provider == "cloudflare":
            return min(configured, self.cloudflare_max_tokens)
        return configured


settings = Settings()

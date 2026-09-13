from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str
    llm_model: str = "poolside/laguna-s-2.1:free"
    mapping_temperature: float = 0.1
    scoring_temperature: float = 0.4
    scoring_runs: int = 1
    code_curator_model: str | None = None
    code_curator_temperature: float = 0.1
    code_accept_confidence: float = 0.82
    code_uncertain_confidence: float = 0.60
    code_stable_min_participants: int = 3
    calibration_min_participants: int = 30
    originality_min_participants: int = 100
    codebook_refresh_interval: int = 20
    cors_origins: str = "http://localhost:5173"
    mock_mode: bool = False

    # --- Database ---
    database_url: str

    # --- Auth (dùng ở bước tiếp theo: đăng nhập / phân quyền) ---
    jwt_secret: str = "change-me-in-env"
    jwt_expire_minutes: int = 60 * 24
    participant_email_secret: str | None = None


settings = Settings()

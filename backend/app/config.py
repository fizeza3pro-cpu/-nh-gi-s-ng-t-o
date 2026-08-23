from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_api_key: str
    llm_model: str = "gemini-3.6-flash"
    mapping_temperature: float = 0.1
    scoring_temperature: float = 0.4
    scoring_runs: int = 1
    cors_origins: str = "http://localhost:5173"
    mock_mode: bool = False

    # --- Database ---
    database_url: str

    # --- Auth (dùng ở bước tiếp theo: đăng nhập / phân quyền) ---
    jwt_secret: str = "change-me-in-env"
    jwt_expire_minutes: int = 60 * 24


settings = Settings()
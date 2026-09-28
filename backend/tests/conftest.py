"""Cấu hình môi trường tối thiểu để test không phụ thuộc file `.env` cá nhân."""

import os


os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("LLM_PROVIDER", "byteplus")
os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("ASYNC_PROCESSING_ENABLED", "false")
os.environ.setdefault("SURVEY_SESSION_REQUIRED", "false")
os.environ.setdefault("PARTICIPANT_TOKEN_REQUIRED", "false")

"""Cấu hình môi trường tối thiểu để test không phụ thuộc file `.env` cá nhân."""

import os


os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("LLM_PROVIDER", "byteplus")
os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("MOCK_MODE", "true")

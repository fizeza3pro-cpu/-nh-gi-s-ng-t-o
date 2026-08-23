"""Tiện ích chung cho script validation: tạo client, nạp ground truth."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.storage import load_items

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HUMAN_DIR = DATA_DIR / "human_ratings"


def make_client() -> OpenAI:
    if settings.mock_mode:
        print("[LỖI] MOCK_MODE=true — validation cần gọi API thật. Đặt MOCK_MODE=false trong .env.")
        sys.exit(1)
    if not settings.openai_api_key:
        print("[LỖI] Thiếu OPENAI_API_KEY trong .env.")
        sys.exit(1)
    return OpenAI(api_key=settings.openai_api_key)


def load_gold(filename: str) -> list[dict]:
    path = HUMAN_DIR / filename
    if not path.exists():
        print(f"[LỖI] Không tìm thấy ground truth: {path}")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def items_map():
    return load_items()

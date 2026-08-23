import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import Item


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ITEMS_PATH = DATA_DIR / "items.json"
RESPONSES_DIR = DATA_DIR / "responses"


def load_items() -> dict[str, Item]:
    raw = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    return {
        item_id: Item(id=item_id, **payload)
        for item_id, payload in raw.items()
    }


def new_response_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def save_response(response_id: str, payload: dict) -> Path:
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    path = RESPONSES_DIR / f"{response_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_response(response_id: str) -> dict | None:
    path = RESPONSES_DIR / f"{response_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_responses() -> list[dict]:
    """Tóm tắt mọi response đã lưu, mới nhất trước — cho dashboard/lịch sử."""
    if not RESPONSES_DIR.exists():
        return []
    summaries: list[dict] = []
    for path in RESPONSES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        scoring = data.get("scoring", {})
        item = data.get("item", {})
        summaries.append(
            {
                "response_id": data.get("response_id", path.stem),
                "created_at": data.get("created_at", ""),
                "item_id": item.get("id", ""),
                "item_name": item.get("name", ""),
                "fluency": scoring.get("fluency", 0),
                "flexibility": scoring.get("flexibility", 0),
                "originality": scoring.get("originality", 0),
                "elaboration": scoring.get("elaboration", 0),
            }
        )
    summaries.sort(key=lambda s: s["created_at"], reverse=True)
    return summaries

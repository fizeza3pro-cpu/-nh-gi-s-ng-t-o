"""Script chạy 1 lần: khởi tạo bảng DB + nạp dữ liệu cũ từ file JSON vào Postgres.

Cách chạy (đứng trong thư mục backend/):
    uv run python -m scripts.migrate_json_to_db
"""

import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Item as ItemModel
from app.models import Response as ResponseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
ITEMS_PATH = DATA_DIR / "items.json"
RESPONSES_DIR = DATA_DIR / "responses"


def migrate_items(db) -> int:
    if not ITEMS_PATH.exists():
        print(f"[bỏ qua] Không thấy {ITEMS_PATH}")
        return 0
    raw = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    count = 0
    for item_id, payload in raw.items():
        existing = db.get(ItemModel, item_id)
        if existing:
            existing.name = payload["name"]
            existing.description = payload.get("description", "")
            existing.codes = payload.get("codes", [])
        else:
            db.add(
                ItemModel(
                    id=item_id,
                    name=payload["name"],
                    description=payload.get("description", ""),
                    codes=payload.get("codes", []),
                )
            )
            count += 1
    db.commit()
    return count


def migrate_responses(db) -> int:
    if not RESPONSES_DIR.exists():
        print(f"[bỏ qua] Không thấy {RESPONSES_DIR}")
        return 0
    count = 0
    for path in sorted(RESPONSES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[lỗi] Không đọc được {path.name}: {exc}")
            continue

        response_id = data.get("response_id", path.stem)
        if db.get(ResponseModel, response_id):
            continue

        item = data.get("item", {})
        scoring = data.get("scoring", {})

        if item.get("id") and not db.get(ItemModel, item["id"]):
            db.add(
                ItemModel(
                    id=item["id"],
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    codes=item.get("codes", []),
                )
            )
            db.flush()

        db.add(
            ResponseModel(
                id=response_id,
                user_id=None,
                item_id=item.get("id", ""),
                raw_input=data.get("raw_input", ""),
                mapping=data.get("mapping", {}),
                scoring=scoring,
                mapping_meta=data.get("mapping_meta", {}),
                scoring_meta=data.get("scoring_meta", {}),
                fluency=scoring.get("fluency", 0),
                flexibility=scoring.get("flexibility", 0),
                originality=scoring.get("originality", 0),
                elaboration=scoring.get("elaboration", 0),
            )
        )
        count += 1
    db.commit()
    return count


def main() -> None:
    print("1) Tạo bảng (nếu chưa có)...")
    init_db()

    db = SessionLocal()
    try:
        n_items = migrate_items(db)
        print(f"2) Đã nạp/cập nhật {n_items} item mới vào bảng items.")

        n_resp = migrate_responses(db)
        print(f"3) Đã nạp {n_resp} response cũ vào bảng responses.")

        total_items = len(db.scalars(select(ItemModel)).all())
        total_resp = len(db.scalars(select(ResponseModel)).all())
        print(f"-- Tổng hiện có: {total_items} items, {total_resp} responses.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
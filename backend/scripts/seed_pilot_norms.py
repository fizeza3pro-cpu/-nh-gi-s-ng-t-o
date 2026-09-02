"""Script chạy 1 LẦN: nạp tần suất pilot (item_code_counts/item_stats)
vào Postgres. items.json (codebook) đã được nạp qua migrate_json_to_db.py
riêng — script này CHỈ lo phần tần suất Originality.

Cách chạy (đứng trong thư mục backend/):
    uv run python -m scripts.seed_pilot_norms
"""
import json
from pathlib import Path

from app.db import SessionLocal
from app.pipeline.code_stats_db import DBCodeStatsStore

BACKEND_DIR = Path(__file__).resolve().parent.parent
PILOT_NORMS_DIR = BACKEND_DIR / "data" / "pilot_norms"  # copy pilot_norms_*.json vào đây


def main() -> None:
    norm_files = list(PILOT_NORMS_DIR.glob("pilot_norms_*.json"))
    if not norm_files:
        print(f"Không tìm thấy file pilot_norms_*.json nào trong {PILOT_NORMS_DIR}")
        return

    db = SessionLocal()
    store = DBCodeStatsStore(db)
    try:
        for path in norm_files:
            norms = json.loads(path.read_text(encoding="utf-8"))
            store.seed_stats(
                item_id=norms["item_id"],
                code_counts=norms["code_counts"],
                norm_version=norms["norm_version"],
            )
            print(f"  seeded '{norms['item_id']}': {norms['total_valid_responses']} ý, "
                  f"{len(norms['code_counts'])} code, norm_version={norms['norm_version']}")
        db.commit()
        print(f"HOÀN TẤT — đã seed {len(norm_files)} item, đã commit.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
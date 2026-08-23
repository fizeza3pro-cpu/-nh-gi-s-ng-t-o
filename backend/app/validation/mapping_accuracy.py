"""Đo độ chính xác gán Code của Tầng 1 (Mapping) so với Code do human gán.

Mục tiêu: > 85% (CLAUDE.md E.1). Mỗi mục ground truth là 1 ý đơn + Code chuẩn.

Ground truth: data/human_ratings/mapping_gold.json
  [ {"item_id": "dua", "text": "gõ tạo nhịp", "code": "Nhạc cụ"}, ... ]

Chạy: uv run python -m app.validation.mapping_accuracy
"""
from __future__ import annotations

from app.pipeline.mapping import run_mapping
from app.validation._common import load_gold, make_client, items_map


def _norm(s: str) -> str:
    return s.strip().lower()


def main() -> None:
    client = make_client()
    items = items_map()
    gold = load_gold("mapping_gold.json")

    total = 0
    correct = 0
    misses: list[tuple[str, str, str]] = []

    print(f"Đang chấm mapping trên {len(gold)} ý...\n")
    for entry in gold:
        item = items.get(entry["item_id"])
        if item is None:
            print(f"  [bỏ qua] item_id lạ: {entry['item_id']}")
            continue
        mapping, _ = run_mapping(item, entry["text"], client)
        valid = [i for i in mapping.ideas if i.status == "VALID"]
        ai_code = valid[0].code if valid else "(không có VALID)"
        gold_code = entry["code"]
        total += 1
        if _norm(ai_code) == _norm(gold_code):
            correct += 1
        else:
            misses.append((entry["text"], gold_code, ai_code))

    acc = correct / total if total else 0.0
    print("\n===== KẾT QUẢ MAPPING ACCURACY (Tầng 1) =====")
    print(f"Đúng: {correct}/{total}  →  {acc:.1%}")
    print(f"Mục tiêu CLAUDE.md: > 85%  →  {'ĐẠT' if acc > 0.85 else 'CHƯA ĐẠT'}")
    if misses:
        print("\nCác ý gán sai (text | gold | AI):")
        for text, g, a in misses:
            print(f"  - {text!r}  |  {g}  →  {a}")


if __name__ == "__main__":
    main()

"""Đo tương đồng AI vs human trên toàn pipeline 2 tầng: ICC(2,1) + Pearson r.

Mục tiêu: ICC > 0.75, Pearson r > 0.70 (CLAUDE.md E.1).

Ground truth: data/human_ratings/scoring_gold.json
  [ {"item_id": "dua", "raw_input": "...", "human": {
       "originality_avg": 1.2, "elaboration_avg": 2.6,
       "fluency": 5, "flexibility": 3 }}, ... ]

Chạy: uv run python -m app.validation.icc
"""
from __future__ import annotations

from app.pipeline.mapping import run_mapping
from app.pipeline.scoring import run_scoring
from app.validation._common import load_gold, make_client, items_map
from app.validation.stats import icc_2_1, interpret_icc, pearson_r


def _ai_averages(scoring) -> dict:
    valid = max(scoring.fluency, 1)
    return {
        "originality_avg": scoring.originality / valid,
        "elaboration_avg": scoring.elaboration / valid,
        "fluency": float(scoring.fluency),
        "flexibility": float(scoring.flexibility),
    }


def main() -> None:
    client = make_client()
    items = items_map()
    gold = load_gold("scoring_gold.json")

    dims = ["originality_avg", "elaboration_avg", "fluency", "flexibility"]
    ai_vals: dict[str, list[float]] = {d: [] for d in dims}
    hu_vals: dict[str, list[float]] = {d: [] for d in dims}

    print(f"Đang chấm pipeline 2 tầng trên {len(gold)} response...\n")
    for idx, entry in enumerate(gold, 1):
        item = items.get(entry["item_id"])
        if item is None:
            print(f"  [bỏ qua] item_id lạ: {entry['item_id']}")
            continue
        mapping, _ = run_mapping(item, entry["raw_input"], client)
        scoring, _ = run_scoring(item, mapping, client)
        ai = _ai_averages(scoring)
        for d in dims:
            ai_vals[d].append(ai[d])
            hu_vals[d].append(float(entry["human"][d]))
        print(f"  [{idx}/{len(gold)}] {item.name}: AI orig_avg={ai['originality_avg']:.2f} "
              f"human={float(entry['human']['originality_avg']):.2f}")

    print("\n===== ICC(2,1) + PEARSON r — AI vs HUMAN =====")
    print(f"{'Chiều':<18}{'Pearson r':>12}{'ICC(2,1)':>12}   Nhận xét ICC")
    for d in dims:
        r = pearson_r(ai_vals[d], hu_vals[d])
        paired = [[a, h] for a, h in zip(ai_vals[d], hu_vals[d])]
        icc = icc_2_1(paired)
        print(f"{d:<18}{r:>12.3f}{icc:>12.3f}   {interpret_icc(icc)}")

    print("\nMục tiêu: ICC > 0.75, Pearson r > 0.70")


if __name__ == "__main__":
    main()

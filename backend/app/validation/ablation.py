"""ABLATION: pipeline 2 tầng vs baseline 1 tầng — đóng góp kỹ thuật chính.

So sánh tương quan với human của:
  (A) 2 tầng: Mapping → Scoring  (sản phẩm)
  (B) 1 tầng: gộp 1 call         (baseline)
Kỳ vọng: 2 tầng > 1 tầng (CLAUDE.md C.2, E.1).

Ground truth: data/human_ratings/scoring_gold.json (giống icc.py).

Chạy: uv run python -m app.validation.ablation
"""
from __future__ import annotations

from app.pipeline.mapping import run_mapping
from app.pipeline.scoring import run_scoring
from app.pipeline.single_call import run_single_call
from app.validation._common import load_gold, make_client, items_map
from app.validation.stats import icc_2_1, interpret_icc, pearson_r


def _orig_avg(scoring) -> float:
    return scoring.originality / max(scoring.fluency, 1)


def _report(name: str, ai: list[float], hu: list[float]) -> tuple[float, float]:
    r = pearson_r(ai, hu)
    icc = icc_2_1([[a, h] for a, h in zip(ai, hu)])
    print(f"{name:<26}{r:>12.3f}{icc:>12.3f}   {interpret_icc(icc)}")
    return r, icc


def main() -> None:
    client = make_client()
    items = items_map()
    gold = load_gold("scoring_gold.json")

    hu: list[float] = []
    two_tier: list[float] = []
    one_tier: list[float] = []

    print(f"Đang chạy ablation trên {len(gold)} response (mỗi response 3 call LLM)...\n")
    for idx, entry in enumerate(gold, 1):
        item = items.get(entry["item_id"])
        if item is None:
            continue
        # (A) 2 tầng.
        mapping, _ = run_mapping(item, entry["raw_input"], client)
        scoring2, _ = run_scoring(item, mapping, client)
        # (B) 1 tầng.
        scoring1, _ = run_single_call(item, entry["raw_input"], client)

        hu.append(float(entry["human"]["originality_avg"]))
        two_tier.append(_orig_avg(scoring2))
        one_tier.append(_orig_avg(scoring1))
        print(f"  [{idx}/{len(gold)}] {item.name}: 2tier={two_tier[-1]:.2f} "
              f"1tier={one_tier[-1]:.2f} human={hu[-1]:.2f}")

    print("\n===== ABLATION: Originality avg vs HUMAN =====")
    print(f"{'Phương pháp':<26}{'Pearson r':>12}{'ICC(2,1)':>12}   Nhận xét")
    r2, icc2 = _report("2 tầng (sản phẩm)", two_tier, hu)
    r1, icc1 = _report("1 tầng (baseline)", one_tier, hu)

    print("\n----- KẾT LUẬN -----")
    winner = "2 TẦNG" if r2 >= r1 else "1 TẦNG"
    print(f"Pearson: 2 tầng={r2:.3f} vs 1 tầng={r1:.3f}  →  thắng: {winner}")
    print(f"Chênh lệch r = {r2 - r1:+.3f} (dương = 2 tầng tốt hơn, đúng kỳ vọng)")


if __name__ == "__main__":
    main()

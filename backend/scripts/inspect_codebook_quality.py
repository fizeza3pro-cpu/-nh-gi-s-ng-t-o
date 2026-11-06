"""Rà soát codebook chỉ đọc, không gọi API, không gộp mã hoặc viết lại điểm.

Chạy: uv run python -m scripts.inspect_codebook_quality --output <bao-cao.json>
Các ngưỡng chỉ lọc cặp đáng xem xét, không xác nhận mã trùng nghĩa.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models.models import Item, ResponseIdea
from app.pipeline.codebook_service import list_curator_codes
from app.pipeline.code_retrieval import functional_key, normalize_text, semantic_signature_similarity, signature_similarity


def inspect_codebook_quality(db, item_id=None):
    """Nêu bằng chứng trùng tên/chữ ký/member và ranh giới thiếu; chưa kết luận ngữ nghĩa."""
    query = select(Item).order_by(Item.id)
    if item_id:
        query = query.where(Item.id == item_id)
    reports = []
    for item in db.scalars(query):
        codes = list_curator_codes(db, item.id)
        if not codes:
            continue
        ids = [code["id"] for code in codes]
        members = defaultdict(list)
        for code_id, original in db.execute(select(ResponseIdea.code_id, ResponseIdea.original).where(
                ResponseIdea.code_id.in_(ids), ResponseIdea.mapping_status == "VALID").order_by(ResponseIdea.id)):
            members[code_id].append(original)

        def view(code):
            return {**{key: code.get(key) for key in ("id", "name", "description", "functional_signature",
                                                     "inclusion_rules", "exclusion_rules")},
                    "member_count": len(members[code["id"]]),
                    "member_examples": list(dict.fromkeys(members[code["id"]]))[:4]}

        incomplete = []
        for code in codes:
            signature = code.get("functional_signature") or {}
            missing = [field for field in ("goal", "object_role", "mechanism") if not signature.get(field, "").strip()]
            missing += [field for field in ("inclusion_rules", "exclusion_rules") if not code.get(field)]
            contradiction = set(map(normalize_text, code.get("inclusion_rules") or [])) & set(map(normalize_text, code.get("exclusion_rules") or []))
            if missing or contradiction:
                incomplete.append({"code": view(code), "missing_fields": missing,
                                   "identical_inclusion_exclusion": sorted(contradiction)})

        pairs = []
        generic = {"dung", "de", "lam", "tu", "bang", "cua", "vat", "soi"}
        generic.update(normalize_text(item.name).split())
        for left, right in combinations(sorted(codes, key=lambda code: code["id"]), 2):
            lexical = signature_similarity(left["functional_signature"], right["functional_signature"])
            semantic = semantic_signature_similarity(left.get("signature_embeddings") or {}, right.get("signature_embeddings") or {})
            shared = set(map(normalize_text, members[left["id"]])) & set(map(normalize_text, members[right["id"]]))
            reasons = []
            left_name = set(normalize_text(left["name"]).split()) - generic
            right_name = set(normalize_text(right["name"]).split()) - generic
            name_similarity = len(left_name & right_name) / len(left_name | right_name) if left_name | right_name else 0
            if normalize_text(left["name"]) == normalize_text(right["name"]):
                reasons.append("SAME_NORMALIZED_NAME")
            if functional_key(left["functional_signature"]) == functional_key(right["functional_signature"]) and all(
                    left["functional_signature"].get(field) for field in ("goal", "object_role", "mechanism")):
                reasons.append("SAME_FUNCTIONAL_SIGNATURE")
            if lexical["weighted"] >= .65 and lexical["goal"] >= .45 and lexical["object_role"] >= .45:
                reasons.append("SIMILAR_FUNCTION_WORDS")
            if (lexical["goal"] >= .45 and lexical["object_role"] >= .2) or (
                    lexical["object_role"] == 1 and lexical["goal"] >= .2):
                reasons.append("SHARED_GOAL_AND_ROLE_WORDS")
            if name_similarity >= .5:
                reasons.append("SIMILAR_FUNCTION_NAMES")
            if semantic["goal"] >= .85 and semantic["object_role"] >= .85 and semantic["weighted"] >= .80:
                reasons.append("SIMILAR_FUNCTION_VECTORS")
            if shared:
                reasons.append("SAME_OBSERVED_TEXT_IN_MULTIPLE_CODES")
            if reasons:
                pairs.append({"left": view(left), "right": view(right), "signals": reasons,
                              "lexical_similarity": lexical, "semantic_similarity": semantic,
                              "name_similarity": round(name_similarity, 6),
                              "shared_observed_text": sorted(shared)[:4], "confirmed_duplicate": False})
        pairs.sort(key=lambda pair: (-len(pair["signals"]), -pair["lexical_similarity"]["weighted"], pair["left"]["id"]))
        reports.append({"item_id": item.id, "item_name": item.name, "active_code_count": len(codes),
                        "suspected_overlaps": pairs, "incomplete_or_conflicting_boundaries": incomplete})
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "read_only": True,
            "external_api_calls": 0, "thresholds_are_screening_only": True, "items": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        report = inspect_codebook_quality(db, args.item_id)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "items": len(report["items"]),
            "suspected_pairs": sum(len(item["suspected_overlaps"]) for item in report["items"]),
            "codes_with_boundary_issues": sum(len(item["incomplete_or_conflicting_boundaries"]) for item in report["items"])}, ensure_ascii=False))
    else:
        print(rendered)


if __name__ == "__main__":
    main()

"""Dọn key JSON đã bỏ; giữ lịch sử/audit và mọi bài đã chốt điểm."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.models import ItemCode, Response, ResponseIdea, ResponseScoringStatus, PipelineAudit


REMOVED_SIGNATURE_FIELDS = {"transformation", "target", "context"}
REMOVED_FIELDS = {"uses_target_object", "target_object_role", "target_object_confirmed"}


def clean_payload(value):
    """Chỉ bỏ key chữ ký/điều kiện đã ngưng dùng; không đụng nhóm bằng chứng Elaboration."""
    if isinstance(value, list):
        return [clean_payload(row) for row in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if key in REMOVED_FIELDS:
            continue
        if key in {"functional_signature", "idea_functional_signature"} and isinstance(child, dict):
            result[key] = {k: v for k, v in child.items() if k not in REMOVED_SIGNATURE_FIELDS}
        else:
            result[key] = clean_payload(child)
    return result


def cleanup(db: Session, *, apply: bool = False, backup_path: Path | None = None) -> dict:
    """Khóa hàng, sao lưu trước thay đổi; caller chịu trách nhiệm commit/rollback."""
    changes = []
    for code in db.scalars(select(ItemCode).order_by(ItemCode.id).with_for_update(skip_locked=True)):
        before = code.functional_signature or {}
        after = {k: v for k, v in before.items() if k not in REMOVED_SIGNATURE_FIELDS}
        if before != after:
            changes.append((code, "functional_signature", deepcopy(before), after))
    pending = select(ResponseIdea).join(Response, Response.id == ResponseIdea.response_id).where(
        Response.scoring_status != ResponseScoringStatus.FINAL, Response.scored_at.is_(None),
        Response.processing_state == "DONE",
    ).order_by(ResponseIdea.id).with_for_update(of=ResponseIdea, skip_locked=True)
    for idea in db.scalars(pending):
        signature = idea.functional_signature or {}
        after = {k: v for k, v in signature.items() if k not in REMOVED_SIGNATURE_FIELDS}
        if signature != after:
            changes.append((idea, "functional_signature", deepcopy(signature), after))
        evidence = idea.mapping_evidence or {}
        after = clean_payload(evidence)
        if evidence != after:
            changes.append((idea, "mapping_evidence", deepcopy(evidence), after))
    records = [{"table": row.__tablename__, "id": row.id, "field": field, "before": before, "after": after}
               for row, field, before, after in changes]
    result = {"applied": apply, "changed_fields": len(records),
              "codes": len({r["id"] for r in records if r["table"] == "item_codes"}),
              "ideas": len({r["id"] for r in records if r["table"] == "response_ideas"})}
    if not apply:
        return result
    if backup_path is None:
        raise ValueError("Phải có đường dẫn sao lưu khi áp dụng.")
    payload = json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "changes": records},
                         ensure_ascii=False, indent=2)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    # Không ghi đè một bản sao lưu cũ.
    with backup_path.open("x", encoding="utf-8") as stream:
        stream.write(payload)
    for row, field, before, after in changes:
        setattr(row, field, after)
    for item_id in sorted({row.item_id if isinstance(row, ItemCode) else row.response.item_id
                           for row, *_ in changes}):
        db.add(PipelineAudit(item_id=item_id, event="MAPPING_CONTRACT_CLEANUP", payload={
            **result, "backup_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "removed_signature_fields": sorted(REMOVED_SIGNATURE_FIELDS),
        }))
    db.flush()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = cleanup(db, apply=args.apply, backup_path=args.backup)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

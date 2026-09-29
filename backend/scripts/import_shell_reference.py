"""Nạp bổ sung mã vỏ đạn; mặc định chỉ xem kế hoạch, --apply mới ghi DB."""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.db import SessionLocal
from app.models.models import Item, ItemCode, PipelineAudit, CodeValidationStatus, CodeMaturityStatus
from app.pipeline.code_retrieval import core_signature_text, functional_key
from app.pipeline.dynamic_mapping import normalize_code_name
from app.pipeline.embedding import embed_texts
from app.pipeline.shell_reference import plan_shell_reference


def snapshot(codes):
    """Chụp mã để sao lưu và phát hiện thay đổi trong khi gọi embedding."""
    return [{column.name: getattr(row, column.name) for column in ItemCode.__table__.columns}
            for row in sorted(codes, key=lambda row: row.id)]


def insert_reference(db, item, plan, batch):
    """Chỉ thêm mã còn thiếu, giữ số mẫu và các ví dụ quan sát bằng không."""
    missing = [entry for entry, match in plan if match is None]
    if len(batch.vectors) != len(missing):
        raise ValueError("Số vector không khớp số mã mới.")
    created = []
    for entry, vector in zip(missing, batch.vectors):
        row = ItemCode(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"aut/reference/vo_dan/{entry['key']}")),
            item_id=item.id, name=entry["name"], normalized_name=normalize_code_name(entry["name"]),
            description=entry["description"], functional_signature=entry["functional_signature"],
            functional_key=functional_key(entry["functional_signature"]),
            inclusion_rules=entry["inclusion_rules"], exclusion_rules=entry["exclusion_rules"],
            positive_examples=[], embedding=vector, embedding_model=batch.model,
            centroid=[], centroid_sum=[], centroid_count=0, prototype_vectors=[],
            validation_status=CodeValidationStatus.ACCEPTED, maturity_status=CodeMaturityStatus.ACTIVE,
            created_by="AI_REFERENCE", admin_locked=False, confidence=0.0,
            relevance_reason="Mã tham chiếu AI biên soạn theo yêu cầu chủ khảo sát; chưa kiểm định liên giám khảo. Ví dụ minh họa không phải dữ liệu quan sát.",
        )
        db.add(row)
        created.append(row.id)
    if created:
        item.codebook_epoch = (item.codebook_epoch or 0) + 1
        item.scores_dirty = True
        db.add(PipelineAudit(item_id=item.id, event="REFERENCE_CODES_IMPORTED", payload={
            "created_ids": created, "reused_ids": [match.id for _, match in plan if match],
            "source": "app/pipeline/shell_reference.py", "empirically_validated": False,
            "synthetic_responses_added": 0,
        }))
    db.flush()
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        item = db.get(Item, "vo_dan")
        if item is None or item.name != "Vỏ đạn":
            raise RuntimeError("Không tìm thấy đúng đồ vật Vỏ đạn.")
        codes = db.scalars(select(ItemCode).where(ItemCode.item_id == item.id)).all()
        before = snapshot(codes)
        plan = plan_shell_reference(codes)
        missing = [entry for entry, match in plan if match is None]
        print(json.dumps({"existing": len(codes), "add": len(missing),
                          "reuse": len(plan) - len(missing), "new_keys": [entry["key"] for entry in missing]}))
    if not args.apply or not missing:
        return
    # Chỉ gửi chữ ký mã tự soạn, không gửi câu trả lời hay hồ sơ người tham gia.
    from app.controllers.response_controller import _embedding_client
    batch = embed_texts([core_signature_text(entry["functional_signature"]) for entry in missing], _embedding_client())
    artifact_dir = Path(__file__).resolve().parents[2] / ".artifacts"
    artifact_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = artifact_dir / f"shell-codes-before-reference-{stamp}.json"
    with SessionLocal() as db, db.begin():
        item = db.scalar(select(Item).where(Item.id == "vo_dan").with_for_update())
        codes = db.scalars(select(ItemCode).where(ItemCode.item_id == item.id).with_for_update()).all()
        if snapshot(codes) != before:
            raise RuntimeError("Codebook vừa thay đổi; chạy lại để lập kế hoạch mới.")
        backup.write_text(json.dumps({"item_id": item.id, "codebook_epoch": item.codebook_epoch,
                                      "codes": before}, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        created = insert_reference(db, item, plan_shell_reference(codes), batch)
    report = {"added": len(created), "created_ids": created, "backup": str(backup), "embedding_model": batch.model}
    (artifact_dir / "shell-reference-import-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()

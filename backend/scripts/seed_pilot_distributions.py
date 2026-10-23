"""Nạp mã và 450 ý mô phỏng cho cuộn chỉ, xẻng, mũ cối; --apply mới ghi DB."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models.models import Item, ItemCode, Response, ResponseIdea
from app.pipeline.code_retrieval import core_signature_text
from app.pipeline.embedding import embed_texts, EmbeddingBatch
from app.pipeline.pilot_reference import REFERENCES, corpus_options, plan_reference
from scripts.import_shell_reference import insert_reference, snapshot
from scripts.seed_shell_distribution import populate, build_corpus


def serialize(rows, model):
    """Lưu đầy đủ cột của các bản ghi có thể bị cập nhật điểm/tần suất."""
    return [{column.name: getattr(row, column.name) for column in model.__table__.columns} for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if settings.survey_data_source != "PILOT":
        raise RuntimeError("Chỉ nạp bộ dữ liệu này vào PILOT.")
    before, missing = {}, {}
    with SessionLocal() as db:
        for item_id in REFERENCES:
            item = db.get(Item, item_id)
            if item is None:
                raise RuntimeError(f"Thiếu đồ vật {item_id}.")
            codes = db.scalars(select(ItemCode).where(ItemCode.item_id == item_id)).all()
            before[item_id] = snapshot(codes)
            missing[item_id] = [spec for spec, match in plan_reference(item_id, codes) if match is None]
            options = corpus_options(item_id)
            build_corpus(options["counts"], options["variants"])
            print(json.dumps({"item": item_id, "new_codes": len(missing[item_id]),
                              "reused_codes": 20 - len(missing[item_id]), "participants": 5,
                              "responses": 15, "ideas": 150, "empirical": False}))
    if not args.apply:
        return
    if settings.mock_mode:
        raise RuntimeError("Không nạp embedding giả vào DB thật; tắt MOCK_MODE trước khi --apply.")
    # Chỉ gửi chữ ký mã tự biên soạn, không gửi bài hay hồ sơ của người tham gia.
    from app.pipeline.clients import embedding_client as _embedding_client
    specs = [spec for group in missing.values() for spec in group]
    batch = embed_texts([core_signature_text(spec["functional_signature"]) for spec in specs], _embedding_client())
    if len(batch.vectors) != len(specs):
        raise RuntimeError("Số embedding trả về không khớp.")
    if specs and not batch.semantic:
        raise RuntimeError("Không nạp vector dự phòng thay cho embedding ngữ nghĩa.")
    artifacts = Path(__file__).resolve().parents[2] / ".artifacts"
    artifacts.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = artifacts / f"pilot-three-items-before-{stamp}.json"
    reports = {}
    with SessionLocal() as db, db.begin():
        items = {item.id: item for item in db.scalars(select(Item).where(Item.id.in_(REFERENCES)).order_by(Item.id).with_for_update())}
        codes = db.scalars(select(ItemCode).where(ItemCode.item_id.in_(REFERENCES)).with_for_update()).all()
        for item_id in REFERENCES:
            if snapshot([row for row in codes if row.item_id == item_id]) != before[item_id]:
                raise RuntimeError("Codebook vừa đổi; chạy lại để lập kế hoạch mới.")
        responses = db.scalars(select(Response).where(Response.item_id.in_(REFERENCES)).with_for_update()).all()
        ideas = db.scalars(select(ResponseIdea).join(Response).where(Response.item_id.in_(REFERENCES))).all()
        backup_path.write_text(json.dumps({
            "items": serialize(items.values(), Item), "codes": serialize(codes, ItemCode),
            "responses": serialize(responses, Response), "ideas": serialize(ideas, ResponseIdea),
        }, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        offset = 0
        for item_id in REFERENCES:
            size = len(missing[item_id])
            item_batch = EmbeddingBatch(vectors=batch.vectors[offset:offset + size], model=batch.model, semantic=batch.semantic)
            offset += size
            created = insert_reference(db, items[item_id], plan_reference(item_id, [c for c in codes if c.item_id == item_id]),
                                       item_batch, source="app/pipeline/pilot_reference.py")
            reports[item_id] = {"codes_added": len(created), **populate(db, **corpus_options(item_id))}
    report = {"backup": str(backup_path), "empirical": False, "embedding_model": batch.model, "items": reports}
    report_path = artifacts / f"pilot-three-items-report-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=True))


if __name__ == "__main__":
    main()

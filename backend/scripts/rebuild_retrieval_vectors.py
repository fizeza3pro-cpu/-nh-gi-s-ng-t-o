"""Chuyển cache vector sang câu gốc và ba trường; không chạy lại mapping/scoring.

Mặc định chỉ thống kê. --apply cần backup mới và sẽ gửi văn bản cần embedding
đến provider đang cấu hình. Không gửi email/hồ sơ và không ghi điểm/snapshot FINAL.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.models import Item, ItemCode, Response, ResponseIdea
from app.pipeline.clients import embedding_client
from app.pipeline.code_retrieval import prepare_code_embeddings
from app.pipeline.embedding import embed_texts, embedding_model, configured_embedding_model
from app.pipeline.centroid import rebuild_confirmed_members

_CODE_CACHE_FIELDS = ("embedding", "embedding_model", "signature_embeddings", "centroid", "centroid_sum",
                      "centroid_count", "centroid_model", "centroid_revision", "centroid_dirty", "drift_flag", "prototype_vectors")


def rebuild_vectors(factory=SessionLocal, client=None, *, apply=False, backup_path: Path | None = None):
    """Lời gọi mạng ngoài khóa; trước khi ghi kiểm tra lại nội dung/tập thành viên."""
    model = embedding_model(client) if apply or client is not None else configured_embedding_model()
    with factory() as db:
        codes = [{"id": c.id, "item_id": c.item_id, "name": c.name, "description": c.description,
                  "functional_signature": c.functional_signature or {},
                  **{key: getattr(c, key) for key in _CODE_CACHE_FIELDS}}
                 for c in db.scalars(select(ItemCode).where(ItemCode.maturity_status == "ACTIVE",
                                    ItemCode.validation_status == "ACCEPTED")).all()]
        ideas = [{"id": i.id, "item_id": item_id, "code_id": i.code_id, "original": i.original,
                  "embedding": i.embedding or [], "embedding_model": i.embedding_model}
                 for i, item_id in db.execute(select(ResponseIdea, Response.item_id)
                    .join(Response, Response.id == ResponseIdea.response_id)
                    .where(ResponseIdea.mapping_status == "VALID", ResponseIdea.code_id.is_not(None),
                           Response.processing_state == "DONE", Response.scoring_status != "EXCLUDED")).all()
                 if not i.embedding or i.embedding_model != model]
    summary = {"applied": False, "target_model": model, "active_codes": len(codes), "ideas_to_convert": len(ideas),
               "codes_updated": 0, "ideas_updated": 0, "skipped_changed": 0}
    if not apply:
        return summary
    if backup_path is None:
        raise ValueError("Cần backup mới trước khi ghi cache vector.")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with backup_path.open("x", encoding="utf-8") as handle:
        # Chỉ giữ cache cũ để hoàn tác; không sao chép câu trả lời vào backup.
        json.dump({"codes": [{k: c[k] for k in ("id", *_CODE_CACHE_FIELDS)} for c in codes],
                   "ideas": [{k: i[k] for k in ("id", "embedding", "embedding_model")} for i in ideas]}, handle)
    for offset in range(0, len(codes), 16):
        batch = codes[offset:offset + 16]
        prepare_code_embeddings(batch, client)
        with factory() as db:
            for key in sorted({c["item_id"] for c in batch}):
                db.scalar(select(Item).where(Item.id == key).with_for_update())
            for snapshot in batch:
                code = db.get(ItemCode, snapshot["id"])
                if (code is None or code.maturity_status != "ACTIVE" or code.validation_status != "ACCEPTED"
                        or any(getattr(code, key) != snapshot[key] for key in ("name", "description", "functional_signature"))):
                    summary["skipped_changed"] += 1
                    continue
                code.embedding = snapshot["embedding"]
                code.embedding_model = snapshot["embedding_model"]
                code.signature_embeddings = snapshot["signature_embeddings"]
                code.centroid_dirty = True
                summary["codes_updated"] += 1
            db.commit()
    for offset in range(0, len(ideas), settings.embedding_batch_size):
        batch = ideas[offset:offset + settings.embedding_batch_size]
        vectors = embed_texts([i["original"] for i in batch], client)
        with factory() as db:
            for key in sorted({i["item_id"] for i in batch}):
                db.scalar(select(Item).where(Item.id == key).with_for_update())
            for snapshot, vector in zip(batch, vectors.vectors):
                idea = db.scalar(select(ResponseIdea).where(ResponseIdea.id == snapshot["id"]).with_for_update())
                if (idea is None or idea.original != snapshot["original"] or idea.code_id != snapshot["code_id"]
                        or idea.mapping_status != "VALID" or idea.response.processing_state != "DONE"
                        or idea.response.scoring_status == "EXCLUDED"):
                    summary["skipped_changed"] += 1
                    continue
                idea.embedding, idea.embedding_model = vector, vectors.model
                code = db.get(ItemCode, idea.code_id)
                if code is not None:
                    code.centroid_dirty = True
                summary["ideas_updated"] += 1
            db.commit()
    # Tâm dựng từ tập hiện hành dưới khóa; không gọi mạng trong transaction này.
    with factory() as db:
        for item in db.scalars(select(Item).order_by(Item.id).with_for_update()).all():
            for code in db.scalars(select(ItemCode).where(ItemCode.item_id == item.id, ItemCode.centroid_dirty.is_(True))).all():
                members = db.execute(select(ResponseIdea.embedding, ResponseIdea.embedding_model)
                    .join(Response, Response.id == ResponseIdea.response_id)
                    .where(ResponseIdea.code_id == code.id, ResponseIdea.mapping_status == "VALID", Response.scoring_status != "EXCLUDED")).all()
                rebuild_confirmed_members(code, [(v or [], m or "") for v, m in members],
                                          drift_cosine_floor=settings.centroid_drift_cosine_floor, expected_model=model)
                code.centroid_dirty = False
        db.commit()
    return {**summary, "applied": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply and args.backup is None:
        parser.error("--apply cần --backup trỏ đến file mới.")
    # Chế độ thống kê không tạo client, không gửi dữ liệu ra ngoài.
    client = embedding_client() if args.apply else None
    result = rebuild_vectors(client=client, apply=args.apply, backup_path=args.backup)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

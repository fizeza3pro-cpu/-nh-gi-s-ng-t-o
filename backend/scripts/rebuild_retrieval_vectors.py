"""Chuyển cache vector sang câu gốc và ba trường; không chạy lại mapping/scoring.

Mặc định chỉ thống kê. --apply cần backup mới và sẽ gửi văn bản cần embedding
đến provider đang cấu hình. Không gửi email/hồ sơ và không ghi điểm/snapshot FINAL.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import hashlib

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.models import Item, ItemCode, Response, ResponseIdea
from app.pipeline.clients import embedding_client
from app.pipeline.code_retrieval import prepare_code_embeddings
from app.pipeline.embedding import embed_texts, embedding_model, configured_embedding_model, response_embedding_text
from app.pipeline.centroid import rebuild_confirmed_members

_CODE_CACHE_FIELDS = ("embedding", "embedding_model", "signature_embeddings", "centroid", "centroid_sum",
                      "centroid_count", "centroid_model", "centroid_revision", "centroid_dirty", "drift_flag", "prototype_vectors")


def rebuild_vectors(factory=SessionLocal, client=None, *, apply=False, backup_path: Path | None = None,
                    only_idea_id: str | None = None, centroids_only: bool = False):
    """Lời gọi mạng ngoài khóa; trước khi ghi kiểm tra lại nội dung/tập thành viên."""
    model = configured_embedding_model() if centroids_only else (
        embedding_model(client) if apply or client is not None else configured_embedding_model())
    with factory() as db:
        codes = [{"id": c.id, "item_id": c.item_id, "item_name": c.item.name, "name": c.name, "description": c.description,
                  "functional_signature": c.functional_signature or {},
                  **{key: getattr(c, key) for key in _CODE_CACHE_FIELDS}}
                 for c in db.scalars(select(ItemCode).where(ItemCode.maturity_status == "ACTIVE",
                                    ItemCode.validation_status == "ACCEPTED")).all()]
        ideas = [{"id": i.id, "item_id": item_id, "item_name": i.response.item.name,
                  "code_id": i.code_id, "original": i.original,
                  "embedding": i.embedding or [], "embedding_model": i.embedding_model}
                 for i, item_id in db.execute(select(ResponseIdea, Response.item_id)
                    .join(Response, Response.id == ResponseIdea.response_id)
                    .where(ResponseIdea.mapping_status == "VALID", ResponseIdea.code_id.is_not(None),
                           Response.processing_state == "DONE", Response.scoring_status != "EXCLUDED")).all()
                 if (not only_idea_id or i.id == only_idea_id) and (not i.embedding or i.embedding_model != model)]
        if only_idea_id:
            codes = [code for code in codes if code["id"] in {idea["code_id"] for idea in ideas}]
        if centroids_only:
            ideas = []
    summary = {"applied": False, "target_model": model, "active_codes": len(codes), "ideas_to_convert": len(ideas),
               "codes_updated": 0, "ideas_updated": 0, "centroids_updated": 0, "skipped_changed": 0}
    if not apply:
        return summary
    with factory() as db:
        frozen_before = {row["id"]: _row_digest(dict(row)) for row in db.execute(
            select(Response.__table__).where(Response.scoring_status == "FINAL")).mappings()}
    if backup_path is None:
        raise ValueError("Cần backup mới trước khi ghi cache vector.")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with backup_path.open("x", encoding="utf-8") as handle:
        # Chỉ giữ cache cũ để hoàn tác; không sao chép câu trả lời vào backup.
        json.dump({"target_model": model, "frozen_digest_policy": "ALL_COLUMNS_EXCEPT_LIVE_MAPPING_V1",
                   "frozen_response_hashes": frozen_before,
                   "codes": [{k: c[k] for k in ("id", *_CODE_CACHE_FIELDS)} for c in codes],
                   "ideas": [{k: i[k] for k in ("id", "embedding", "embedding_model")} for i in ideas]}, handle)
    for offset in range(0, 0 if only_idea_id or centroids_only else len(codes), 16):
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
        vectors = embed_texts([response_embedding_text(i["original"], i["item_name"]) for i in batch], client)
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
            criteria = [ItemCode.item_id == item.id]
            criteria.extend([ItemCode.maturity_status == "ACTIVE", ItemCode.validation_status == "ACCEPTED"]
                            if centroids_only else [ItemCode.centroid_dirty.is_(True)])
            for code in db.scalars(select(ItemCode).where(*criteria)).all():
                if only_idea_id and code.id not in {idea["code_id"] for idea in ideas}:
                    continue
                members = db.execute(select(ResponseIdea.embedding, ResponseIdea.embedding_model)
                    .join(Response, Response.id == ResponseIdea.response_id)
                    .where(ResponseIdea.code_id == code.id, ResponseIdea.mapping_status == "VALID", Response.scoring_status != "EXCLUDED")).all()
                rebuild_confirmed_members(code, [(v or [], m or "") for v, m in members],
                                          drift_cosine_floor=settings.centroid_drift_cosine_floor, expected_model=model)
                code.centroid_dirty = False
                summary["centroids_updated"] += 1
        db.commit()
    with factory() as db:
        frozen_after = {row["id"]: _row_digest(dict(row)) for row in db.execute(
            select(Response.__table__).where(Response.id.in_(frozen_before))).mappings()}
    if frozen_after != frozen_before:
        raise RuntimeError("Bản ghi FINAL đã thay đổi trong lúc chuyển cache; cần đối chiếu tiến trình ghi khác.")
    return {**summary, "applied": True, "frozen_responses_checked": len(frozen_before), "final_unchanged": True}


def _row_digest(row):
    """Giữ mọi cột và snapshot FINAL; cache mapping hiện hành có thể đổi khi gộp code nền."""
    frozen = {key: value for key, value in row.items() if key != "mapping"}
    return hashlib.sha256(json.dumps(frozen, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--only-idea-id", help="Chỉ gửi một câu gốc để hoàn tất cache; không gọi lại embedding code.")
    parser.add_argument("--centroids-only", action="store_true", help="Chỉ dựng tâm từ cache hiện có, không gọi API.")
    args = parser.parse_args()
    if args.apply and args.backup is None:
        parser.error("--apply cần --backup trỏ đến file mới.")
    # Chế độ thống kê không tạo client, không gửi dữ liệu ra ngoài.
    client = embedding_client() if args.apply and not args.centroids_only else None
    result = rebuild_vectors(client=client, apply=args.apply, backup_path=args.backup,
                             only_idea_id=args.only_idea_id, centroids_only=args.centroids_only)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

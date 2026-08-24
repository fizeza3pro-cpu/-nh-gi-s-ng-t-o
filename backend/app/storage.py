"""Lớp truy cập dữ liệu (data access layer).

Trước đây đọc/ghi file JSON trực tiếp trong thư mục data/.
Giờ chuyển sang đọc/ghi qua PostgreSQL (SQLAlchemy Session).

Tên hàm được giữ giống bản cũ để app/main.py thay đổi ít nhất có thể,
chỉ cần truyền thêm tham số `db: Session`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Item as ItemModel
from app.models.models import Response as ResponseModel
from app.schemas.schemas import Item


def load_items(db: Session) -> dict[str, Item]:
    """Trả về toàn bộ đồ vật trong bảng items, dạng dict giống bản cũ."""
    rows = db.scalars(select(ItemModel)).all()
    return {
        row.id: Item(id=row.id, name=row.name, description=row.description, codes=row.codes)
        for row in rows
    }


def new_response_id() -> str:
    return str(uuid.uuid4())


def save_response(db: Session, response_id: str, payload: dict, user_id: str | None = None) -> None:
    """Lưu 1 lượt làm bài. payload có cấu trúc giống bản JSON cũ
    (response_id, created_at, item, raw_input, mapping, scoring, ...meta).
    """
    scoring = payload.get("scoring", {})
    row = ResponseModel(
        id=response_id,
        user_id=user_id,
        item_id=payload["item"]["id"],
        raw_input=payload["raw_input"],
        mapping=payload["mapping"],
        scoring=scoring,
        mapping_meta=payload.get("mapping_meta", {}),
        scoring_meta=payload.get("scoring_meta", {}),
        fluency=scoring.get("fluency", 0),
        flexibility=scoring.get("flexibility", 0),
        originality=scoring.get("originality", 0),
        elaboration=scoring.get("elaboration", 0),
    )
    db.add(row)
    db.commit()


def _row_to_dict(row: ResponseModel) -> dict:
    return {
        "response_id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "item": {
            "id": row.item.id,
            "name": row.item.name,
            "description": row.item.description,
            "codes": row.item.codes,
        },
        "raw_input": row.raw_input,
        "mapping": row.mapping,
        "scoring": row.scoring,
        "mapping_meta": row.mapping_meta,
        "scoring_meta": row.scoring_meta,
    }


def load_response(db: Session, response_id: str) -> dict | None:
    row = db.get(ResponseModel, response_id)
    if row is None:
        return None
    return _row_to_dict(row)


def list_responses(db: Session, user_id: str | None = None) -> list[dict]:
    """Tóm tắt các response, mới nhất trước.

    user_id=None -> trả về TẤT CẢ (dùng cho admin).
    user_id="xxx" -> chỉ trả về của người đó (dùng cho user thường).
    Việc kiểm tra ai được gọi kiểu nào sẽ nằm ở lớp route (bước thêm auth).
    """
    stmt = select(ResponseModel).order_by(ResponseModel.created_at.desc())
    if user_id is not None:
        stmt = stmt.where(ResponseModel.user_id == user_id)
    rows = db.scalars(stmt).all()
    return [
        {
            "response_id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "item_id": row.item_id,
            "item_name": row.item.name if row.item else "",
            "fluency": row.fluency,
            "flexibility": row.flexibility,
            "originality": row.originality,
            "elaboration": row.elaboration,
        }
        for row in rows
    ]

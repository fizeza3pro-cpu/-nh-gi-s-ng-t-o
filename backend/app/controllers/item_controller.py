"""Nghiệp vụ đọc danh sách đồ vật (item) dùng cho bài test AUT."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Item as ItemModel
from app.schemas.schemas import Item


def _to_schema(row: ItemModel) -> Item:
    return Item(id=row.id, name=row.name, description=row.description, codes=row.codes)


def get_all_items(db: Session) -> list[Item]:
    rows = db.scalars(select(ItemModel)).all()
    return [_to_schema(r) for r in rows]


def get_item_by_id(db: Session, item_id: str) -> Item | None:
    row = db.get(ItemModel, item_id)
    if row is None:
        return None
    return _to_schema(row)
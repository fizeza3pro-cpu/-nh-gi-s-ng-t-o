from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.controllers import item_controller
from app.core.deps import get_current_user
from app.db import get_db
from app.schemas.schemas import Item

# dependencies=[Depends(get_current_user)] -> yêu cầu đăng nhập cho MỌI route
# trong router này, không cần khai báo current_user riêng ở từng hàm.
router = APIRouter(prefix="/api/items", tags=["items"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[Item])
def list_items(db: Session = Depends(get_db)) -> list[Item]:
    return item_controller.get_all_items(db)


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: str, db: Session = Depends(get_db)) -> Item:
    item = item_controller.get_item_by_id(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    return item
"""
Đọc/ghi tần suất Code tích lũy theo item_id, dùng để tính Originality
bằng công thức (không qua LLM). Dùng chung 1 Session với request hiện
tại — KHÔNG tự commit() bên trong (xem ghi chú cuối file).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ItemCodeCount, ItemStat
from app.schemas.schemas import ItemCodeStats


class DBCodeStatsStore:
    def __init__(self, session: Session):
        self.session = session

    def record_and_get_stats(self, item_id: str, codes_in_response: list[str]) -> ItemCodeStats:
        """Cộng dồn 1 response mới. SELECT ... FOR UPDATE khóa đúng các
        dòng liên quan, tránh race condition khi 2 user submit cùng lúc."""
        stat = self.session.execute(
            select(ItemStat).where(ItemStat.item_id == item_id).with_for_update()
        ).scalar_one_or_none()
        if stat is None:
            stat = ItemStat(item_id=item_id, total_valid_responses=0)
            self.session.add(stat)
            self.session.flush()

        stat.total_valid_responses += len(codes_in_response)

        for code in codes_in_response:
            row = self.session.execute(
                select(ItemCodeCount)
                .where(ItemCodeCount.item_id == item_id, ItemCodeCount.code == code)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                row = ItemCodeCount(item_id=item_id, code=code, count=0)
                self.session.add(row)
            row.count += 1

        self.session.flush()
        return self._read_stats(item_id, stat)

    def peek_stats(self, item_id: str) -> ItemCodeStats:
        stat = self.session.execute(
            select(ItemStat).where(ItemStat.item_id == item_id)
        ).scalar_one_or_none()
        return self._read_stats(item_id, stat)

    def seed_stats(self, item_id: str, code_counts: dict[str, int], norm_version: str) -> ItemCodeStats:
        """Ghi đè hoàn toàn — CHỈ dùng khi nạp pilot norms lúc CHƯA có
        user thật submit cho item_id đó."""
        self.session.execute(
            ItemCodeCount.__table__.delete().where(ItemCodeCount.item_id == item_id)
        )
        for code, count in code_counts.items():
            self.session.add(ItemCodeCount(item_id=item_id, code=code, count=count))

        stat = self.session.execute(
            select(ItemStat).where(ItemStat.item_id == item_id)
        ).scalar_one_or_none()
        total = sum(code_counts.values())
        if stat is None:
            stat = ItemStat(item_id=item_id, total_valid_responses=total, norm_version=norm_version)
            self.session.add(stat)
        else:
            stat.total_valid_responses = total
            stat.norm_version = norm_version

        self.session.flush()
        return self._read_stats(item_id, stat)

    def get_norm_version(self, item_id: str) -> str:
        stat = self.session.execute(
            select(ItemStat).where(ItemStat.item_id == item_id)
        ).scalar_one_or_none()
        return stat.norm_version if stat else "unseeded"

    def _read_stats(self, item_id: str, stat: "ItemStat | None") -> ItemCodeStats:
        rows = self.session.execute(
            select(ItemCodeCount).where(ItemCodeCount.item_id == item_id)
        ).scalars().all()
        return ItemCodeStats(
            item_id=item_id,
            total_valid_responses=stat.total_valid_responses if stat else 0,
            code_counts={r.code: r.count for r in rows},
        )


# LƯU Ý: các hàm trên chỉ flush(), KHÔNG tự commit(). response_controller.py
# gọi db.commit() SAU KHI toàn bộ pipeline (mapping + compute_scores +
# elaboration LLM + lưu Response) chạy xong không lỗi — để tần suất
# code_stats và bản ghi Response luôn nhất quán trong CÙNG 1 transaction.
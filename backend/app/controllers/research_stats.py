"""Truy vấn điểm dùng chung để dashboard và báo cáo thống nhất mẫu và trọng số."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Item, Participant, Response, ResponseScoringStatus

DIMENSIONS = ("originality", "flexibility", "fluency", "elaboration")


def participant_score_rows(db: Session, *, data_source: str, item_ids: list[str] | None = None):
    """Mỗi người đóng góp trung bình các lượt FINAL đã đồng bộ trong phạm vi chọn."""
    scope = [
        Response.data_source == data_source,
        Response.processing_state == "DONE",
        Response.scoring_status == ResponseScoringStatus.FINAL,
        Participant.ai_usage_group.in_(("LOW", "HIGH")),
    ]
    if item_ids is not None:
        scope.append(Response.item_id.in_(item_ids))
    return db.execute(
        select(Participant.ai_usage_group, Response.participant_id,
               *[func.avg(getattr(Response, dimension)) for dimension in DIMENSIONS],
               func.count(Response.id))
        .join(Participant, Participant.id == Response.participant_id)
        .join(Item, Item.id == Response.item_id)
        .where(*scope).group_by(Participant.ai_usage_group, Response.participant_id)
    ).all()

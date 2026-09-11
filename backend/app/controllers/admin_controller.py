"""Nghiệp vụ dành riêng cho admin: thống kê tổng quan, danh sách user kèm
số lượt submit, và lịch sử chi tiết của 1 user cụ thể.

Tất cả hàm ở đây GIẢ ĐỊNH người gọi đã qua require_admin (route lo việc
đó) — không tự kiểm tra quyền lại ở đây.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Item as ItemModel
from app.models.models import Response as ResponseModel
from app.models.models import User as UserModel
from app.schemas.schemas import (
    AdminDailyStat,
    AdminDashboardStats,
    AdminItemBreakdown,
    AdminRecentResponse,
    AdminTopUserByDimension,
    AdminTopUserByTotal,
    AdminTopUsersByDimension,
    AdminUserDetail,
    AdminUserSummary,
    ResponseSummary,
    UserOut,
)

TOP_N = 5


def _to_summary(row: ResponseModel) -> ResponseSummary:
    return ResponseSummary(
        response_id=row.id,
        created_at=row.created_at.isoformat() if row.created_at else "",
        item_id=row.item_id,
        item_name=row.item.name if row.item else "",
        fluency=row.fluency,
        flexibility=row.flexibility,
        originality=row.originality,
        elaboration=row.elaboration,
    )


def _to_recent(row: ResponseModel) -> AdminRecentResponse:
    return AdminRecentResponse(
        response_id=row.id,
        created_at=row.created_at.isoformat() if row.created_at else "",
        username=row.user.username if row.user else "(đã xóa)",
        item_id=row.item_id,
        item_name=row.item.name if row.item else "",
        fluency=row.fluency,
        flexibility=row.flexibility,
        originality=row.originality,
        elaboration=row.elaboration,
    )


def _top_users_by_total(db: Session) -> list[AdminTopUserByTotal]:
    """Top N user theo TỔNG điểm cộng dồn (fluency+flexibility+originality+
    elaboration) trên TẤT CẢ lượt submit của họ — số càng lớn vừa do điểm
    cao vừa do submit nhiều lần, đúng ý nghĩa "điểm tổng" (không phải điểm
    trung bình mỗi lượt)."""
    total_expr = (
        ResponseModel.fluency
        + ResponseModel.flexibility
        + ResponseModel.originality
        + ResponseModel.elaboration
    )
    rows = db.execute(
        select(
            UserModel.id,
            UserModel.username,
            UserModel.full_name,
            func.sum(total_expr),
            func.count(ResponseModel.id),
            func.max(ResponseModel.created_at),
        )
        .join(ResponseModel, ResponseModel.user_id == UserModel.id)
        .group_by(UserModel.id)
        .order_by(func.sum(total_expr).desc())
        .limit(TOP_N)
    ).all()

    return [
        AdminTopUserByTotal(
            user_id=user_id,
            username=username,
            full_name=full_name,
            total_score=int(total or 0),
            submit_count=count,
            last_submitted_at=last.isoformat() if last else "",
        )
        for user_id, username, full_name, total, count, last in rows
    ]


def _top_by_dimension(db: Session, column) -> list[AdminTopUserByDimension]:
    rows = db.execute(
        select(
            UserModel.id,
            UserModel.username,
            UserModel.full_name,
            func.avg(column),
        )
        .join(ResponseModel, ResponseModel.user_id == UserModel.id)
        .group_by(UserModel.id)
        .order_by(func.avg(column).desc())
        .limit(TOP_N)
    ).all()
    return [
        AdminTopUserByDimension(
            user_id=user_id, username=username, full_name=full_name,
            avg_value=round(avg_v or 0, 2),
        )
        for user_id, username, full_name, avg_v in rows
    ]


def _top_users_by_dimension(db: Session) -> AdminTopUsersByDimension:
    """Top N user theo điểm TRUNG BÌNH mỗi chỉ số — dùng trung bình (không
    phải tổng) để không thiên vị user submit nhiều lần trong bảng xếp hạng
    theo từng kỹ năng riêng lẻ."""
    return AdminTopUsersByDimension(
        fluency=_top_by_dimension(db, ResponseModel.fluency),
        flexibility=_top_by_dimension(db, ResponseModel.flexibility),
        originality=_top_by_dimension(db, ResponseModel.originality),
        elaboration=_top_by_dimension(db, ResponseModel.elaboration),
    )


def get_dashboard_stats(db: Session) -> AdminDashboardStats:
    total_users = db.scalar(select(func.count()).select_from(UserModel)) or 0
    total_responses = db.scalar(select(func.count()).select_from(ResponseModel)) or 0

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    responses_last_7_days = (
        db.scalar(
            select(func.count())
            .select_from(ResponseModel)
            .where(ResponseModel.created_at >= week_ago)
        )
        or 0
    )

    two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
    responses_previous_7_days = (
        db.scalar(
            select(func.count())
            .select_from(ResponseModel)
            .where(
                ResponseModel.created_at >= two_weeks_ago,
                ResponseModel.created_at < week_ago,
            )
        )
        or 0
    )

    # 14 ngày gần nhất, kể cả ngày không có lượt nào (count=0) — để đường
    # biểu đồ không bị "nhảy cóc" giữa các ngày có dữ liệu.
    fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=13)
    raw_rows = db.scalars(
        select(ResponseModel).where(ResponseModel.created_at >= fourteen_days_ago)
    ).all()
    buckets: dict[str, list[int]] = {}
    for r in raw_rows:
        day_key = r.created_at.date().isoformat()
        total = r.fluency + r.flexibility + r.originality + r.elaboration
        buckets.setdefault(day_key, []).append(total)

    daily_stats: list[AdminDailyStat] = []
    today = datetime.now(timezone.utc).date()
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        scores = buckets.get(key, [])
        daily_stats.append(
            AdminDailyStat(
                date=key,
                count=len(scores),
                avg_score=round(sum(scores) / len(scores) / 4, 2) if scores else 0,
            )
        )

    # Thống kê theo từng item: số lượt + điểm trung bình 4 chiều.
    by_item_rows = db.execute(
        select(
            ResponseModel.item_id,
            ItemModel.name,
            func.count(ResponseModel.id),
            func.avg(ResponseModel.fluency),
            func.avg(ResponseModel.flexibility),
            func.avg(ResponseModel.originality),
            func.avg(ResponseModel.elaboration),
        )
        .join(ItemModel, ItemModel.id == ResponseModel.item_id)
        .group_by(ResponseModel.item_id, ItemModel.name)
        .order_by(func.count(ResponseModel.id).desc())
    ).all()

    by_item = [
        AdminItemBreakdown(
            item_id=item_id,
            item_name=item_name,
            response_count=count,
            avg_fluency=round(avg_f or 0, 2),
            avg_flexibility=round(avg_fx or 0, 2),
            avg_originality=round(avg_o or 0, 2),
            avg_elaboration=round(avg_e or 0, 2),
        )
        for item_id, item_name, count, avg_f, avg_fx, avg_o, avg_e in by_item_rows
    ]

    recent_rows = db.scalars(
        select(ResponseModel).order_by(ResponseModel.created_at.desc()).limit(10)
    ).all()
    recent_responses = [_to_recent(r) for r in recent_rows]

    return AdminDashboardStats(
        total_users=total_users,
        total_responses=total_responses,
        responses_last_7_days=responses_last_7_days,
        responses_previous_7_days=responses_previous_7_days,
        daily_stats=daily_stats,
        by_item=by_item,
        recent_responses=recent_responses,
        top_users_by_total=_top_users_by_total(db),
        top_users_by_dimension=_top_users_by_dimension(db),
    )


def list_users_with_stats(db: Session) -> list[AdminUserSummary]:
    rows = db.execute(
        select(
            UserModel,
            func.count(ResponseModel.id),
            func.max(ResponseModel.created_at),
        )
        .outerjoin(ResponseModel, ResponseModel.user_id == UserModel.id)
        .group_by(UserModel.id)
        .order_by(UserModel.created_at.desc())
    ).all()

    return [
        AdminUserSummary(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            created_at=user.created_at,
            response_count=count,
            last_submitted_at=last_submitted.isoformat() if last_submitted else None,
        )
        for user, count, last_submitted in rows
    ]


def get_user_detail(db: Session, user_id: str) -> AdminUserDetail:
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")

    rows = db.scalars(
        select(ResponseModel)
        .where(ResponseModel.user_id == user_id)
        .order_by(ResponseModel.created_at.desc())
    ).all()

    return AdminUserDetail(
        user=UserOut.model_validate(user),
        responses=[_to_summary(r) for r in rows],
    )
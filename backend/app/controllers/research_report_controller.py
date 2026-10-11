"""Báo cáo mô tả từ dữ liệu đã lưu, không thay mapping hoặc tính lại điểm."""

import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, stdev

from fastapi import HTTPException
from scipy.stats import ttest_ind
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.controllers.research_stats import DIMENSIONS, participant_score_rows
from app.models.models import (
    CodeMaturityStatus, CodeValidationStatus, Item, ItemCode, Participant,
    Response, ResponseIdea, ResponseScoringStatus,
)
from app.schemas.schemas import (
    AdminResearchReport, Item as ItemSchema, ReportIdeaCounts, ReportObjectCodes,
    ReportObjectGroup, ReportSampleCounts, ReportScoreDimension, ReportScoreEstimate,
)

DIMENSION_LABELS = {
    "originality": "Độc đáo", "flexibility": "Linh hoạt",
    "fluency": "Trôi chảy", "elaboration": "Chi tiết",
}


def _estimate(values: list[float]) -> ReportScoreEstimate:
    """Sai số chuẩn dùng độ lệch chuẩn mẫu; một người chưa đủ ước lượng sai số."""
    if not values:
        return ReportScoreEstimate()
    sd = stdev(values) if len(values) > 1 else None
    return ReportScoreEstimate(
        n=len(values), mean=mean(values), sd=sd,
        sem=sd / math.sqrt(len(values)) if sd is not None else None,
    )


def _compare(dimension: str, low: list[float], high: list[float]) -> ReportScoreDimension:
    """Welch hai phía trên các quan sát độc lập ở cấp người tham gia."""
    # PostgreSQL trả AVG(Integer) dưới dạng Decimal; SciPy cần số thực chuẩn.
    low, high = [float(value) for value in low], [float(value) for value in high]
    result = ReportScoreDimension(dimension=dimension, low=_estimate(low), high=_estimate(high))
    if low and high:
        result.difference = mean(high) - mean(low)
    if min(len(low), len(high)) < 2:
        result.test_note = "Cần ít nhất 2 người có điểm ở mỗi nhóm để tính p."
    elif result.low.sd == 0 and result.high.sd == 0:
        result.test_note = "Cả hai nhóm không có biến thiên; không ước lượng p."
    else:
        p_value = float(ttest_ind(low, high, equal_var=False).pvalue)
        if math.isfinite(p_value):
            result.p_value = p_value
        else:
            result.test_note = "Không đủ thông tin để ước lượng p."
    return result


def _adjust_holm(dimensions: list[ReportScoreDimension]) -> None:
    """Hiệu chỉnh họ bốn phép so sánh, kể cả khi một phép chưa tính được."""
    ordered = sorted((row for row in dimensions if row.p_value is not None), key=lambda row: row.p_value)
    previous = 0.0
    for index, row in enumerate(ordered):
        previous = min(1.0, max(previous, (len(dimensions) - index) * row.p_value))
        row.p_value_holm = previous


def get_research_report(
    db: Session, *, data_source: str | None = None, item_id: str | None = None,
    item_ids: list[str] | None = None,
) -> AdminResearchReport:
    """Đếm bằng ORM hiện hành; tách nguồn thật, lượt bị loại và điểm đang lỗi thời."""
    source = data_source or settings.survey_data_source
    all_items = db.scalars(select(Item).order_by(Item.name, Item.id)).all()
    selected_ids = list(dict.fromkeys([*(item_ids or []), *([item_id] if item_id is not None else [])]))
    if set(selected_ids) - {item.id for item in all_items}:
        raise HTTPException(status_code=404, detail="Không tìm thấy đồ vật.")
    items = [item for item in all_items if not selected_ids or item.id in selected_ids]
    scope = [Response.data_source == source]
    item_scope = [Response.item_id.in_(selected_ids)] if selected_ids else []
    scope.extend(item_scope)
    analyzed = [*scope, Response.processing_state == "DONE",
                Response.scoring_status != ResponseScoringStatus.EXCLUDED]
    group_expr = func.coalesce(Participant.ai_usage_group, "UNKNOWN")
    sample = ReportSampleCounts()
    registered = dict(db.execute(
        select(Participant.ai_usage_group, func.count(Participant.id))
        .where(Participant.ai_usage_group.in_(("LOW", "HIGH"))).group_by(Participant.ai_usage_group)
    ).all())
    submitted = dict(db.execute(
        select(Participant.ai_usage_group, func.count(func.distinct(Response.participant_id)))
        .join(Response, Response.participant_id == Participant.id)
        .where(*scope, Participant.ai_usage_group.in_(("LOW", "HIGH"))).group_by(Participant.ai_usage_group)
    ).all())
    for group, suffix in (("LOW", "low"), ("HIGH", "high")):
        setattr(sample, f"registered_participants_{suffix}", registered.get(group, 0))
        setattr(sample, f"submitted_participants_{suffix}", submitted.get(group, 0))
    status_rows = db.execute(
        select(Response.processing_state, Response.scoring_status, group_expr, func.count(Response.id))
        .join(Participant, Response.participant_id == Participant.id)
        .where(*scope).group_by(Response.processing_state, Response.scoring_status, group_expr)
    ).all()
    for state, status, group, count in status_rows:
        sample.submitted_responses += count
        if status == ResponseScoringStatus.EXCLUDED:
            sample.excluded_responses += count
        elif state == "FAILED":
            sample.failed_responses += count
        elif state != "DONE":
            sample.unfinished_responses += count
        else:
            sample.analyzed_responses += count
            if group not in ("LOW", "HIGH"):
                sample.ungrouped_responses += count
    sample.other_source_responses = db.scalar(
        select(func.count(Response.id)).where(*item_scope, Response.data_source != source)
    ) or 0

    # Luôn có hai dòng mỗi đồ vật; nhóm thiếu thông tin chỉ xuất hiện khi có bài.
    buckets = {
        (item.id, group): ReportObjectGroup(item_id=item.id, item_name=item.name, group=group)
        for item in items for group in ("LOW", "HIGH")
    }
    names = {item.id: item.name for item in items}
    response_rows = db.execute(
        select(Response.item_id, group_expr, func.count(Response.id), func.count(func.distinct(Response.participant_id)))
        .join(Participant, Participant.id == Response.participant_id)
        .where(*analyzed).group_by(Response.item_id, group_expr)
    ).all()
    for key, group, count, participants in response_rows:
        group = group if group in ("LOW", "HIGH") else "UNKNOWN"
        bucket = buckets.setdefault((key, group), ReportObjectGroup(item_id=key, item_name=names[key], group=group))
        bucket.response_count += count
        bucket.participant_count += participants

    code_sets = defaultdict(set)
    idea_rows = db.execute(
        select(Response.item_id, group_expr, ResponseIdea.mapping_status, ResponseIdea.code_id,
               ItemCode.validation_status, ItemCode.maturity_status, func.count(ResponseIdea.id))
        .join(Response, Response.id == ResponseIdea.response_id)
        .join(Participant, Participant.id == Response.participant_id)
        .outerjoin(ItemCode, ItemCode.id == ResponseIdea.code_id)
        .where(*analyzed)
        .group_by(Response.item_id, group_expr, ResponseIdea.mapping_status, ResponseIdea.code_id,
                  ItemCode.validation_status, ItemCode.maturity_status)
    ).all()
    for key, group, status, code_id, validation, maturity, count in idea_rows:
        group = group if group in ("LOW", "HIGH") else "UNKNOWN"
        bucket = buckets[(key, group)]
        bucket.total_ideas += count
        field = {"VALID": "valid_ideas", "INVALID": "invalid_ideas", "DUPLICATE": "duplicate_ideas"}.get(status, "unclassified_ideas")
        setattr(bucket, field, getattr(bucket, field) + count)
        accepted = (code_id is not None and validation == CodeValidationStatus.ACCEPTED
                    and maturity == CodeMaturityStatus.ACTIVE)
        if status == "VALID":
            if accepted:
                code_sets[(key, group)].add(code_id)
            else:
                bucket.pending_code_ideas += count
    for key, bucket in buckets.items():
        bucket.used_code_count = len(code_sets[key])
    object_codes = []
    for item in items:
        low, high, unknown = (code_sets[(item.id, group)] for group in ("LOW", "HIGH", "UNKNOWN"))
        object_codes.append(ReportObjectCodes(
            item_id=item.id, item_name=item.name, low_code_count=len(low), high_code_count=len(high),
            shared_code_count=len(low & high), total_code_count=len(low | high | unknown),
        ))

    # Dùng cùng truy vấn với dashboard: trung bình lượt của từng người, rồi trung bình nhóm.
    score_rows = participant_score_rows(db, data_source=source, item_ids=selected_ids or None)
    samples = {group: {dimension: [] for dimension in DIMENSIONS} for group in ("LOW", "HIGH")}
    for group, _participant, *values in score_rows:
        sample.final_scored_responses += values[-1]
        for index, dimension in enumerate(DIMENSIONS):
            samples[group][dimension].append(float(values[index]))
    sample.score_participants_low = len(samples["LOW"]["fluency"])
    sample.score_participants_high = len(samples["HIGH"]["fluency"])
    # Điểm FINAL thuộc mốc chấm của từng bài, không lỗi thời khi có mẫu mới.
    sample.stale_score_responses = 0
    dimensions = [_compare(dimension, samples["LOW"][dimension], samples["HIGH"][dimension]) for dimension in DIMENSIONS]
    _adjust_holm(dimensions)
    totals = ReportIdeaCounts(
        participant_count=db.scalar(select(func.count(func.distinct(Response.participant_id))).where(*analyzed)) or 0,
        response_count=sample.analyzed_responses,
        **{field: sum(getattr(bucket, field) for bucket in buckets.values()) for field in (
            "total_ideas", "valid_ideas", "invalid_ideas", "duplicate_ideas", "unclassified_ideas", "pending_code_ideas",
        )},
        used_code_count=sum(row.total_code_count for row in object_codes),
    )
    summary = [
        f"Nguồn {source}: {totals.participant_count} người, {totals.response_count} lượt hoàn tất được tổng hợp.",
        f"Trong phạm vi được chọn, đã nộp bài: {sample.submitted_participants_low} người ít sử dụng AI và {sample.submitted_participants_high} người sử dụng nhiều AI. Toàn hệ thống có {sample.registered_participants_low} và {sample.registered_participants_high} hồ sơ tương ứng; hồ sơ chưa nộp hoặc chưa có điểm FINAL không tham gia biểu đồ điểm.",
        f"Có {totals.total_ideas} ý tưởng: {totals.valid_ideas} hợp lệ, {totals.invalid_ideas} không hợp lệ và {totals.duplicate_ideas} trùng lặp.",
        f"Biểu đồ điểm dùng {sample.final_scored_responses} lượt có điểm chính thức, từ {sample.score_participants_low} người ít sử dụng AI và {sample.score_participants_high} người sử dụng nhiều AI.",
    ]
    if totals.total_ideas:
        summary.insert(2, f"Tỷ lệ ý hợp lệ là {100 * totals.valid_ideas / totals.total_ideas:.2f}%; có {totals.pending_code_ideas} ý hợp lệ đang chờ mã và {totals.used_code_count} mã đã được sử dụng (đếm riêng theo đồ vật).")
    for row in dimensions:
        if row.difference is not None:
            summary.append(
                f"{DIMENSION_LABELS[row.dimension]}: nhóm sử dụng nhiều AI {'cao' if row.difference >= 0 else 'thấp'} hơn {abs(row.difference):.2f} điểm trung bình."
            )
    tested = [row for row in dimensions if row.p_value_holm is not None]
    significant = [DIMENSION_LABELS[row.dimension] for row in tested if row.p_value_holm < 0.05]
    if significant:
        summary.append(f"Khác biệt có ý nghĩa thống kê sau hiệu chỉnh Holm (p < 0,05): {', '.join(significant)}. Đây là liên hệ quan sát, không chứng minh tác động của AI.")
    elif tested:
        summary.append("Chưa ghi nhận khác biệt có ý nghĩa thống kê ở các tiêu chí kiểm định được sau hiệu chỉnh Holm (p ≥ 0,05). Kết quả này không chứng minh hai nhóm tương đương; cần đối chiếu cỡ mẫu và cơ cấu đồ vật.")
    else:
        summary.append("Chưa đủ dữ liệu có biến thiên ở cả hai nhóm để kiểm định khác biệt điểm.")
    return AdminResearchReport(
        generated_at=datetime.now(timezone.utc), data_source=source,
        item_id=selected_ids[0] if len(selected_ids) == 1 else None, item_ids=selected_ids,
        available_items=[ItemSchema(id=item.id, name=item.name, description=item.description) for item in all_items],
        sample=sample, totals=totals,
        object_groups=[buckets[(item.id, group)] for item in items for group in ("LOW", "HIGH", "UNKNOWN") if (item.id, group) in buckets],
        object_codes=object_codes, dimensions=dimensions, summary_vi=summary,
        methodology_vi=[
            "Phân nhóm theo mức sử dụng AI tự khai trong hồ sơ hiện tại: LOW = sử dụng ít AI; HIGH = sử dụng nhiều AI. Đây là so sánh quan sát giữa hai nhóm, không phải trước/sau can thiệp và không chứng minh quan hệ nhân quả.",
            "Bảng ý tưởng và mã dùng mọi lượt DONE không bị EXCLUDED của nguồn được chọn, kể cả lượt chưa có điểm. Không trộn dữ liệu SYNTHETIC hoặc nguồn khác. Nhóm chưa khai báo được thống kê riêng và không tham gia so sánh điểm.",
            "Tổng ý = hợp lệ + không hợp lệ + trùng lặp + chưa phân loại. Ý chờ mã là một phần của ý VALID chưa có mã ACCEPTED/ACTIVE. Số mã chỉ đếm mã khác nhau đã gán cho ý VALID; tổng mã là hợp của các nhóm, không cộng mã trùng giữa nhóm.",
            "Biểu đồ chỉ dùng điểm FINAL của lượt DONE trên đồ vật có điểm đã đồng bộ. Điểm là tổng điểm của một lượt theo rubric hiện hành; số 0 được giữ như một điểm thực. Điểm tạm thời, chưa chấm và điểm đang lỗi thời không được coi là 0.",
            "Đơn vị so sánh là người tham gia: lấy trung bình tất cả lượt FINAL đủ điều kiện của mỗi người trên các đồ vật được chọn, rồi lấy trung bình nhóm. Mỗi người có trọng số bằng nhau. Cách tính và mẫu điểm thống nhất với dashboard khi cùng nguồn và tất cả đồ vật. Cơ cấu đồ vật có thể khác giữa người/nhóm; dùng bộ lọc đồ vật để đối chiếu.",
            "Thanh sai số là ±1 SEM (độ lệch chuẩn mẫu chia căn bậc hai số người). Một người chưa đủ để ước lượng SEM. p thô dùng Welch t-test hai phía; p trên biểu đồ hiệu chỉnh Holm cho bốn tiêu chí. Không ước lượng p nếu mỗi nhóm chưa có ít nhất 2 người hoặc cả hai nhóm không có biến thiên.",
        ],
    )

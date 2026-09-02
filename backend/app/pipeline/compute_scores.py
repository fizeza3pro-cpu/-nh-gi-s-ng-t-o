"""
Tính Fluency, Flexibility, Originality bằng công thức xác định
(deterministic), KHÔNG dùng LLM — cho MỘT response vừa submit.

Nhận stats_store (DBCodeStatsStore) làm tham số thay vì import singleton
toàn cục — vì mỗi request có 1 Session/transaction riêng (FastAPI
Depends(get_db)), không thể dùng chung 1 store cho mọi request.
"""
from app.schemas.schemas import MappingResult, PerIdeaScore
from app.pipeline.code_stats_db import DBCodeStatsStore

MIN_SAMPLE_FOR_FORMULA = 30  # lưới an toàn nếu lỡ quên seed pilot cho item nào đó


def compute_response_scores(
    item_id: str, mapping: MappingResult, stats_store: DBCodeStatsStore
) -> tuple[int, int, list[str], list[PerIdeaScore], bool]:
    """Trả về (fluency, flexibility, flexibility_codes, per_idea_scores
    [chỉ originality điền sẵn, elaboration=1 placeholder chờ LLM ghi đè],
    sufficient_data).
    """
    valid_ideas = [i for i in mapping.ideas if i.is_valid]

    fluency = len(valid_ideas)
    flexibility_codes = sorted(set(i.code for i in valid_ideas if i.code))
    flexibility = len(flexibility_codes)

    if not valid_ideas:
        return fluency, flexibility, flexibility_codes, [], True

    codes_in_response = [i.code for i in valid_ideas if i.code]
    stats = stats_store.record_and_get_stats(item_id, codes_in_response)
    sufficient_data = stats.total_valid_responses >= MIN_SAMPLE_FOR_FORMULA

    def originality_of(code: str) -> int:
        freq_pct = (stats.code_counts.get(code, 0) / stats.total_valid_responses) * 100
        if freq_pct <= 1:
            return 2
        elif freq_pct <= 5:
            return 1
        return 0

    per_idea_scores = [
        PerIdeaScore(
            normalized=i.normalized,
            code=i.code,
            originality=originality_of(i.code) if i.code else 0,
            elaboration=1,  # placeholder hợp lệ (schema yêu cầu ge=1) —
                             # scoring.py sẽ GHI ĐÈ bằng kết quả LLM chấm thật
        )
        for i in valid_ideas
    ]

    return fluency, flexibility, flexibility_codes, per_idea_scores, sufficient_data
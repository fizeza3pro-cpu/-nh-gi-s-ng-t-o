"""Mô phỏng mapping và scoring cho dev/test, không gọi provider thật."""
from app.schemas.schemas import (Item, IdeaExtractionResult, ExtractedIdea, FunctionalSignature, CuratorResult, CuratorDecision, PerIdeaScore, ScoringResult)


def run_mapping(
    item: Item, raw: str, existing_codes: list[dict]
) -> tuple[IdeaExtractionResult, CuratorResult]:
    """Mock có cùng contract hai tầng để test không vô tình quay lại code tĩnh."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()][:10]
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original=line,
                normalized=line,
                status="VALID",
                object_used=item.name,
                line_index=index,
                functional_signature=FunctionalSignature(
                    goal=line,
                    object_role=f"Dùng {item.name} làm vật thể chính",
                    mechanism="Cơ chế mô phỏng ổn định",
                ),
            )
            for index, line in enumerate(lines)
        ]
    )
    by_name = {code["name"].strip().casefold(): code for code in existing_codes}
    decisions = []
    for index, line in enumerate(lines):
        existing = by_name.get(line.casefold())
        if existing:
            decisions.append(
                CuratorDecision(
                    idea_index=index,
                    decision="MATCH_EXISTING",
                    existing_code_id=existing["id"],
                    code_relation="SAME_CATEGORY",
                    functional_signature=extraction.ideas[index].functional_signature,
                    existing_code_evaluations=[
                        {
                            "code_id": existing["id"],
                            "relation": "SAME_CATEGORY",
                            "goal_match": True,
                            "role_match": True,
                            "mechanism_match": True,
                            "excluded_by": "",
                            "verdict": "MATCH",
                        }
                    ],
                    confidence=0.99,
                    reason="[MOCK] Khớp code đã có.",
                )
            )
        else:
            decisions.append(
                CuratorDecision(
                    idea_index=index,
                    decision="CREATE_NEW",
                    proposal_group=f"mock:{line.casefold()}",
                    code_name=line[:80],
                    code_description=f"[MOCK] Dùng {item.name}: {line[:120]}",
                    functional_signature=extraction.ideas[index].functional_signature,
                    inclusion_rules=[f"Dùng {item.name} theo chức năng {line[:80]}"],
                    exclusion_rules=["Không bao gồm mục đích hoặc cơ chế khác"],
                    positive_examples=[line],
                    scope_variants=[
                        f"[MOCK] Biến thể cách diễn đạt thứ nhất của: {line[:80]}",
                        f"[MOCK] Biến thể cách diễn đạt thứ hai của: {line[:80]}",
                    ],
                    policy_gates={
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    reviewed_by_challenger=True,
                    confidence=0.95,
                    reason="[MOCK] Công dụng hợp lệ chưa có trong codebook.",
                )
            )
    return extraction, CuratorResult(decisions=decisions)



def run_scoring(
    fluency: int,
    flexibility: int,
    flexibility_codes: list[str],
    per_idea: list[PerIdeaScore],
) -> tuple[ScoringResult, dict]:
    scored = [score.model_copy(update={"elaboration": 2, "note": "[MOCK]"}) for score in per_idea]
    return (
        ScoringResult(
            fluency=fluency,
            flexibility=flexibility,
            flexibility_codes=flexibility_codes,
            originality=sum(score.originality for score in scored),
            elaboration=sum(score.elaboration for score in scored),
            per_idea_scores=scored,
            summary_vi="[MOCK] Điểm được tính từ dữ liệu tại thời điểm nộp bài.",
        ),
        {"mock": True},
    )


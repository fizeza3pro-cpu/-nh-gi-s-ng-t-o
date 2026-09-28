"""Tầng chấm điểm: công thức cố định, LLM chỉ trích bằng chứng Elaboration."""
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata
# from google import genai
from openai import OpenAI
from app.config import settings
from app.pipeline.llm import aggregate_usage, chat_json, LLMJSONError
from app.schemas.schemas import Item, PerIdeaScore, ScoringResult


PROMPT_PATH = Path(__file__).parent / "prompts" / "scoring.txt"
_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")

_FACETS = ("target", "mechanism", "context", "goal")
_FACET_LABELS = {
    "target": "đối tượng/đích",
    "mechanism": "cách làm/cơ chế",
    "context": "bối cảnh/điều kiện",
    "goal": "mục đích/kết quả",
}
_WORD_RE = re.compile(r"[^\W\d_]+|\d+(?:[.,]\d+)?", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "ai", "bạn", "bằng", "bị", "các", "cái", "cho", "chiếc", "chúng",
        "có", "của", "dùng", "đang", "đã", "để", "đó", "được", "gì", "hoặc",
        "kia", "là", "làm", "mà", "một", "này", "những", "nó", "người", "ở",
        "sẽ", "sử", "ta", "tại", "thì", "thứ", "tôi", "trên", "trong", "từ",
        "và", "vào", "với",
    }
)


def build_prompt(item: Item, valid_ideas: list[dict]) -> str:
    return _TEMPLATE.format(
        item_name=item.name,
        valid_ideas_json=json.dumps(
            valid_ideas, ensure_ascii=False, separators=(",", ":")
        ),
    )


def _analyze_once(
    item: Item, valid_ideas: list[dict], client: OpenAI
) -> tuple[dict, dict]:
    prompt = build_prompt(item, valid_ideas)
    data, meta = chat_json(
        client,
        model=settings.active_llm_model,
        temperature=settings.scoring_temperature,
        prompt=prompt,
        provider=settings.llm_provider,
        reasoning_effort=settings.active_reasoning_effort,
        max_tokens=settings.max_tokens_for("scoring"),
        max_retries=settings.llm_max_retries,
        stage="scoring",
        include_raw_response=settings.store_raw_llm_response,
    )
    return data, meta


def _normalized_evidence(value: str) -> str:
    """Chuẩn hoá nhẹ để kiểm tra đoạn trích mà không cho phép diễn giải lại."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def _grounded_evidence(original: str, evidence: object) -> str:
    """Chỉ nhận bằng chứng có đoạn chữ thực sự xuất hiện trong câu gốc."""
    if not isinstance(evidence, str) or not evidence.strip():
        return ""
    normalized_original = _normalized_evidence(original)
    normalized_evidence = _normalized_evidence(evidence)
    if not normalized_evidence or normalized_evidence not in normalized_original:
        return ""
    return " ".join(evidence.split())


def count_meaningful_words(original: str, item_name: str) -> int:
    """Đếm token nội dung theo stoplist cố định để làm chỉ số đối chứng."""
    tokens = _WORD_RE.findall(unicodedata.normalize("NFKC", original).casefold())
    item_tokens = set(
        _WORD_RE.findall(unicodedata.normalize("NFKC", item_name).casefold())
    )
    excluded = _STOPWORDS | item_tokens
    return sum(token not in excluded for token in tokens)


def _aggregate_facets(
    originals: list[str], run_payloads: list[dict]
) -> list[dict[str, str]]:
    """Lấy đồng thuận đa lượt; backend tự xác thực mọi đoạn bằng chứng."""
    threshold = len(run_payloads) // 2 + 1
    aggregated: list[dict[str, str]] = []
    for idea_index, original in enumerate(originals):
        details: dict[str, str] = {}
        for facet_name in _FACETS:
            grounded: list[str] = []
            for payload in run_payloads:
                analyses = payload.get("elaboration_analysis", [])
                if not isinstance(analyses, list) or idea_index >= len(analyses):
                    continue
                analysis = analyses[idea_index]
                facets = analysis.get("facets", {}) if isinstance(analysis, dict) else {}
                facet = facets.get(facet_name, {}) if isinstance(facets, dict) else {}
                if not isinstance(facet, dict) or facet.get("present") is not True:
                    continue
                evidence = _grounded_evidence(original, facet.get("evidence"))
                if evidence:
                    grounded.append(evidence)
            if len(grounded) >= threshold:
                # Ưu tiên đoạn trích được lặp lại; nếu hoà thì giữ kết quả lượt đầu.
                counts = Counter(_normalized_evidence(value) for value in grounded)
                first_positions = {
                    value: next(
                        index for index, evidence in enumerate(grounded)
                        if _normalized_evidence(evidence) == value
                    )
                    for value in counts
                }
                selected_key = max(
                    counts, key=lambda value: (counts[value], -first_positions[value])
                )
                details[facet_name] = next(
                    evidence for evidence in grounded
                    if _normalized_evidence(evidence) == selected_key
                )
        aggregated.append(details)
    return aggregated


def _detail_note(details: dict[str, str], meaningful_word_count: int) -> str:
    if details:
        labels = ", ".join(
            f'{_FACET_LABELS[name]} ("{evidence}")'
            for name, evidence in details.items()
        )
        return f"Ghi nhận: {labels}. Từ nội dung đối chứng: {meaningful_word_count}."
    return (
        "Chỉ nêu công dụng, chưa có chi tiết bổ sung được dẫn chứng. "
        f"Từ nội dung đối chứng: {meaningful_word_count}."
    )


def _summary(per_idea_scores: list[PerIdeaScore]) -> str:
    """Tạo nhận xét từ điểm đã tính, không giao phần kết luận cho LLM."""
    count = len(per_idea_scores)
    average = sum(score.elaboration for score in per_idea_scores) / count
    developed = sum(score.elaboration >= 3 for score in per_idea_scores)
    facet_counts = Counter(
        facet
        for score in per_idea_scores
        for facet in score.elaboration_details
    )
    first = (
        f"Độ chi tiết trung bình {average:.2f}/5; "
        f"{developed}/{count} ý có từ hai loại chi tiết bổ sung trở lên."
    )
    if not facet_counts:
        return first + " Các ý hiện chủ yếu mới nêu tên công dụng."
    strongest = max(_FACETS, key=lambda facet: facet_counts[facet])
    weakest = min(_FACETS, key=lambda facet: facet_counts[facet])
    if facet_counts[strongest] == facet_counts[weakest]:
        return first + " Các loại chi tiết được sử dụng tương đối cân bằng."
    return (
        first
        + f" Chi tiết nổi bật nhất là {_FACET_LABELS[strongest]}; "
        + f"có thể bổ sung rõ hơn {_FACET_LABELS[weakest]}."
    )


def run_scoring(
    item: Item,
    fluency: int,
    flexibility: int,
    flexibility_codes: list[str],
    per_idea_originality: list[PerIdeaScore],
    client: OpenAI,
    runs: int | None = None,
) -> tuple[ScoringResult, dict]:
    """Nhận ba chỉ số đã tính từ snapshot động, rồi chấm Elaboration."""
    if not per_idea_originality:
        return (
            ScoringResult(
                fluency=fluency, flexibility=0, flexibility_codes=[],
                originality=0, elaboration=0, per_idea_scores=[],
                summary_vi=(
                    "Các ý tưởng hợp lệ đã được tính Fluency, nhưng chưa có ý nào "
                    "đủ căn cứ để gán code và tính các chỉ số còn lại."
                    if fluency
                    else "Không có ý tưởng hợp lệ nào để chấm điểm. Hãy thử nghĩ thêm nhiều cách dùng khác nhau cho đồ vật."
                ),
            ),
            {
                "provider": settings.llm_provider,
                "model": settings.active_llm_model,
                "skipped": True,
            },
        )

    n_runs = max(1, runs if runs is not None else settings.scoring_runs)
    valid_ideas_payload = [
        {"idea_id": p.idea_id, "original": p.original, "normalized": p.normalized, "code": p.code}
        for p in per_idea_originality
    ]

    run_payloads, metas = [], []
    for _ in range(n_runs):
        data, meta = _analyze_once(item, valid_ideas_payload, client)
        if all(idea.idea_id for idea in per_idea_originality):
            rows = data.get("elaboration_analysis", [])
            by_id = {row.get("idea_id"): row for row in rows if isinstance(row, dict)}
            expected = {idea.idea_id for idea in per_idea_originality}
            if len(rows) != len(expected) or set(by_id) != expected:
                raise LLMJSONError("Elaboration thiếu, trùng hoặc sai idea_id.", metadata=meta)
            if any(by_id[idea.idea_id].get("original") != idea.original for idea in per_idea_originality):
                raise LLMJSONError("Elaboration bị lệch câu nguồn.", metadata=meta)
            data["elaboration_analysis"] = [by_id[idea.idea_id] for idea in per_idea_originality]
        run_payloads.append(data)
        metas.append(meta)

    originals = [score.original for score in per_idea_originality]
    elaboration_details = _aggregate_facets(originals, run_payloads)

    per_idea_scores = []
    for orig, details in zip(per_idea_originality, elaboration_details):
        meaningful_word_count = count_meaningful_words(orig.original, item.name)
        per_idea_scores.append(
            PerIdeaScore(
                idea_id=orig.idea_id,
                original=orig.original,
                normalized=orig.normalized,
                code=orig.code,
                originality=orig.originality,
                elaboration=1 + len(details),
                meaningful_word_count=meaningful_word_count,
                elaboration_details=details,
                note=_detail_note(details, meaningful_word_count),
            )
        )

    result = ScoringResult(
        fluency=fluency,
        flexibility=flexibility,
        flexibility_codes=flexibility_codes,
        originality=sum(p.originality for p in per_idea_scores),
        elaboration=sum(p.elaboration for p in per_idea_scores),
        per_idea_scores=per_idea_scores,
        summary_vi=_summary(per_idea_scores),
    )
    meta = {
        "provider": settings.llm_provider,
        "model": settings.active_llm_model,
        "temperature": settings.scoring_temperature,
        "runs": n_runs,
        "response_ids": [m.get("response_id") for m in metas],
        "llm_runs": metas,
        "usage": aggregate_usage(metas),
        "latency_ms": round(sum(float(m.get("latency_ms") or 0) for m in metas), 2),
        "elaboration_method": {
            "score_formula": "1 + target + mechanism + context + goal",
            "facet_source": "LLM evidence extraction with verbatim grounding",
            "aggregation": "majority vote across runs",
            "meaningful_word_count": "deterministic Vietnamese stoplist baseline",
        },
        "note": "Mọi chỉ số đều do công thức tính; LLM chỉ trích đoạn bằng chứng Elaboration.",
    }
    return result, meta

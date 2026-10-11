"""Nhận xét định tính sau chấm điểm, có đối chiếu dẫn chứng với câu gốc."""
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from app.config import settings
from app.pipeline.llm import chat_json, LLMJSONError


_TEMPLATE_PATH = Path(__file__).parent / "prompts/creative_feedback.txt"


class FeedbackEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idea_id: str = Field(min_length=1)
    quote: str = Field(min_length=2, max_length=160)


class FeedbackObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=10, max_length=450)
    evidence: list[FeedbackEvidence] = Field(min_length=1, max_length=2)


class CreativeFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[FeedbackObservation] = Field(min_length=1, max_length=1)
    suggestion: str = Field(min_length=10, max_length=200)


def _suggestion_body(text: str) -> str:
    """Bỏ nhãn do model thêm để backend chỉ hiển thị một lần."""
    return re.sub(r"^(?:bạn\s+có\s+thể\s+thử\s*[:：,–—-]?\s*)+", "", text.strip(), flags=re.IGNORECASE).strip()


def generate_creative_feedback(item, scores, client, *, fallback):
    """Lỗi nhận xét không làm mất điểm hoặc bắt chạy lại cả pipeline chấm."""
    if not scores:
        return fallback, {"status": "SKIPPED", "reason": "no_scored_ideas"}
    sources = {score.idea_id or f"idea-{index}": score.original for index, score in enumerate(scores)}
    payload = [{"idea_id": idea_id, "original": original} for idea_id, original in sources.items()]
    meta = {}
    try:
        data, meta = chat_json(
            client, model=settings.active_llm_model, temperature=min(settings.scoring_temperature, 0.2),
            prompt=_TEMPLATE_PATH.read_text(encoding="utf-8").format(item_name=item.name, ideas_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("creative_feedback"), max_retries=0,
            stage="creative_feedback",
        )
        feedback = CreativeFeedback.model_validate(data)
        feedback.suggestion = _suggestion_body(feedback.suggestion)
        if len(feedback.suggestion) < 10:
            raise ValueError("feedback_empty_suggestion")
        # Chặn phản hồi dài mà không cắt giữa câu hoặc tốn thêm lượt gọi sửa văn phong.
        word_count = sum(len(observation.text.split()) + sum(len(entry.quote.split()) for entry in observation.evidence)
                         for observation in feedback.observations) + len(feedback.suggestion.split())
        if word_count > 80:
            raise ValueError("feedback_too_long")
        for observation in feedback.observations:
            # Bài có nhiều ý phải có hai câu nguồn khác nhau để tránh nhận xét từ một ví dụ đơn lẻ.
            if len({entry.idea_id for entry in observation.evidence}) != min(2, len(sources)):
                raise ValueError("feedback_insufficient_evidence")
            for evidence in observation.evidence:
                if not evidence.quote.strip() or evidence.quote not in sources.get(evidence.idea_id, ""):
                    raise ValueError("feedback_evidence_not_in_source")
        paragraphs = []
        for observation in feedback.observations:
            quotes = "; ".join(f'“{entry.quote}”' for entry in observation.evidence)
            paragraphs.append(f"{observation.text.strip()} Ví dụ: {quotes}.")
        paragraphs.append(f"Bạn có thể thử: {feedback.suggestion.strip()}")
        return "\n\n".join(paragraphs), {**meta, "status": "GENERATED", "feedback": feedback.model_dump(),
                                       "depends_on_frequency": False, "feedback_contract": "grounded-directions-v2"}
    except (LLMJSONError, ValueError, TypeError, OSError) as exc:
        failure = getattr(exc, "metadata", None) or meta
        reason = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("feedback_") else type(exc).__name__
        return fallback, {**failure, "status": "FALLBACK", "error_type": type(exc).__name__, "fallback_reason": reason}

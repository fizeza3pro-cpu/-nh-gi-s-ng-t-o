"""Nhận xét định tính sau chấm điểm, có đối chiếu dẫn chứng với câu gốc."""
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from app.config import settings
from app.pipeline.llm import chat_json, LLMJSONError


_TEMPLATE = (Path(__file__).parent / "prompts/creative_feedback.txt").read_text(encoding="utf-8")


class FeedbackEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idea_id: str = Field(min_length=1)
    quote: str = Field(min_length=2, max_length=500)


class FeedbackObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=10, max_length=750)
    evidence: list[FeedbackEvidence] = Field(min_length=1, max_length=2)


class CreativeFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[FeedbackObservation] = Field(min_length=1, max_length=2)
    suggestion: str = Field(min_length=10, max_length=500)


def generate_creative_feedback(item, scores, client, *, fallback):
    """Lỗi nhận xét không làm mất điểm hoặc bắt chạy lại cả pipeline chấm."""
    if not scores:
        return fallback, {"status": "SKIPPED", "reason": "no_scored_ideas"}
    sources = {score.idea_id or f"idea-{index}": score.original for index, score in enumerate(scores)}
    payload = [{"idea_id": score.idea_id or f"idea-{index}", "original": score.original,
                "detail_evidence": score.elaboration_details} for index, score in enumerate(scores)]
    meta = {}
    try:
        data, meta = chat_json(
            client, model=settings.active_llm_model, temperature=settings.scoring_temperature,
            prompt=_TEMPLATE.format(item_name=item.name, ideas_json=json.dumps(payload, ensure_ascii=False)),
            provider=settings.llm_provider, reasoning_effort=settings.active_reasoning_effort,
            max_tokens=settings.max_tokens_for("creative_feedback"), max_retries=0,
            stage="creative_feedback",
        )
        feedback = CreativeFeedback.model_validate(data)
        for observation in feedback.observations:
            for evidence in observation.evidence:
                if not evidence.quote.strip() or evidence.quote not in sources.get(evidence.idea_id, ""):
                    raise ValueError("feedback_evidence_not_in_source")
        paragraphs = ["Trong bài làm này:"]
        for observation in feedback.observations:
            quotes = "; ".join(f'“{entry.quote}”' for entry in observation.evidence)
            paragraphs.append(f"{observation.text.strip()} Ví dụ từ bài của bạn: {quotes}.")
        paragraphs.append(f"Bạn có thể thử: {feedback.suggestion.strip()}")
        return "\n\n".join(paragraphs), {**meta, "status": "GENERATED", "feedback": feedback.model_dump(),
                                       "depends_on_frequency": False}
    except (LLMJSONError, ValueError, TypeError) as exc:
        failure = getattr(exc, "metadata", None) or meta
        return fallback, {**failure, "status": "FALLBACK", "error_type": type(exc).__name__}

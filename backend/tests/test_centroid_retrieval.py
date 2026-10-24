"""Kiểm tra centroid hỗ trợ truy xuất mà không khuếch đại một ý đại diện sai."""

import pytest

from app.config import settings
from app.pipeline import code_retrieval
from app.pipeline.cluster_proposals import _nearest_codes
from app.pipeline.embedding import EmbeddingBatch
from app.schemas.schemas import ExtractedIdea, FunctionalSignature, IdeaExtractionResult


@pytest.mark.parametrize(
    "enabled,updates,expected",
    [
        (True, {}, 0.8),
        (False, {}, 0.6),
        (True, {"centroid_dirty": True}, 0.6),
        (True, {"drift_flag": True}, 0.6),
        (True, {"centroid_model": "other-model"}, 0.6),
        (True, {"centroid": []}, 0.6),
        (True, {"centroid": [0.0, 1.0]}, 0.6),
        (True, {"centroid": [1.0, 0.0, 0.0]}, 0.6),
    ],
)
def test_retrieval_uses_only_definition_and_eligible_centroid(monkeypatch, enabled, updates, expected):
    """Ý đại diện trùng query không được đẩy điểm lên 1 hoặc vượt mã đúng hơn."""
    monkeypatch.setattr(settings, "centroid_retrieval_enabled", enabled)
    monkeypatch.setattr(code_retrieval, "embedding_model", lambda client: "test-model")

    def embed(texts, client):
        assert len(texts) == 1
        return EmbeddingBatch(vectors=[[1.0, 0.0]], model="test-model", semantic=True)

    monkeypatch.setattr(code_retrieval, "embed_texts", embed)
    signature = FunctionalSignature(goal="giữ giấy", object_role="vật chặn", mechanism="trọng lượng")
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
        line_index=0, original="Chặn giấy", normalized="Chặn giấy", status="VALID",
        uses_target_object=True, object_used="Vỏ đạn", target_object_role="vật chặn",
        functional_signature=signature,
    )])
    code = {
        "id": "suspect", "name": "Mã cần kiểm tra",
        "functional_signature": signature.model_dump(),
        "embedding": [0.6, 0.8], "embedding_model": "test-model",
        "centroid": [0.8, 0.6], "centroid_model": "test-model",
        "prototype_vectors": [[1.0, 0.0]], "centroid_dirty": False, "drift_flag": False,
        **updates,
    }
    competitor = {
        "id": "better", "name": "Mã gần hơn", "functional_signature": signature.model_dump(),
        "embedding": [0.9, 0.435889894], "embedding_model": "test-model",
    }
    ranked = code_retrieval.rank_code_candidates(extraction, [code, competitor])[0]
    assert ranked[0]["id"] == "better"
    candidate = ranked[1]
    assert candidate["semantic_similarity"] == pytest.approx(expected)
    assert candidate["retrieval_score"] == pytest.approx(0.75 * expected + 0.25)
    assert "prototype_vectors" not in candidate

    # Gợi ý cụm cho admin cũng tuân thủ cùng cờ bật/tắt và không dùng ý đại diện.
    nearest = _nearest_codes(
        [{"functional_signature": signature.model_dump()}], [1.0, 0.0], "test-model", [code, competitor],
    )
    assert nearest[0]["code_id"] == "better"
    assert nearest[1]["semantic_similarity"] == pytest.approx(expected)

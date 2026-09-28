import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.controllers.response_controller import _needs_curator_retry
from app.db import Base
from app.models.models import (
    Item,
    ItemCode,
    Participant,
    Response,
    ResponseIdea,
)
from app.pipeline.codebook_service import (
    list_curator_codes,
    originality_for_response,
    persist_mapping,
    qualifying_idea_count,
    qualifying_response_count,
    refresh_item_scoring_state,
)
from app.pipeline.code_retrieval import core_signature_text, functional_key, rank_code_candidates
from app.controllers.response_worker import _guard_stale_creations
from app.pipeline.dynamic_mapping import (
    _creation_goal_is_grounded,
    _guard_ungrounded_creations,
    _normalize_curator_contract,
    _one_decision_per_index,
    _potential_new_code_overlaps,
    _stored_match_review_reason,
    run_code_curator,
    run_idea_extraction,
)
from app.schemas.schemas import (
    CuratorDecision,
    CuratorResult,
    ExtractedIdea,
    IdeaExtractionResult,
    FunctionalSignature,
    ScoreRequest,
)
from tests.fake_llm import FakeClient


def test_stale_create_requires_explicit_comparison_to_new_code():
    decision = CuratorDecision(
        idea_index=0, decision="CREATE_NEW", code_name="Trang trí Giáng sinh",
        target_object_confirmed=True, target_object_role="Dùng đúng đồ vật",
        confidence=0.9, reviewed_by_challenger=True,
    )
    guarded = _guard_stale_creations(CuratorResult(decisions=[decision]), {"new-code"})
    assert guarded.decisions[0].decision == "UNCERTAIN"
    checked = decision.model_copy(update={"existing_code_evaluations": [{
        "code_id": "new-code", "relation": "DIFFERENT", "verdict": "NO_MATCH",
        "goal_match": False, "role_match": True, "mechanism_match": False,
    }]})
    accepted = _guard_stale_creations(CuratorResult(decisions=[checked]), {"new-code"})
    assert accepted.decisions[0].decision == "CREATE_NEW"


def test_missing_curator_decisions_keeps_response_pending():
    """JSON hợp lệ nhưng thiếu decisions không làm mất câu trả lời hoặc tạo code đoán mò."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()
        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    line_index=0,
                    original="làm vòng đeo tay",
                    normalized="làm vòng đeo tay từ vỏ đạn",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Vỏ đạn",
                    target_object_role="vật liệu",
                    functional_signature=FunctionalSignature(
                        goal="trang trí cơ thể",
                        object_role="vật liệu trang sức",
                        mechanism="gia công thành vòng đeo",
                    ),
                )
            ]
        )

        curator, meta = run_code_curator(item, extraction, [], FakeClient(["{}"]), None)
        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )

        assert meta["adjudicator"]["failed"] is True
        assert _needs_curator_retry(curator, extraction) is True
        assert uncertain is True
        assert mapping.ideas[0].status == "VALID"
        assert mapping.ideas[0].code is None
        assert mapping.ideas[0].curator_decision == "MISSING_DECISION"
        assert db.scalar(select(ItemCode)) is None


def test_missing_challenger_decisions_abstains():
    """Challenger trả object rỗng thì không chấp nhận quyết định chưa phản biện."""
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                line_index=0,
                original="làm vòng đeo tay",
                normalized="làm vòng đeo tay từ vỏ đạn",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="vật liệu",
                functional_signature=FunctionalSignature(
                    goal="trang trí cơ thể",
                    object_role="vật liệu trang sức",
                    mechanism="gia công thành vòng đeo",
                ),
            )
        ]
    )
    adjudicator = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "OUT_OF_CODEBOOK",
                    "code_relation": "DIFFERENT",
                    "target_object_confirmed": True,
                    "target_object_role": "vật liệu",
                    "confidence": 0.8,
                }
            ]
        }
    )

    curator, meta = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        [],
        FakeClient([adjudicator, "{}"]),
    )

    assert curator.decisions[0].decision == "UNCERTAIN"
    assert meta["challenger"]["failed"] is True


def test_empty_codebook_keeps_disagreement_uncertain():
    """Backend không tự bịa category khi Challenger chưa đồng ý tạo code."""
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                line_index=0,
                original="Nung chảy vỏ đạn thành nguyên liệu thô đem bán",
                normalized="Tái chế vỏ đạn thành nguyên liệu thô",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Nguồn kim loại tái chế",
                functional_signature=FunctionalSignature(
                    goal="thu hồi nguyên liệu kim loại",
                    object_role="nguồn kim loại tái chế",
                    mechanism="nung chảy và tái chế",
                ),
            )
        ]
    )
    adjudicator = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": None,
                    "target_object_confirmed": True,
                    "confidence": 0.82,
                    "reason": "Ý tưởng phù hợp một nhóm tái chế.",
                }
            ]
        },
        ensure_ascii=False,
    )
    challenger = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "UNCERTAIN",
                    "existing_code_id": None,
                    "target_object_confirmed": True,
                    "confidence": 0.4,
                    "reason": "Chưa có code để so sánh.",
                }
            ]
        },
        ensure_ascii=False,
    )
    client = FakeClient([adjudicator, challenger])

    result, meta = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        extraction,
        [],
        client,
    )

    decision = result.decisions[0]
    assert client.chat.completions.calls == 2
    assert decision.decision == "UNCERTAIN"
    assert decision.existing_code_id is None
    assert meta["challenger"]["response_id"] == "fake-2"


def test_empty_codebook_keeps_incomplete_signature_uncertain():
    """Fallback quyết định không tự tạo code khi thiếu chữ ký chức năng cốt lõi."""
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                line_index=0,
                original="Dùng lại vỏ đạn",
                normalized="Dùng lại vỏ đạn",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Vật liệu",
                functional_signature=FunctionalSignature(
                    goal="dùng lại",
                    object_role="vật liệu",
                    mechanism="",
                ),
            )
        ]
    )
    adjudicator = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "OUT_OF_CODEBOOK",
                    "confidence": 0.6,
                    "reason": "Không có code ứng viên.",
                }
            ]
        }
    )
    challenger = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "UNCERTAIN",
                    "confidence": 0.5,
                    "reason": "Thiếu cơ chế sử dụng.",
                }
            ]
        }
    )

    result, _ = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        extraction,
        [],
        FakeClient([adjudicator, challenger]),
    )

    assert result.decisions[0].decision == "UNCERTAIN"


def test_challenger_repairs_missing_or_generic_code_boundaries():
    """Chỉ gọi thêm một lượt ngắn khi ranh giới bị thiếu hoặc chỉ mang tính hình thức."""
    signature = FunctionalSignature(
        goal="trang trí cơ thể",
        object_role="vật liệu trang sức",
        mechanism="gia công thành vật đeo",
    )
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                line_index=0,
                original="làm vòng đeo tay",
                normalized="Làm vòng đeo tay từ vỏ đạn",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Vật liệu trang sức",
                functional_signature=signature,
            )
        ]
    )
    adjudicator = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "OUT_OF_CODEBOOK",
                    "code_relation": "DIFFERENT",
                    "target_object_confirmed": True,
                    "target_object_role": "Vật liệu trang sức",
                    "functional_signature": signature.model_dump(),
                    "confidence": 0.9,
                    "reason": "Codebook đang rỗng.",
                }
            ]
        },
        ensure_ascii=False,
    )
    incomplete = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "CREATE_NEW",
                    "code_name": "Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn",
                    "code_description": "Gia công vỏ đạn thành đồ trang sức hoặc phụ kiện đeo.",
                    "target_object_confirmed": True,
                    "target_object_role": "Vật liệu trang sức",
                    "functional_signature": signature.model_dump(),
                    "inclusion_rules": ["có cơ chế trang trí"],
                    "exclusion_rules": ["không dùng để bảo vệ"],
                    "positive_examples": ["làm vòng đeo tay"],
                    "policy_gates": {
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    "confidence": 0.95,
                }
            ]
        },
        ensure_ascii=False,
    )
    repaired = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "CREATE_NEW",
                    "code_name": "Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn",
                    "code_description": "Gia công vỏ đạn thành đồ trang sức hoặc phụ kiện đeo.",
                    "target_object_confirmed": True,
                    "target_object_role": "Vật liệu trang sức",
                    "functional_signature": signature.model_dump(),
                    "inclusion_rules": [
                        "Vỏ đạn được gia công thành vật trang trí đeo trên người"
                    ],
                    "exclusion_rules": [
                        "Không gồm đồ trang trí không đeo hoặc tái chế thành nguyên liệu"
                    ],
                    "scope_variants": [
                        "gia công thành mặt dây chuyền",
                        "gia công thành khuyên tai",
                    ],
                    "positive_examples": ["làm vòng đeo tay"],
                    "policy_gates": {
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    "confidence": 0.95,
                }
            ]
        },
        ensure_ascii=False,
    )
    client = FakeClient([adjudicator, incomplete, repaired])

    result, meta = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        [],
        client,
    )

    decision = result.decisions[0]
    assert client.chat.completions.calls == 3
    assert decision.decision == "CREATE_NEW"
    assert decision.inclusion_rules
    assert decision.exclusion_rules
    assert decision.reviewed_by_challenger is True
    assert meta["challenger"]["boundary_repair"]["response_id"] == "fake-3"


def test_weak_wrong_match_is_sent_to_challenger_and_created_as_new_code():
    """Top-1 retrieval gần bằng 0 không được phép ép ý mới vào category cũ."""
    signature = FunctionalSignature(
        goal="gãi lưng",
        object_role="công cụ",
        mechanism="ma sát",
    )
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original="làm đồ gãi ngứa",
                normalized="Dụng cụ gãi lưng",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Công cụ gãi",
                functional_signature=signature,
            )
        ]
    )
    plant_code = {
        "id": "plant-pot",
        "name": "Chậu cây",
        "description": "Dùng vỏ đạn làm chậu trồng cây",
        "functional_signature": {
            "goal": "trồng trọt",
            "object_role": "chậu",
            "mechanism": "chứa đất",
        },
        "embedding": [0.0] * 384,
    }
    wrong_match = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": "plant-pot",
                    "target_object_confirmed": True,
                    "target_object_role": "Công cụ gãi",
                    "functional_signature": signature.model_dump(),
                    "confidence": 0.8,
                    "reason": "Candidate đứng đầu.",
                }
            ]
        },
        ensure_ascii=False,
    )
    create_new = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "CREATE_NEW",
                    "code_name": "Dụng cụ gãi bằng vỏ đạn",
                    "code_description": "Dùng vỏ đạn như công cụ tạo ma sát để gãi lưng.",
                    "target_object_confirmed": True,
                    "target_object_role": "Công cụ gãi",
                    "functional_signature": signature.model_dump(),
                    "inclusion_rules": ["Dùng vỏ đạn để gãi"],
                    "exclusion_rules": ["Không bao gồm trồng cây"],
                    "scope_variants": [
                        "dùng vỏ đạn gãi vùng da bị ngứa",
                        "gắn cán để làm dụng cụ gãi lưng",
                    ],
                    "positive_examples": ["làm đồ gãi ngứa"],
                    "policy_gates": {
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    "confidence": 0.9,
                    "reason": "Khác mục đích, vai trò và cơ chế.",
                }
            ]
        },
        ensure_ascii=False,
    )
    client = FakeClient([wrong_match, create_new])

    result, _ = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        extraction,
        [plant_code],
        client,
    )

    assert client.chat.completions.calls == 2
    assert result.decisions[0].decision == "CREATE_NEW"
    assert result.decisions[0].code_name == "Dụng cụ gãi bằng vỏ đạn"


def test_challenger_cannot_reapprove_same_weak_match():
    """Hai lượt LLM cùng thiên vị top-1 vẫn phải abstain thay vì gộp sai."""
    signature = FunctionalSignature(
        goal="đậy kín",
        object_role="nắp",
        mechanism="đậy lên",
    )
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original="làm nắp chai",
                normalized="Đậy chai",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Nắp đậy",
                functional_signature=signature,
            )
        ]
    )
    plant_code = {
        "id": "plant-pot",
        "name": "Chậu cây",
        "description": "Dùng vỏ đạn làm chậu trồng cây",
        "functional_signature": {
            "goal": "trồng trọt",
            "object_role": "chậu",
            "mechanism": "chứa đất",
        },
    }
    weak_match = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": "plant-pot",
                    "target_object_confirmed": True,
                    "target_object_role": "Nắp đậy",
                    "functional_signature": signature.model_dump(),
                    "confidence": 0.9,
                    "reason": "Gán theo top-1.",
                }
            ]
        },
        ensure_ascii=False,
    )

    result, _ = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        extraction,
        [plant_code],
        FakeClient([weak_match, weak_match]),
    )

    assert result.decisions[0].decision == "UNCERTAIN"
    assert result.decisions[0].existing_code_id is None
    assert "MATCH an toàn" in result.decisions[0].reason


def test_numeric_match_gate_rejects_llm_flags_when_backend_signals_are_weak():
    """LLM không thể khai ba cờ true để gộp “đe dọa” vào “chèn giấy”."""
    signature = FunctionalSignature(
        goal="đe dọa",
        object_role="đạo cụ gây sợ hãi",
        mechanism="trưng ra cho người khác nhìn thấy",
    )
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(
        original="mang ra dọa người khác",
        normalized="Dùng làm đạo cụ đe dọa",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Đạo cụ gây sợ hãi",
        functional_signature=signature,
    )])
    decision = CuratorDecision(
        idea_index=0,
        decision="MATCH_EXISTING",
        existing_code_id="paperweight",
        code_relation="SAME_CATEGORY",
        target_object_confirmed=True,
        target_object_role="Đạo cụ gây sợ hãi",
        functional_signature=signature,
        existing_code_evaluations=[{
            "code_id": "paperweight",
            "relation": "SAME_CATEGORY",
            "goal_match": True,
            "role_match": True,
            "mechanism_match": True,
            "excluded_by": "",
            "verdict": "MATCH",
        }],
        confidence=0.9,
    )
    candidates = {0: [
        {
            "id": "paperweight",
            "name": "Làm vật chèn giấy",
            "retrieval_score": 0.524365,
            "semantic_similarity": 0.665821,
            "signature_similarity": {
                "goal": 0.0,
                "object_role": 0.333333,
                "mechanism": 0.0,
                "weighted": 0.1,
            },
        },
        {
            "id": "weapon",
            "name": "Làm vũ khí",
            "retrieval_score": 0.485382,
            "semantic_similarity": 0.62,
            "signature_similarity": {"weighted": 0.1},
        },
    ]}

    normalized = _normalize_curator_contract(
        CuratorResult(decisions=[decision]), ideas, candidates
    ).decisions[0]

    assert normalized.decision == "UNCERTAIN"
    assert normalized.existing_code_id is None
    assert "semantic=0.666 < 0.700" in normalized.reason
    assert "margin=0.039 < 0.080" in normalized.reason


def test_numeric_match_gate_rejects_candidate_that_is_not_top_one():
    """Móc khóa không được gắn vào candidate hạng ba chỉ vì tên có chữ phụ kiện."""
    signature = FunctionalSignature(
        goal="giữ chìa khóa", object_role="móc khóa", mechanism="gắn vào vòng"
    )
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(
        original="làm móc khóa",
        normalized="Làm móc khóa",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Móc khóa",
        functional_signature=signature,
    )])
    decision = CuratorDecision(
        idea_index=0,
        decision="MATCH_EXISTING",
        existing_code_id="jewelry",
        code_relation="IDEA_NARROWER_THAN_CODE",
        target_object_confirmed=True,
        target_object_role="Móc khóa",
        functional_signature=signature,
        existing_code_evaluations=[{
            "code_id": "jewelry",
            "relation": "IDEA_NARROWER_THAN_CODE",
            "goal_match": True,
            "role_match": True,
            "mechanism_match": True,
            "excluded_by": "",
            "verdict": "MATCH",
        }],
        confidence=0.9,
    )
    candidates = {0: [
        {"id": "gift", "retrieval_score": 0.50, "semantic_similarity": 0.65},
        {"id": "model", "retrieval_score": 0.45, "semantic_similarity": 0.60},
        {
            "id": "jewelry",
            "retrieval_score": 0.425,
            "semantic_similarity": 0.56,
            "signature_similarity": {
                "goal": 0.0, "object_role": 0.0,
                "mechanism": 0.06, "weighted": 0.02,
            },
        },
    ]}

    normalized = _normalize_curator_contract(
        CuratorResult(decisions=[decision]), ideas, candidates
    ).decisions[0]

    assert normalized.decision == "UNCERTAIN"
    assert "hạng 3" in normalized.reason


def test_challenger_can_resolve_uncertain_as_create_new_with_full_evidence():
    """Curator abstain không bắt một đề xuất mã đầy đủ phải chờ admin."""
    signature = FunctionalSignature(
        goal="gãi ngứa", object_role="dụng cụ gãi", mechanism="tạo ma sát"
    )
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
        original="dùng để gãi ngứa",
        normalized="Dùng làm dụng cụ gãi",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Dụng cụ gãi",
        functional_signature=signature,
    )])
    uncertain = json.dumps({"decisions": [{
        "idea_index": 0,
        "decision": "UNCERTAIN",
        "code_relation": "UNCERTAIN",
        "target_object_confirmed": True,
        "target_object_role": "Dụng cụ gãi",
        "functional_signature": signature.model_dump(),
        "confidence": 0.5,
        "reason": "Cần phản biện phạm vi mã.",
    }]}, ensure_ascii=False)
    create_new = json.dumps({"decisions": [{
        "idea_index": 0,
        "decision": "CREATE_NEW",
        "code_relation": "NOT_APPLICABLE",
        "code_name": "Dụng cụ gãi từ vỏ đạn",
        "code_description": "Dùng vỏ đạn tạo ma sát để gãi ngứa.",
        "target_object_confirmed": True,
        "target_object_role": "Dụng cụ gãi",
        "functional_signature": signature.model_dump(),
        "inclusion_rules": ["Vỏ đạn trực tiếp tạo ma sát trên vùng da bị ngứa"],
        "exclusion_rules": ["Không bao gồm dùng vỏ đạn chỉ để trang trí cơ thể"],
        "scope_variants": [
            "dùng vỏ đạn gãi vùng da bị ngứa",
            "gắn cán để làm dụng cụ gãi lưng",
        ],
        "positive_examples": ["dùng để gãi ngứa"],
        "policy_gates": {
            "response_is_valid": True,
            "no_existing_code_covers": True,
            "functionally_distinct": True,
            "granularity_consistent": True,
            "paraphrase_stable": True,
            "counterexample_passed": True,
        },
        "confidence": 0.9,
        "reason": "Chức năng mới có ranh giới đầy đủ.",
    }]}, ensure_ascii=False)

    result, _ = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        [],
        FakeClient([uncertain, create_new]),
    )

    assert result.decisions[0].decision == "CREATE_NEW"
    assert result.decisions[0].reviewed_by_challenger is True


def test_match_with_false_goal_flag_is_rejected_even_when_verdict_says_match():
    """Không lặp lại lỗi vật chèn giấy bị hút vào category trang sức."""
    signature = FunctionalSignature(
        goal="giữ giấy cố định",
        object_role="vật chèn",
        mechanism="trọng lượng và ma sát",
    )
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original="dùng làm vật chèn giấy",
                normalized="Chèn giấy",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Vật chèn",
                functional_signature=signature,
            )
        ]
    )
    jewelry = {
        "id": "jewelry",
        "name": "Đồ trang sức hoặc phụ kiện đeo",
        "description": "Gia công vỏ đạn thành vật trang trí đeo trên người.",
        "functional_signature": {
            "goal": "trang trí",
            "object_role": "vật liệu",
            "mechanism": "đeo",
        },
    }
    contradictory_match = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": "jewelry",
                    "code_relation": "SAME_CATEGORY",
                    "target_object_confirmed": True,
                    "target_object_role": "Vật chèn",
                    "functional_signature": signature.model_dump(),
                    "existing_code_evaluations": [
                        {
                            "code_id": "jewelry",
                            "relation": "SAME_CATEGORY",
                            "goal_match": False,
                            "role_match": False,
                            "mechanism_match": False,
                            "excluded_by": "",
                            "verdict": "MATCH",
                        }
                    ],
                    "confidence": 0.95,
                    "reason": "Ép gán candidate gần nhất.",
                }
            ]
        },
        ensure_ascii=False,
    )

    result, _ = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        [jewelry],
        FakeClient([contradictory_match, contradictory_match]),
    )

    assert result.decisions[0].decision == "UNCERTAIN"
    assert result.decisions[0].existing_code_id is None
    assert "mục đích chức năng không khớp" in result.decisions[0].reason


def test_strong_match_skips_challenger_and_records_backend_audit():
    signature = FunctionalSignature(
        goal="trang trí",
        object_role="vật liệu",
        mechanism="dính kết",
    )
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                original="gắn vỏ đạn thành mô hình",
                normalized="Làm mô hình trang trí",
                status="VALID",
                uses_target_object=True,
                object_used="Vỏ đạn",
                target_object_role="Vật liệu trang trí",
                functional_signature=signature,
            )
        ]
    )
    code = {
        "id": "decoration",
        "name": "Trang trí bằng vỏ đạn",
        "description": "Dùng vỏ đạn làm vật liệu dính kết thành đồ trang trí",
        "functional_signature": signature.model_dump(),
    }
    match = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": 0,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": "decoration",
                    "code_relation": "SAME_CATEGORY",
                    "target_object_confirmed": True,
                    "target_object_role": "Vật liệu trang trí",
                    "functional_signature": signature.model_dump(),
                    "existing_code_evaluations": [
                        {
                            "code_id": "decoration",
                            "relation": "SAME_CATEGORY",
                            "goal_match": True,
                            "role_match": True,
                            "mechanism_match": True,
                            "excluded_by": "",
                            "verdict": "MATCH",
                        }
                    ],
                    "confidence": 0.9,
                    "reason": "Cùng chức năng cốt lõi.",
                }
            ]
        },
        ensure_ascii=False,
    )
    client = FakeClient([match])

    result, meta = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        extraction,
        [code],
        client,
    )

    assert client.chat.completions.calls == 1
    assert result.decisions[0].decision == "MATCH_EXISTING"
    audit = result.decisions[0].existing_code_evaluations[-1]
    assert audit["source"] == "BACKEND_MATCH_GUARD"
    assert audit["verdict"] == "PASS"
    assert meta["challenger"]["skipped"] is True


def test_extraction_repairs_false_object_flag_when_structured_evidence_is_complete():
    payload = json.dumps(
        {
            "ideas": [
                {
                    "line_index": 0,
                    "original": "làm vòng cổ",
                    "normalized": "Làm trang sức",
                    "status": "VALID",
                    "uses_target_object": False,
                    "object_used": "Vỏ đạn",
                    "target_object_role": "Vật trang trí",
                    "functional_signature": {
                        "goal": "trang trí",
                        "object_role": "vật liệu",
                        "mechanism": "đeo trên người",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    result, meta = run_idea_extraction(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        ["làm vòng cổ"],
        FakeClient([payload]),
    )

    assert result.ideas[0].uses_target_object is True
    assert meta["contract_repairs"][0]["field"] == "uses_target_object"


def test_invalid_extraction_is_verified_again_with_implicit_target_context():
    """Câu “dùng để tính điểm” không bị loại chỉ vì không nhắc lại tên vật thể."""
    first = json.dumps(
        {
            "ideas": [
                {
                    "line_index": 0,
                    "original": "dùng để tính điểm chuyên cần",
                    "normalized": "tính điểm chuyên cần",
                    "status": "INVALID",
                    "uses_target_object": False,
                    "object_used": "",
                    "reason": "Không liên quan đến vỏ đạn",
                }
            ]
        },
        ensure_ascii=False,
    )
    verified = json.dumps(
        {
            "ideas": [
                {
                    "line_index": 0,
                    "original": "dùng để tính điểm chuyên cần",
                    "normalized": "Dùng vỏ đạn làm vật đếm điểm chuyên cần",
                    "status": "VALID",
                    "uses_target_object": True,
                    "object_used": "Vỏ đạn",
                    "target_object_role": "vật đếm hoặc thẻ điểm",
                    "functional_signature": {
                        "goal": "ghi nhận điểm chuyên cần",
                        "object_role": "vật đếm",
                        "mechanism": "đặt hoặc trao một đơn vị cho mỗi lần ghi nhận",
                    },
                    "reason": "",
                }
            ]
        },
        ensure_ascii=False,
    )

    result, meta = run_idea_extraction(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        ["dùng để tính điểm chuyên cần"],
        FakeClient([first, verified]),
    )

    assert result.ideas[0].status == "VALID"
    assert result.ideas[0].uses_target_object is True
    assert result.ideas[0].functional_signature.object_role == "vật đếm"
    assert meta["invalid_verifier"]["response_id"] == "fake-2"


def test_impossibility_reason_gets_focused_policy_repair():
    """“Không thể nhồi lại” không được dùng làm lý do INVALID trong AUT."""
    rejected = json.dumps({"ideas": [{
        "line_index": 0,
        "original": "nhồi thuốc súng lại bắn tiếp",
        "normalized": "Nhồi thuốc súng để tái sử dụng",
        "status": "INVALID",
        "uses_target_object": False,
        "object_used": "",
        "reason": "Vỏ đạn không thể nhồi thuốc súng lại để bắn tiếp",
    }]}, ensure_ascii=False)
    repaired = json.dumps({"ideas": [{
        "line_index": 0,
        "original": "nhồi thuốc súng lại bắn tiếp",
        "normalized": "Tái nạp vỏ đạn",
        "status": "VALID",
        "uses_target_object": True,
        "object_used": "Vỏ đạn",
        "target_object_role": "vỏ chứa liều phóng",
        "functional_signature": {
            "goal": "tái nạp đạn",
            "object_role": "vỏ chứa liều phóng",
            "mechanism": "chứa và định vị thuốc súng",
        },
        "functional_evidence": {
            "goal": "bắn tiếp",
            "object_role": "",
            "mechanism": "nhồi thuốc súng",
        },
        "inferred_signature_fields": ["object_role"],
        "reason": "",
    }]}, ensure_ascii=False)
    client = FakeClient([rejected, rejected, repaired])

    result, meta = run_idea_extraction(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại của viên đạn"),
        ["nhồi thuốc súng lại bắn tiếp"],
        client,
    )

    assert client.chat.completions.calls == 3
    assert result.ideas[0].status == "VALID"
    assert result.ideas[0].functional_signature.goal == "tái nạp đạn"
    assert meta["invalid_verifier"]["policy_repair"]["response_id"] == "fake-3"


def test_repeated_impossibility_rejection_is_queued_for_admin_not_discarded():
    """Nếu model vẫn cố loại bằng tính khả thi, backend giữ ý để con người phân xử."""
    rejected = json.dumps({"ideas": [{
        "line_index": 0,
        "original": "nhồi thuốc súng lại bắn tiếp",
        "normalized": "Nhồi thuốc súng để tái sử dụng",
        "status": "INVALID",
        "uses_target_object": False,
        "object_used": "",
        "reason": "Vỏ đạn không thể nhồi thuốc súng lại để bắn tiếp",
    }]}, ensure_ascii=False)
    extraction, _ = run_idea_extraction(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        ["nhồi thuốc súng lại bắn tiếp"],
        FakeClient([rejected, rejected, rejected]),
    )
    assert extraction.ideas[0].status == "INVALID"
    assert extraction.ideas[0].review_required is True

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()
        mapping, uncertain = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=CuratorResult(decisions=[]),
        )
        saved = db.scalar(select(ResponseIdea))

        assert uncertain is True
        assert mapping.ideas[0].status == "VALID"
        assert mapping.ideas[0].code is None
        assert saved.review_status == "PENDING"
        assert saved.curator_decision == "EXTRACTION_REVIEW"


def test_challenger_retries_only_missing_decisions_before_admin_review():
    """Một dòng bị thiếu trong JSON Challenger được hỏi lại riêng thay vì treo admin."""
    signatures = [
        FunctionalSignature(
            goal="gãi ngứa", object_role="dụng cụ gãi", mechanism="tạo ma sát"
        ),
        FunctionalSignature(
            goal="giữ giấy", object_role="vật chèn", mechanism="tạo sức nặng"
        ),
    ]
    extraction = IdeaExtractionResult(ideas=[
        ExtractedIdea(
            line_index=index,
            original=original,
            normalized=original,
            status="VALID",
            uses_target_object=True,
            object_used="Vỏ đạn",
            target_object_role=signature.object_role,
            functional_signature=signature,
        )
        for index, (original, signature) in enumerate(zip(
            ["dùng để gãi ngứa", "dùng làm vật chèn giấy"], signatures
        ))
    ])
    adjudicator = json.dumps({"decisions": [
        {
            "idea_index": index,
            "decision": "OUT_OF_CODEBOOK",
            "code_relation": "DIFFERENT",
            "target_object_confirmed": True,
            "target_object_role": signature.object_role,
            "functional_signature": signature.model_dump(),
            "confidence": 0.8,
            "reason": "Không mã nào bao phủ chức năng.",
        }
        for index, signature in enumerate(signatures)
    ]}, ensure_ascii=False)

    def create_payload(index: int, name: str) -> dict:
        signature = signatures[index]
        return {
            "idea_index": index,
            "decision": "CREATE_NEW",
            "code_relation": "NOT_APPLICABLE",
            "code_name": name,
            "code_description": f"Dùng vỏ đạn cho chức năng {signature.goal}.",
            "target_object_confirmed": True,
            "target_object_role": signature.object_role,
            "functional_signature": signature.model_dump(),
            "inclusion_rules": [f"Vỏ đạn trực tiếp tham gia chức năng {signature.goal}"],
            "exclusion_rules": ["Không bao gồm ý có mục đích và cơ chế hoàn toàn khác"],
            "scope_variants": [
                f"biến thể thứ nhất vẫn dùng vỏ đạn để {signature.goal}",
                f"biến thể thứ hai vẫn dùng cơ chế {signature.mechanism}",
            ],
            "positive_examples": [extraction.ideas[index].original],
            "policy_gates": {
                "response_is_valid": True,
                "no_existing_code_covers": True,
                "functionally_distinct": True,
                "granularity_consistent": True,
                "paraphrase_stable": True,
                "counterexample_passed": True,
            },
            "confidence": 0.85,
            "reason": "Chức năng mới có ranh giới rõ.",
        }

    first_challenge = json.dumps(
        {"decisions": [create_payload(0, "Dụng cụ gãi từ vỏ đạn")]},
        ensure_ascii=False,
    )
    retry_missing = json.dumps(
        {"decisions": [create_payload(1, "Vật chèn giấy từ vỏ đạn")]},
        ensure_ascii=False,
    )
    client = FakeClient([adjudicator, first_challenge, retry_missing])

    result, meta = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        [],
        client,
    )

    assert client.chat.completions.calls == 3
    assert [decision.decision for decision in result.decisions] == [
        "CREATE_NEW", "CREATE_NEW"
    ]
    assert meta["challenger"]["strategy"] == "retry_missing_only"
    assert meta["challenger"]["initial_missing_indices"] == [1]


@pytest.mark.parametrize("grouped_contract", [False, True])
def test_overlapping_new_codes_in_same_submission_are_reconciled(grouped_contract):
    """Các cách chứa khác nhau của thùng đạn không tạo code rộng/hẹp song song."""
    signatures = [
        FunctionalSignature(
            goal="chứa đạn",
            object_role="thùng chứa",
            mechanism="đậy nắp và bảo vệ",
        ),
        FunctionalSignature(
            goal="chứa đồ quân nhu",
            object_role="thùng chứa",
            mechanism="đậy nắp và bảo vệ",
        ),
    ]
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                line_index=index,
                original=original,
                normalized=normalized,
                status="VALID",
                uses_target_object=True,
                object_used="Thùng đạn",
                target_object_role="Thùng chứa",
                functional_signature=signatures[index],
            )
            for index, (original, normalized) in enumerate(
                [
                    ("đựng đạn", "Chứa đạn"),
                    ("đựng đồ quân nhu", "Chứa đồ quân nhu"),
                ]
            )
        ]
    )
    adjudicator = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": index,
                    "decision": "OUT_OF_CODEBOOK",
                    "code_relation": "DIFFERENT",
                    "target_object_confirmed": True,
                    "target_object_role": "Thùng chứa",
                    "functional_signature": signatures[index].model_dump(),
                    "confidence": 0.8,
                }
                for index in range(2)
            ]
        },
        ensure_ascii=False,
    )
    challenger = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": index,
                    "decision": "CREATE_NEW",
                    "code_name": name,
                    "code_description": description,
                    "target_object_confirmed": True,
                    "target_object_role": "Thùng chứa",
                    "functional_signature": signatures[index].model_dump(),
                    "inclusion_rules": [
                        "Dùng thùng đạn có nắp để chứa và bảo vệ đồ vật bên trong"
                    ],
                    "exclusion_rules": [
                        "Không gồm dùng gỗ của thùng làm nhiên liệu tạo nhiệt"
                    ],
                    "scope_variants": [
                        "dùng thùng đạn chứa dụng cụ bảo dưỡng",
                        "dùng thùng đạn bảo quản thiết bị dã ngoại",
                    ],
                    "positive_examples": [example],
                    "policy_gates": {
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    "confidence": 0.9,
                }
                for index, (name, description, example) in enumerate(
                    [
                        ("Chứa đạn", "Dùng thùng để chứa đạn.", "đựng đạn"),
                        (
                            "Chứa đồ quân nhu",
                            "Dùng thùng để chứa đồ quân nhu.",
                            "đựng đồ quân nhu",
                        ),
                    ]
                )
            ]
        },
        ensure_ascii=False,
    )
    reconciled = json.dumps(
        {
            "decisions": [
                {
                    "idea_index": index,
                    "decision": "CREATE_NEW",
                    "code_name": "Chứa và bảo quản đồ vật",
                    "code_description": "Dùng thùng đạn để chứa và bảo vệ các đồ vật bên trong.",
                    "target_object_confirmed": True,
                    "target_object_role": "Thùng chứa",
                    "functional_signature": {
                        "goal": "chứa và bảo quản đồ vật",
                        "object_role": "thùng chứa",
                        "mechanism": "đậy nắp và bảo vệ",
                    },
                    "inclusion_rules": [
                        "Thùng đạn giữ vai trò vật chứa có nắp để lưu trữ và bảo vệ đồ vật"
                    ],
                    "exclusion_rules": [
                        "Không gồm tháo gỗ làm nhiên liệu hoặc xếp thùng làm kết cấu leo trèo"
                    ],
                    "scope_variants": [
                        "dùng thùng đạn chứa dụng cụ bảo dưỡng",
                        "dùng thùng đạn bảo quản thiết bị dã ngoại",
                    ],
                    "positive_examples": ["đựng đạn", "đựng đồ quân nhu"],
                    "policy_gates": {
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    "confidence": 0.92,
                }
                for index in range(2)
            ]
        },
        ensure_ascii=False,
    )
    if grouped_contract:
        canonical = json.loads(reconciled)["decisions"][0]
        canonical.pop("positive_examples")
        reconciled = json.dumps({"groups": [{"idea_indices": [0, 1], "canonical": canonical}]}, ensure_ascii=False)
    client = FakeClient([adjudicator, challenger, reconciled])

    result, meta = run_code_curator(
        Item(id="thung_dan", name="Thùng đạn", description="Thùng gỗ có nắp"),
        extraction,
        [],
        client,
    )

    assert client.chat.completions.calls == 3
    assert {decision.code_name for decision in result.decisions} == {
        "Chứa và bảo quản đồ vật"
    }
    assert all(len(decision.positive_examples) == 2 for decision in result.decisions)
    assert meta["batch_reconciliation"]["response_id"] == "fake-3"
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="thung_dan", name="Thùng đạn", description="Thùng gỗ có nắp")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()
        mapping, pending = persist_mapping(db, item=item, response=response,
                                          extraction=extraction, curator=result, code_snapshots=[])
        assert not pending
        assert len(db.scalars(select(ItemCode)).all()) == 1
        assert all(idea.coding_state == "ASSIGNED" for idea in mapping.ideas)


def test_duplicate_missing_reference_repairs_only_affected_line():
    """Giữ nguyên ý đầu, chỉ hỏi lại liên kết bị thiếu của ý trùng."""
    first = {"line_index": 0, "original": "tặng bạn An", "normalized": "tặng quà", "status": "VALID",
             "uses_target_object": True, "object_used": "Vỏ đạn", "target_object_role": "món quà",
             "functional_signature": {"goal": "tặng quà", "object_role": "món quà", "mechanism": "trao tặng"}}
    duplicate = {**first, "line_index": 1, "original": "tặng bạn Bình", "status": "DUPLICATE", "duplicate_of_index": None}
    fixed = {**duplicate, "duplicate_of_index": 0}
    client = FakeClient([json.dumps({"ideas": [first, duplicate]}, ensure_ascii=False),
                         json.dumps({"ideas": [fixed]}, ensure_ascii=False)])
    result, metadata = run_idea_extraction(Item(id="vo", name="Vỏ đạn", description="Vỏ kim loại rỗng"),
                                         [first["original"], duplicate["original"]], client)
    assert client.chat.completions.calls == 2
    assert result.ideas[1].duplicate_of_index == 0
    assert result.ideas[0].status == "VALID"
    assert metadata["extraction_repairs"][0]["stage"] == "duplicate_reference_repair"


def test_score_request_accepts_ten_separate_ideas_and_rejects_more():
    request = ScoreRequest(item_id="dua", responses=[f"Ý tưởng {index}" for index in range(10)])
    assert len(request.responses) == 10
    assert request.raw_input.count("\n") == 9
    with pytest.raises(ValueError):
        ScoreRequest(item_id="dua", responses=[f"Ý tưởng {index}" for index in range(11)])


def test_retrieval_prioritizes_goal_role_and_mechanism():
    extraction = IdeaExtractionResult(
        ideas=[
            ExtractedIdea(
                line_index=0,
                original="Dùng gạch chặn cửa",
                normalized="Chặn cửa bằng gạch",
                status="VALID",
                uses_target_object=True,
                object_used="Gạch",
                target_object_role="Vật cố định",
                functional_signature=FunctionalSignature(
                    goal="ngăn vật di chuyển",
                    object_role="vật cố định",
                    mechanism="khối lượng và ma sát",
                ),
            )
        ]
    )
    codes = [
        {
            "id": "exercise",
            "name": "Tập luyện",
            "description": "Dùng gạch làm tải trọng",
            "embedding": [0.0] * 384,
            "functional_signature": {
                "goal": "tạo sức cản",
                "object_role": "vật tạo tải",
                "mechanism": "khối lượng",
            },
        },
        {
            "id": "stabilize",
            "name": "Cố định bằng trọng lượng",
            "description": "Dùng gạch ngăn vật di chuyển",
            "functional_signature": {
                "goal": "ngăn vật di chuyển",
                "object_role": "vật cố định",
                "mechanism": "khối lượng và ma sát",
            },
        },
    ]
    ranked = rank_code_candidates(extraction, codes)
    assert ranked[0][0]["id"] == "stabilize"
    assert "embedding" not in ranked[0][0]
    assert ranked[0][0]["signature_similarity"]["goal"] == 1.0


def test_core_embedding_text_does_not_include_surface_label_or_context():
    signature = FunctionalSignature(
        goal="treo đồ vật",
        object_role="móc chịu lực",
        mechanism="uốn và ghép nối",
        target="áo khoác",
        context="trong phòng ngủ",
    )
    text = core_signature_text(signature)
    assert "treo đồ vật" in text
    assert "móc chịu lực" in text
    assert "uốn và ghép nối" in text
    assert "áo khoác" not in text
    assert "phòng ngủ" not in text


def test_new_code_is_created_directly_without_challenger_or_self_reported_gates():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="gach", name="Gạch", description="Một viên gạch")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()
        signature = FunctionalSignature(
            goal="giữ ấm",
            object_role="vật tích nhiệt",
            mechanism="hấp thụ và giải phóng nhiệt",
        )
        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    line_index=0,
                    original="Nung gạch để sưởi chân",
                    normalized="Dùng gạch nóng để giữ ấm",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Gạch",
                    target_object_role="Vật tích và truyền nhiệt",
                    functional_signature=signature,
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Tích và truyền nhiệt",
                    code_description="Dùng gạch như vật tích và truyền nhiệt để điều chỉnh nhiệt độ.",
                    target_object_confirmed=True,
                    target_object_role="Vật tích nhiệt",
                    functional_signature=signature,
                    inclusion_rules=["Khả năng giữ nhiệt là cơ chế chính"],
                    exclusion_rules=["Không bao gồm dùng gạch làm nhiên liệu"],
                    scope_variants=[
                        "Làm nóng gạch để ủ ấm giường",
                        "Dùng gạch đã nung làm khối giữ nhiệt",
                    ],
                    positive_examples=["Nung gạch để sưởi chân"],
                    confidence=0.51,
                )
            ]
        )
        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )
        code = db.scalar(select(ItemCode))
        assert uncertain is False
        assert mapping.ideas[0].code == "Tích và truyền nhiệt"
        assert code.validation_status.value == "ACCEPTED"
        assert code.functional_signature["mechanism"] == "hấp thụ và giải phóng nhiệt"


def test_compact_curator_can_create_directly_and_skips_challenger():
    signature = FunctionalSignature(
        goal="tạo âm thanh",
        object_role="buồng cộng hưởng",
        mechanism="dao động cột không khí",
        target="tiếng sáo",
    )
    category_signature = signature.model_copy(update={"target": ""})
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
        line_index=0,
        original="Thổi vào vỏ đạn để tạo tiếng sáo",
        normalized="Dùng vỏ đạn tạo âm thanh",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Buồng cộng hưởng",
        functional_signature=signature,
    )])
    compact_create = json.dumps({"decisions": [{
        "idea_index": 0,
        "decision": "CREATE_NEW",
        "code_relation": "DIFFERENT",
        "existing_code_id": None,
        "code_name": "Tạo âm thanh bằng vỏ đạn",
        "code_description": "Dùng vỏ đạn như buồng cộng hưởng để tạo âm thanh.",
        "functional_signature": category_signature.model_dump(),
        "scope_variants": [
            "thổi qua nhiều vỏ đạn để tạo các cao độ",
            "gắn vỏ đạn thành bộ phận cộng hưởng cho nhạc cụ",
        ],
        "inclusion_rules": ["Vỏ đạn trực tiếp cộng hưởng hoặc phát ra âm thanh"],
        "exclusion_rules": ["Không gồm việc chỉ treo vỏ đạn làm đồ trang trí"],
        "confidence": 0.88,
        "reason": "Các code hiện có không bao phủ chức năng âm thanh.",
    }]}, ensure_ascii=False)
    client = FakeClient([compact_create])

    result, meta = run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        [],
        client,
    )

    decision = result.decisions[0]
    assert client.chat.completions.calls == 1
    assert decision.decision == "CREATE_NEW"
    assert decision.functional_signature == category_signature
    assert extraction.ideas[0].functional_signature.target == "tiếng sáo"
    assert len(decision.scope_variants) == 2
    assert decision.positive_examples == [extraction.ideas[0].original]
    assert decision.reviewed_by_challenger is False
    assert meta["challenger"]["skipped"] is True


def test_create_without_category_signature_never_inherits_idea_signature():
    """Thiếu chữ ký category phải đi scope-repair, không tái diễn lỗi lấy chữ ký ý làm code."""
    idea_signature = FunctionalSignature(
        goal="tạo vỏ bọc cho bút viết",
        object_role="ống bảo vệ",
        mechanism="lồng ruột bút vào khoang rỗng",
        target="bút viết",
        context="văn phòng phẩm",
    )
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(
        original="dùng làm vỏ bút",
        normalized="Làm vỏ bút từ vỏ đạn",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Ống bảo vệ",
        functional_signature=idea_signature,
    )])
    decision = CuratorDecision(
        idea_index=0,
        decision="CREATE_NEW",
        code_relation="DIFFERENT",
        code_name="Làm vỏ bút từ vỏ đạn",
        code_description="Dùng vỏ đạn làm vỏ bút.",
        inclusion_rules=["Vỏ đạn làm ống bảo vệ cho ruột bút bên trong"],
        exclusion_rules=["Không gồm gắn vỏ đạn làm phụ kiện treo đồ dùng"],
        scope_variants=["lắp ruột bút bi", "lắp ngòi dụng cụ đánh dấu"],
        confidence=0.9,
    )

    normalized = _normalize_curator_contract(
        CuratorResult(decisions=[decision]), ideas, {}
    ).decisions[0]

    assert normalized.functional_signature.goal == ""
    assert normalized.functional_signature.target == ""
    assert normalized.positive_examples == [ideas.ideas[0].original]


def test_small_codebook_searches_all_compact_candidates():
    signature = FunctionalSignature(
        goal="tạo âm thanh",
        object_role="buồng cộng hưởng",
        mechanism="dao động cột không khí",
    )
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
        original="Thổi vào vỏ đạn để tạo tiếng sáo",
        normalized="Dùng vỏ đạn tạo âm thanh",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Buồng cộng hưởng",
        functional_signature=signature,
    )])
    codes = [
        {
            "id": f"UNIQUE-CODE-{index}",
            "name": f"Code {index}",
            "description": "Mô tả " * 100,
            "functional_signature": {
                "goal": f"mục đích {index}",
                "object_role": f"vai trò {index}",
                "mechanism": f"cơ chế {index}",
            },
            "scope_history": [{"large": "x" * 1000}],
        }
        for index in range(7)
    ]
    compact_create = json.dumps({"decisions": [{
        "idea_index": 0,
        "decision": "CREATE_NEW",
        "code_relation": "DIFFERENT",
        "code_name": "Tạo âm thanh bằng vỏ đạn",
        "code_description": "Dùng vỏ đạn như buồng cộng hưởng để tạo âm thanh.",
        "functional_signature": signature.model_dump(),
        "scope_variants": [
            "thổi qua nhiều vỏ đạn để tạo các cao độ",
            "gắn vỏ đạn làm bộ phận cộng hưởng cho nhạc cụ",
        ],
        "inclusion_rules": ["Vỏ đạn trực tiếp cộng hưởng để tạo âm thanh"],
        "exclusion_rules": ["Không gồm công dụng có mục đích khác tạo âm thanh"],
        "confidence": 0.88,
        "reason": "Khác chức năng.",
    }]}, ensure_ascii=False)
    client = FakeClient([compact_create])

    run_code_curator(
        Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại"),
        extraction,
        codes,
        client,
    )

    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    included_ids = [code["id"] for code in codes if code["id"] in prompt]
    assert len(included_ids) == 7
    assert "scope_history" not in prompt


def test_same_functional_key_does_not_silently_match_or_create_code():
    """Khung chức năng giống nhau cần bằng chứng phân biệt, không tự gộp hoặc tạo."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="gach", name="Gạch", description="Một viên gạch")
        response = _response(participant.id, item.id)
        signature = FunctionalSignature(
            goal="giữ ấm", object_role="vật tích nhiệt", mechanism="truyền nhiệt"
        )
        existing = ItemCode(
            item_id=item.id,
            name="Sưởi chân bằng gạch",
            normalized_name="suoi chan bang gach",
            description="Dùng gạch để giữ ấm chân.",
            functional_key=functional_key(signature),
            functional_signature=signature.model_dump(),
        )
        db.add_all([participant, item, response, existing])
        db.flush()
        extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
            original="Nung gạch làm túi sưởi", normalized="Dùng gạch để giữ ấm",
            status="VALID", uses_target_object=True, object_used="Gạch",
            target_object_role="Vật tích nhiệt", functional_signature=signature,
        )])
        curator = CuratorResult(decisions=[CuratorDecision(
            idea_index=0, decision="CREATE_NEW",
            code_name="Túi sưởi từ gạch",
            code_description="Dùng gạch tích nhiệt để sưởi.",
            target_object_confirmed=True, target_object_role="Vật tích nhiệt",
            functional_signature=signature,
            inclusion_rules=["Gạch được nung nóng để truyền nhiệt cho cơ thể"],
            exclusion_rules=["Không bao gồm gạch chỉ dùng làm vật kê"],
            positive_examples=["Nung gạch làm túi sưởi"],
            existing_code_evaluations=[{
                "code_id": existing.id,
                "relation": "DIFFERENT",
                "goal_match": False,
                "role_match": False,
                "mechanism_match": False,
                "excluded_by": "",
                "verdict": "NO_MATCH",
            }],
            policy_gates={gate: True for gate in (
                "response_is_valid", "no_existing_code_covers", "functionally_distinct",
                "granularity_consistent", "paraphrase_stable", "counterexample_passed",
            )},
            reviewed_by_challenger=True, confidence=0.9,
        )])

        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )
        assert uncertain is True
        assert mapping.ideas[0].code is None
        assert mapping.ideas[0].curator_decision == "CODE_COLLISION_REVIEW"
        assert len(db.scalars(select(ItemCode)).all()) == 1


def test_excluded_response_does_not_contribute_to_centroid():
    """Ý hợp lệ của bài EXCLUDED không được kéo tâm mã nghiên cứu."""
    from app.models.models import ResponseScoringStatus

    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="gach", name="Gạch", description="Một viên gạch")
        response = _response(participant.id, item.id)
        excluded = _response(participant.id, item.id)
        excluded.scoring_status = ResponseScoringStatus.EXCLUDED
        code = ItemCode(
            item_id=item.id, name="Giữ ấm bằng gạch",
            normalized_name="giu am bang gach",
            description="Dùng gạch để giữ ấm.",
        )
        db.add_all([participant, item, response, excluded, code])
        db.flush()
        db.add(ResponseIdea(
            response_id=excluded.id, code_id=code.id,
            original="Ý bị loại", normalized="Ý bị loại",
            mapping_status="VALID", embedding=[0.0, 1.0], embedding_model="model-v1",
        ))
        db.flush()
        signature = FunctionalSignature(
            goal="giữ ấm", object_role="vật tích nhiệt", mechanism="truyền nhiệt"
        )
        extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
            original="Sưởi chân", normalized="Dùng gạch sưởi chân", status="VALID",
            uses_target_object=True, object_used="Gạch", target_object_role="Vật tích nhiệt",
            functional_signature=signature, embedding=[1.0, 0.0], embedding_model="model-v1",
        )])
        curator = CuratorResult(decisions=[CuratorDecision(
            idea_index=0, decision="MATCH_EXISTING", existing_code_id=code.id,
            code_relation="SAME_CATEGORY", target_object_confirmed=True,
            target_object_role="Vật tích nhiệt", confidence=0.9,
            existing_code_evaluations=[{
                "code_id": code.id, "relation": "SAME_CATEGORY", "verdict": "MATCH",
                "goal_match": True,
            }],
        )])
        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )
        assert not uncertain
        assert mapping.ideas[0].code == code.name
        assert code.centroid_count == 1
        assert code.centroid == [1.0, 0.0]


def test_failed_policy_gate_does_not_mutate_codebook():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="gach", name="Gạch", description="Một viên gạch")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()
        signature = FunctionalSignature(
            goal="giữ ấm", object_role="vật tích nhiệt", mechanism="truyền nhiệt"
        )
        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="Nung gạch để sưởi",
                    normalized="Dùng gạch nóng để giữ ấm",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Gạch",
                    target_object_role="Vật tích nhiệt",
                    functional_signature=signature,
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Giữ ấm chân",
                    code_description="Dùng gạch nóng để giữ ấm chân.",
                    target_object_confirmed=True,
                    target_object_role="Vật tích nhiệt",
                    functional_signature=signature,
                    policy_gates={"response_is_valid": True},
                    confidence=0.99,
                )
            ]
        )
        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )
        assert uncertain is True
        assert mapping.ideas[0].status == "VALID"
        assert mapping.ideas[0].code is None
        assert db.scalar(select(ItemCode)) is None


def test_new_code_with_true_gates_but_no_boundaries_is_rejected():
    """Backend không tin `counterexample_passed` nếu model không trả ranh giới cụ thể."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="gach", name="Gạch", description="Một viên gạch")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()
        signature = FunctionalSignature(
            goal="giữ ấm",
            object_role="vật tích nhiệt",
            mechanism="truyền nhiệt",
        )
        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="Nung gạch để sưởi",
                    normalized="Dùng gạch nóng để giữ ấm",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Gạch",
                    target_object_role="Vật tích nhiệt",
                    functional_signature=signature,
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Tích và truyền nhiệt",
                    code_description="Dùng gạch làm vật tích và truyền nhiệt.",
                    target_object_confirmed=True,
                    target_object_role="Vật tích nhiệt",
                    functional_signature=signature,
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
                )
            ]
        )

        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )

        assert uncertain is True
        assert mapping.ideas[0].curator_decision == "POLICY_REJECTED"
        assert "thiếu quy tắc" in mapping.ideas[0].reason.lower()
        assert db.scalar(select(ItemCode)) is None


def test_broader_idea_expands_narrow_code_and_records_scope_history():
    """Ý “đồ trang sức” mở rộng code “vòng tay” tại chỗ, không tạo code song song."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại")
        response = _response(participant.id, item.id)
        narrow_code = ItemCode(
            item_id=item.id,
            name="Làm vòng đeo tay từ vỏ đạn",
            normalized_name="lam vong deo tay tu vo dan",
            description="Gia công vỏ đạn thành vòng đeo ở cổ tay.",
            functional_signature={
                "goal": "trang trí cổ tay",
                "object_role": "vật liệu phụ kiện đeo",
                "mechanism": "gia công và nối",
            },
            inclusion_rules=["Vòng đeo ở cổ tay"],
            exclusion_rules=["Đồ trang trí không đeo"],
            positive_examples=["Làm vòng đeo tay"],
            confidence=0.9,
        )
        db.add_all([participant, item, response, narrow_code])
        db.flush()
        signature = FunctionalSignature(
            goal="trang trí cơ thể",
            object_role="vật liệu trang sức hoặc phụ kiện đeo",
            mechanism="gia công và lắp ghép thành vật đeo",
        )
        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="làm đồ trang sức",
                    normalized="Làm đồ trang sức từ vỏ đạn",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Vỏ đạn",
                    target_object_role="Vật liệu trang sức",
                    functional_signature=signature,
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="EXPAND_EXISTING",
                    code_relation="IDEA_BROADER_THAN_CODE",
                    existing_code_id=narrow_code.id,
                    code_name="Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn",
                    code_description=(
                        "Gia công vỏ đạn thành đồ trang sức hoặc phụ kiện được đeo trên cơ thể."
                    ),
                    target_object_confirmed=True,
                    target_object_role="Vật liệu trang sức",
                    functional_signature=signature,
                    inclusion_rules=["Vòng tay, vòng cổ, nhẫn và phụ kiện đeo"],
                    exclusion_rules=["Đồ trang trí không đeo trên cơ thể"],
                    positive_examples=["Làm vòng đeo tay", "Làm đồ trang sức"],
                    reviewed_by_challenger=True,
                    confidence=0.94,
                )
            ]
        )

        mapping, uncertain = persist_mapping(
            db, item=item, response=response, extraction=extraction, curator=curator
        )

        assert uncertain is False
        assert mapping.ideas[0].code == "Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn"
        assert len(db.scalars(select(ItemCode)).all()) == 1
        assert narrow_code.name == "Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn"
        assert narrow_code.scope_history[-1]["change"] == "AUTO_SCOPE_EXPANSION"


def test_persist_mapping_keeps_extraction_signature_separate_from_curator_signature():
    """Dấu vết ý gốc không được biến thành chữ ký của category đã chọn."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="vo_dan", name="Vỏ đạn", description="Vỏ kim loại")
        response = _response(participant.id, item.id)
        code = ItemCode(
            item_id=item.id,
            name="Chậu cây",
            normalized_name="chau cay",
            description="Dùng vỏ đạn làm chậu trồng cây",
            functional_signature={
                "goal": "trồng trọt",
                "object_role": "chậu",
                "mechanism": "chứa đất",
            },
            confidence=0.9,
        )
        db.add_all([participant, item, response, code])
        db.flush()
        idea_signature = FunctionalSignature(
            goal="đậy kín",
            object_role="nắp",
            mechanism="đậy lên",
        )
        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="làm nắp chai",
                    normalized="Đậy chai",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Vỏ đạn",
                    target_object_role="Nắp đậy",
                    functional_signature=idea_signature,
                )
            ]
        )
        curator_signature = FunctionalSignature(
            goal="trồng trọt",
            object_role="chậu",
            mechanism="chứa đất",
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="MATCH_EXISTING",
                    existing_code_id=code.id,
                    code_relation="SAME_CATEGORY",
                    target_object_confirmed=True,
                    target_object_role="Nắp đậy",
                    functional_signature=curator_signature,
                    existing_code_evaluations=[
                        {
                            "code_id": code.id,
                            "relation": "SAME_CATEGORY",
                            "goal_match": True,
                            "role_match": True,
                            "mechanism_match": True,
                            "excluded_by": "",
                            "verdict": "MATCH",
                        }
                    ],
                    confidence=0.8,
                )
            ]
        )

        mapping, _ = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=curator,
        )
        stored = db.scalar(select(ResponseIdea))

        assert stored.functional_signature == idea_signature.model_dump()
        assert mapping.ideas[0].functional_signature == idea_signature
        assert stored.mapping_evidence["curator_functional_signature"] == (
            curator_signature.model_dump()
        )


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _response(participant_id: str, item_id: str) -> Response:
    return Response(
        participant_id=participant_id,
        item_id=item_id,
        raw_input="làm dấu trang",
        mapping={},
        scoring={},
    )


def test_empty_responses_do_not_open_sample_threshold():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="dua", name="Đũa", description="Đôi đũa")
        db.add_all([participant, item])
        db.commit()

        db.add_all([
            _response(participant.id, item.id),
            _response(participant.id, item.id),
        ])
        db.commit()
        assert qualifying_response_count(db, item.id) == 0


def test_item_stays_active_after_reaching_people_and_idea_thresholds():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(
            id="dua",
            name="Đũa",
            description="Đôi đũa",
            scoring_min_participants=1,
            scoring_min_ideas=1,
        )
        code = ItemCode(
            item_id=item.id,
            name="Nhạc cụ",
            normalized_name="nhac cu",
            confidence=0.95,
        )
        db.add_all([participant, item, code])
        db.flush()

        first = _response(participant.id, item.id)
        db.add(first)
        db.flush()
        db.add(
            ResponseIdea(
                response_id=first.id,
                code_id=code.id,
                original="gõ nhịp",
                normalized="Dùng làm thanh gõ nhịp",
                mapping_status="VALID",
                confidence=0.95,
            )
        )
        db.flush()
        assert refresh_item_scoring_state(db, item) is True
        assert item.calibration_status.value == "ACTIVE"

        second = _response(participant.id, item.id)
        db.add(second)
        db.flush()
        db.add(
            ResponseIdea(
                response_id=second.id,
                code_id=code.id,
                original="gõ trống",
                normalized="Dùng làm dùi gõ trống",
                mapping_status="VALID",
                confidence=0.95,
            )
        )
        db.flush()
        assert refresh_item_scoring_state(db, item) is False
        assert item.calibration_status.value == "ACTIVE"


def test_item_waits_for_both_people_and_valid_idea_thresholds():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(
            id="chai",
            name="Chai nhựa",
            description="Một chai nhựa",
            scoring_min_participants=2,
            scoring_min_ideas=2,
        )
        p1, p2 = Participant(id=str(uuid.uuid4())), Participant(id=str(uuid.uuid4()))
        code = ItemCode(
            item_id=item.id,
            name="Dụng cụ tưới",
            normalized_name="dung cu tuoi",
            confidence=0.95,
        )
        db.add_all([item, p1, p2, code])
        db.flush()

        first = _response(p1.id, item.id)
        db.add(first)
        db.flush()
        db.add(
            ResponseIdea(
                response_id=first.id,
                code_id=code.id,
                original="tưới cây",
                normalized="Dùng làm bình tưới cây",
                mapping_status="VALID",
                confidence=0.95,
            )
        )
        db.flush()
        assert refresh_item_scoring_state(db, item) is False
        assert item.calibration_status.value == "COLLECTING"

        second = _response(p2.id, item.id)
        db.add(second)
        db.flush()
        db.add(
            ResponseIdea(
                response_id=second.id,
                code_id=code.id,
                original="tưới hoa",
                normalized="Dùng làm bình tưới hoa",
                mapping_status="VALID",
                confidence=0.95,
            )
        )
        db.flush()

        assert qualifying_idea_count(db, item.id) == 2
        assert refresh_item_scoring_state(db, item) is True
        assert item.calibration_status.value == "ACTIVE"


def test_realtime_frequency_uses_idea_share_not_submission_share():
    """Một lượt có nhiều ý phải đóng góp từng ý vào mẫu số theo công thức AUT."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(
            id="chai",
            name="Chai nhựa",
            description="Một chai nhựa",
            scoring_min_participants=2,
            scoring_min_ideas=2,
        )
        p1, p2 = Participant(id=str(uuid.uuid4())), Participant(id=str(uuid.uuid4()))
        code_a = ItemCode(
            item_id=item.id,
            name="Bình tưới",
            normalized_name="binh tuoi",
            confidence=0.95,
        )
        code_b = ItemCode(
            item_id=item.id,
            name="Chậu cây",
            normalized_name="chau cay",
            confidence=0.95,
        )
        db.add_all([item, p1, p2, code_a, code_b])
        db.flush()

        first = _response(p1.id, item.id)
        second = _response(p2.id, item.id)
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                ResponseIdea(
                    response_id=first.id,
                    code_id=code_a.id,
                    original="tưới cây",
                    normalized="Dùng làm bình tưới cây",
                    mapping_status="VALID",
                    confidence=0.95,
                ),
                ResponseIdea(
                    response_id=first.id,
                    code_id=code_b.id,
                    original="trồng cây",
                    normalized="Dùng làm chậu trồng cây",
                    mapping_status="VALID",
                    confidence=0.95,
                ),
                ResponseIdea(
                    response_id=second.id,
                    code_id=code_a.id,
                    original="tưới hoa",
                    normalized="Dùng làm bình tưới hoa",
                    mapping_status="VALID",
                    confidence=0.95,
                ),
                ResponseIdea(
                    response_id=second.id,
                    code_id=code_a.id,
                    original="có thể là bình tưới",
                    normalized="Có thể dùng làm bình tưới",
                    mapping_status="VALID",
                    confidence=0.50,
                    reason="AI chưa chắc ý này khớp với mã bình tưới.",
                ),
            ]
        )
        db.flush()

        _, _, _, _, basis = originality_for_response(db, first)
        frequencies = {
            row["code_id"]: row["frequency"] for row in basis["code_frequencies"]
        }
        assert frequencies[code_a.id] == pytest.approx(3 / 4)
        assert frequencies[code_b.id] == pytest.approx(1 / 4)
        assert sum(frequencies.values()) == pytest.approx(1.0)


def test_curator_nullable_optional_text_is_normalized():
    """Output JSON `null` của LLM không được làm hỏng toàn bộ lượt submit."""
    result = CuratorResult.model_validate(
        {
            "decisions": [
                {
                    "idea_index": 3,
                    "decision": "MATCH_EXISTING",
                    "existing_code_id": "code-1",
                    "code_name": None,
                    "code_description": None,
                    "functional_signature": None,
                    "existing_code_evaluations": None,
                    "retrieval_candidates": None,
                    "inclusion_rules": None,
                    "exclusion_rules": None,
                    "positive_examples": None,
                    "scope_variants": None,
                    "nearest_code_ids": None,
                    "policy_gates": None,
                    "absorbed_code_ids": None,
                    "confidence": 0.94,
                    "reason": None,
                }
            ]
        }
    )

    assert result.decisions[0].code_description == ""
    assert result.decisions[0].reason == ""
    assert result.decisions[0].functional_signature == FunctionalSignature()
    assert result.decisions[0].scope_variants == []
    assert result.decisions[0].inclusion_rules == []
    assert result.decisions[0].exclusion_rules == []
    assert result.decisions[0].absorbed_code_ids == []
    assert result.decisions[0].policy_gates == {}


def test_inferred_goal_cannot_create_code_automatically():
    """Một mục đích không có trong câu nguồn chỉ được giữ làm đề xuất chờ duyệt."""
    idea = ExtractedIdea(
        line_index=0,
        original="Cắt vụn ra thành nhiều mảnh",
        normalized="Cắt balo thành nhiều mảnh để làm nguyên liệu thủ công",
        status="VALID",
        uses_target_object=True,
        object_used="Balo quân nhu",
        target_object_role="Nguồn vật liệu",
        functional_signature=FunctionalSignature(
            goal="tạo nguyên liệu thủ công",
            object_role="nguồn vật liệu",
            mechanism="cắt thành mảnh nhỏ",
        ),
        functional_evidence={
            "goal": "",
            "object_role": "",
            "mechanism": "Cắt vụn ra thành nhiều mảnh",
        },
        inferred_signature_fields=["goal", "object_role"],
    )
    decision = CuratorDecision(
        idea_index=0,
        decision="CREATE_NEW",
        code_relation="DIFFERENT",
        code_name="Nguyên liệu thủ công từ balo quân nhu",
        confidence=0.9,
    )

    guarded = _guard_ungrounded_creations(
        CuratorResult(decisions=[decision]), IdeaExtractionResult(ideas=[idea])
    )

    assert guarded.decisions[0].decision == "UNCERTAIN"
    assert guarded.decisions[0].policy_gates["goal_grounded_in_source"] is False


def test_same_container_function_with_different_targets_triggers_reconciliation():
    """Target quân sự/học tập không được né bước chống trùng khi vai trò và cơ chế chứa giống nhau."""
    decisions = [
        CuratorDecision(
            idea_index=0,
            decision="CREATE_NEW",
            code_name="Chứa đồ dùng quân sự",
            confidence=0.9,
            functional_signature=FunctionalSignature(
                goal="chứa thiết bị quân sự",
                object_role="vật chứa đeo lưng",
                mechanism="xếp đồ vào các ngăn",
            ),
        ),
        CuratorDecision(
            idea_index=1,
            decision="CREATE_NEW",
            code_name="Chứa đồ dùng học tập",
            confidence=0.9,
            functional_signature=FunctionalSignature(
                goal="mang sách vở học tập",
                object_role="túi chứa đeo lưng",
                mechanism="đặt đồ vào ngăn chính",
            ),
        ),
    ]

    overlaps = _potential_new_code_overlaps(decisions)

    assert [(row["left_idea_index"], row["right_idea_index"]) for row in overlaps] == [
        (0, 1)
    ]


def test_semantic_goal_paraphrase_is_not_treated_as_hallucination():
    """Câu ngắn đã nêu công dụng không phải trích đúng nhãn goal do LLM chuẩn hoá."""
    common = {
        "normalized": "Dùng balo quân nhu làm nhiên liệu đốt",
        "status": "VALID",
        "uses_target_object": True,
        "object_used": "Balo quân nhu",
        "target_object_role": "Vật liệu cháy",
        "functional_signature": FunctionalSignature(
            goal="tạo nhiệt hoặc lửa",
            object_role="vật liệu cháy",
            mechanism="bắt lửa và duy trì sự cháy",
        ),
        "functional_evidence": {"goal": "", "object_role": "", "mechanism": ""},
        "inferred_signature_fields": ["goal", "object_role", "mechanism"],
    }

    fuel = ExtractedIdea(original="dùng làm nguyên liệu đốt", **common)
    cover = ExtractedIdea(original="trùm lên đầu bạn bè", **common)
    fragments = ExtractedIdea(original="cắt vụn ra thành nhiều mảnh", **common)

    assert _creation_goal_is_grounded(fuel) is True
    assert _creation_goal_is_grounded(cover) is True
    assert _creation_goal_is_grounded(fragments) is False


def test_low_vector_margin_is_allowed_when_goal_clearly_beats_runner_up():
    """Mô hình ô tô vẫn match mã mô hình dù embedding của mã trang sức đứng khá gần."""
    idea = ExtractedIdea(
        original="lấy keo dính lại thành ô tô bằng đạn",
        normalized="Ghép vỏ đạn thành mô hình ô tô",
        status="VALID",
        uses_target_object=True,
        object_used="Vỏ đạn",
        target_object_role="Vật liệu chế tạo",
        functional_signature=FunctionalSignature(
            goal="tạo mô hình ô tô",
            object_role="vật liệu chế tạo",
            mechanism="ghép nối bằng keo",
        ),
    )
    decision = CuratorDecision(
        idea_index=0,
        decision="MATCH_EXISTING",
        code_relation="SAME_CATEGORY",
        existing_code_id="model",
        target_object_confirmed=True,
        target_object_role="Vật liệu chế tạo",
        confidence=0.9,
        retrieval_candidates=[
            {
                "code_id": "model",
                "retrieval_score": 0.594703,
                "semantic_similarity": 0.708176,
                "signature_similarity": {
                    "goal": 0.6,
                    "object_role": 0.0,
                    "mechanism": 0.047619,
                    "weighted": 0.254286,
                },
            },
            {
                "code_id": "jewelry",
                "retrieval_score": 0.56021,
                "semantic_similarity": 0.682468,
                "signature_similarity": {
                    "goal": 0.0,
                    "object_role": 0.428571,
                    "mechanism": 0.216216,
                    "weighted": 0.193436,
                },
            },
        ],
    )

    assert _stored_match_review_reason(idea, decision) is None


def test_final_persistence_rejects_wrong_rank_two_match_even_if_llm_selects_it():
    """MATCH nhiên liệu -> chứa đồ bị chặn trong transaction cuối, không phụ thuộc tầng trước."""
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="balo", name="Balo quân nhu", description="Balo có khoang và quai đeo")
        response = _response(participant.id, item.id)
        container = ItemCode(
            item_id=item.id,
            name="Chứa và vận chuyển đồ dùng bằng balo quân nhu",
            normalized_name="chua va van chuyen do dung bang balo quan nhu",
            description="Dùng balo quân nhu để chứa và mang đồ dùng.",
        )
        db.add_all([participant, item, response, container])
        db.flush()
        signature = FunctionalSignature(
            goal="tạo nhiệt hoặc lửa",
            object_role="vật liệu cháy",
            mechanism="bắt lửa và duy trì sự cháy",
        )
        extraction = IdeaExtractionResult(ideas=[ExtractedIdea(
            original="dùng làm nguyên liệu đốt",
            normalized="Dùng balo làm nhiên liệu đốt",
            status="VALID",
            uses_target_object=True,
            object_used="Balo quân nhu",
            target_object_role="Vật liệu cháy",
            functional_signature=signature,
        )])
        decision = CuratorDecision(
            idea_index=0,
            decision="MATCH_EXISTING",
            code_relation="SAME_CATEGORY",
            existing_code_id=container.id,
            target_object_confirmed=True,
            target_object_role="Nhiên liệu",
            confidence=0.9,
            functional_signature=signature,
            retrieval_candidates=[
                {
                    "code_id": "training-weight",
                    "retrieval_score": 0.427907,
                    "semantic_similarity": 0.538615,
                    "signature_similarity": {"goal": 0.09, "weighted": 0.09},
                },
                {
                    "code_id": container.id,
                    "retrieval_score": 0.410616,
                    "semantic_similarity": 0.528855,
                    "signature_similarity": {"goal": 0.0, "weighted": 0.055901},
                },
            ],
        )

        mapping, uncertain = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=CuratorResult(decisions=[decision]),
        )
        saved = db.scalar(select(ResponseIdea))

        assert uncertain is True
        assert mapping.ideas[0].code is None
        assert saved.code_id is None
        assert saved.curator_decision == "MATCH_GUARD_REJECTED"
        assert "hạng 2" in saved.reason


def test_duplicate_decision_index_is_dropped_instead_of_taking_last_value():
    decisions = CuratorResult(decisions=[
        CuratorDecision(
            idea_index=0,
            decision="MATCH_EXISTING",
            existing_code_id="fuel",
            confidence=0.8,
        ),
        CuratorDecision(
            idea_index=0,
            decision="MATCH_EXISTING",
            existing_code_id="container",
            confidence=0.8,
        ),
        CuratorDecision(idea_index=1, decision="UNCERTAIN", confidence=0.5),
    ])

    accepted, duplicates, unexpected = _one_decision_per_index(decisions, {0, 1})

    assert [decision.idea_index for decision in accepted.decisions] == [1]
    assert duplicates == {0}
    assert unexpected == set()


def test_extraction_object_guard_rejects_another_object():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="day_thung", name="Dây thừng", description="Dùng để buộc")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()

        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="Gấp giấy báo để bọc quà",
                    normalized="Dùng giấy báo bọc quà",
                    status="VALID",
                    uses_target_object=False,
                    object_used="Giấy báo",
                    target_object_role="",
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Bọc quà bằng giấy báo",
                    code_description="Dùng giấy báo để bọc quà",
                    confidence=0.99,
                )
            ]
        )

        mapping, _ = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=curator,
        )
        idea = db.scalar(select(ResponseIdea).where(ResponseIdea.response_id == response.id))
        assert mapping.ideas[0].status == "INVALID"
        assert idea.curator_decision == "EXTRACTION_OBJECT_GUARD"
        assert db.scalars(select(ItemCode)).all() == []


def test_curator_cannot_create_code_for_another_object():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        participant = Participant(id=str(uuid.uuid4()))
        item = Item(id="day_thung", name="Dây thừng", description="Dùng để buộc")
        response = _response(participant.id, item.id)
        db.add_all([participant, item, response])
        db.flush()

        extraction = IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="Làm dây phơi",
                    normalized="Dùng làm dây phơi",
                    status="VALID",
                    uses_target_object=True,
                    object_used="Dây thừng",
                    target_object_role="Chịu lực để treo quần áo",
                )
            ]
        )
        curator = CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Bọc quà bằng giấy báo",
                    code_description="Dùng giấy báo để bọc quà",
                    target_object_confirmed=True,
                    target_object_role="Chịu lực",
                    confidence=0.99,
                )
            ]
        )

        mapping, _ = persist_mapping(
            db,
            item=item,
            response=response,
            extraction=extraction,
            curator=curator,
        )
        assert mapping.ideas[0].status == "VALID"
        assert mapping.ideas[0].curator_decision == "CURATOR_OBJECT_GUARD"
        assert db.scalar(select(ItemCode)) is None


def test_curator_does_not_receive_off_object_existing_codes():
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        item = Item(id="day_thung", name="Dây thừng", description="Dùng để buộc")
        db.add_all(
            [
                item,
                ItemCode(
                    item_id=item.id,
                    name="Bọc quà bằng giấy báo",
                    normalized_name="boc qua bang giay bao",
                    description="Dùng giấy báo để bọc quà",
                ),
                ItemCode(
                    item_id=item.id,
                    name="Làm dây phơi bằng dây thừng",
                    normalized_name="lam day phoi bang day thung",
                    description="Dùng dây thừng chịu lực để treo quần áo",
                ),
            ]
        )
        db.flush()

        codes = list_curator_codes(db, item.id)
        assert [code["name"] for code in codes] == ["Làm dây phơi bằng dây thừng"]

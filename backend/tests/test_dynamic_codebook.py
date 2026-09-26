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
from app.pipeline.code_retrieval import rank_code_candidates
from app.pipeline.dynamic_mapping import run_code_curator, run_idea_extraction
from app.schemas.schemas import (
    CuratorDecision,
    CuratorResult,
    ExtractedIdea,
    IdeaExtractionResult,
    FunctionalSignature,
    ScoreRequest,
)
from tests.fake_llm import FakeClient


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


def test_overlapping_new_codes_in_same_submission_are_reconciled():
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


def test_new_code_requires_all_policy_gates_and_is_active_immediately():
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
                    positive_examples=["Nung gạch để sưởi chân"],
                    policy_gates={
                        "response_is_valid": True,
                        "no_existing_code_covers": True,
                        "functionally_distinct": True,
                        "granularity_consistent": True,
                        "paraphrase_stable": True,
                        "counterexample_passed": True,
                    },
                    reviewed_by_challenger=True,
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
                    existing_code_evaluations=[
                        {
                            "code_id": narrow_code.id,
                            "relation": "IDEA_BROADER_THAN_CODE",
                            "verdict": "EXPAND",
                        }
                    ],
                    policy_gates={
                        "same_functional_family": True,
                        "broader_scope_justified": True,
                        "previous_examples_preserved": True,
                        "hard_negatives_excluded": True,
                        "no_overlap_after_change": True,
                    },
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


def test_repeat_responses_are_all_qualifying_data():
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
        assert qualifying_response_count(db, item.id) == 2


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
                    "confidence": 0.94,
                    "reason": None,
                }
            ]
        }
    )

    assert result.decisions[0].code_description == ""
    assert result.decisions[0].reason == ""


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

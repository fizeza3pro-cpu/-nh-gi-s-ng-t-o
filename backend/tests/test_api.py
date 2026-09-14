import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.controllers import response_controller
from app.db import Base, get_db
from app.main import app
from app.models.models import Item, Participant, Response
from app.core.deps import require_admin
from app.schemas.schemas import CuratorDecision, CuratorResult, ExtractedIdea, IdeaExtractionResult


@pytest.fixture()
def client(monkeypatch):
    """Dùng SQLite cô lập để test API không phụ thuộc PostgreSQL thật."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Item(
                id="dua",
                name="Đũa",
                description="Một đôi đũa",
            )
        )
        db.commit()

    def override_get_db():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr(main_mod.settings, "mock_mode", True)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def create_participant(client: TestClient, email: str | None = None) -> str:
    email = email or f"participant-{uuid.uuid4()}@example.test"
    response = client.post(
        "/api/participants",
        json={
            "email": email,
            "full_name": "Nguyễn Minh Anh",
            "age": 20,
            "gender": "female",
            "occupation": "Sinh viên",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def uncertain_mapping(item, _raw, _existing_codes):
    """Sinh một mã có độ tin cậy thấp để kiểm tra quyết định của admin."""
    return (
        IdeaExtractionResult(
            ideas=[
                ExtractedIdea(
                    original="làm móc treo",
                    normalized="Dùng đũa làm móc treo",
                    status="VALID",
                    uses_target_object=True,
                    object_used=item.name,
                    target_object_role="Đũa làm phần móc chịu lực.",
                )
            ]
        ),
        CuratorResult(
            decisions=[
                CuratorDecision(
                    idea_index=0,
                    decision="CREATE_NEW",
                    code_name="Móc treo từ đũa",
                    code_description="Dùng đũa làm móc treo đồ vật.",
                    target_object_confirmed=True,
                    target_object_role="Đũa làm phần móc chịu lực.",
                    confidence=0.50,
                    reason="AI chưa đủ chắc chắn về phạm vi công dụng.",
                )
            ]
        ),
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_items_are_public(client):
    response = client.get("/api/items")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {"dua"}
    assert "codes" not in response.json()[0]


def test_empty_admin_dashboard_still_lists_all_items(client):
    app.dependency_overrides[require_admin] = lambda: object()
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_responses"] == 0
    assert payload["qualifying_response_count"] == 0
    assert payload["scoring_status_counts"]["collecting"] == 0
    assert payload["by_item"][0]["item_id"] == "dua"
    assert payload["by_item"][0]["response_count"] == 0


def test_participant_is_idempotent(client):
    email = "same-person@example.test"
    participant_id = create_participant(client, email)
    response = client.post(
        "/api/participants",
        json={
            "email": email.upper(),
            "full_name": "Tên gửi lại không ghi đè",
            "age": 99,
            "gender": "male",
            "occupation": "Dữ liệu retry không ghi đè",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == participant_id
    assert response.json()["full_name"] == "Nguyễn Minh Anh"
    assert "age" not in response.json()
    assert "gender" not in response.json()
    assert "occupation" not in response.json()


def test_email_identifies_returning_participant(client):
    first_lookup = client.post(
        "/api/participants/identify", json={"email": "returning@example.test"}
    )
    assert first_lookup.status_code == 200
    assert first_lookup.json() == {"profile_required": True, "participant": None}

    participant_id = create_participant(client, "returning@example.test")
    returning = client.post(
        "/api/participants/identify", json={"email": " RETURNING@example.test "}
    )
    assert returning.status_code == 200
    assert returning.json()["profile_required"] is False
    assert returning.json()["participant"]["id"] == participant_id
    assert returning.json()["participant"]["full_name"] == "Nguyễn Minh Anh"
    assert returning.json()["participant"]["email_verified_at"] is None
    assert returning.json()["participant"]["email_masked"].endswith("@example.test")
    assert "age" not in returning.json()["participant"]
    assert "gender" not in returning.json()["participant"]
    assert "occupation" not in returning.json()["participant"]

    app.dependency_overrides[require_admin] = lambda: object()
    participants = client.get("/api/admin/participants")
    detail = client.get(f"/api/admin/participants/{participant_id}")
    assert participants.status_code == 200
    assert participants.json()[0]["full_name"] == "Nguyễn Minh Anh"
    assert detail.status_code == 200
    assert detail.json()["participant"]["full_name"] == "Nguyễn Minh Anh"


def test_legacy_participant_can_add_missing_full_name(client):
    """Participant cũ chưa có tên được yêu cầu bổ sung và không bị tạo bản ghi trùng."""
    email = "legacy-name@example.test"
    participant_id = create_participant(client, email)

    db_dependency = app.dependency_overrides[get_db]()
    db = next(db_dependency)
    try:
        participant = db.get(Participant, participant_id)
        assert participant is not None
        participant.full_name = None
        participant.email_hash = None
        participant.email_masked = None
        db.commit()
    finally:
        db_dependency.close()

    identify = client.post(
        "/api/participants/identify",
        json={"email": email, "participant_id": participant_id},
    )
    assert identify.status_code == 200
    assert identify.json() == {"profile_required": True, "participant": None}

    completed = client.post(
        "/api/participants",
        json={
            "email": email,
            "full_name": "  Trần   Thu Hà  ",
            "age": 21,
            "gender": "female",
            "occupation": "Sinh viên",
        },
    )
    assert completed.status_code == 201
    assert completed.json()["id"] == participant_id
    assert completed.json()["full_name"] == "Trần Thu Hà"


def test_score_requires_participant(client):
    response = client.post(
        "/api/score", json={"item_id": "dua", "raw_input": "gõ nhịp"}
    )
    assert response.status_code == 401


def test_score_and_public_result_roundtrip(client):
    participant_id = create_participant(client)
    response = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "gõ nhịp, làm cọc cây"},
    )
    assert response.status_code == 200
    assert response.json()["scoring"] is None
    assert response.json()["scoring_status"] == "COLLECTING"
    response_id = response.json()["response_id"]

    detail = client.get(f"/api/responses/{response_id}")
    assert detail.status_code == 200
    assert detail.json()["response_id"] == response_id

    # Danh sách toàn bộ lượt làm vẫn là dữ liệu quản trị.
    assert client.get("/api/responses").status_code == 401


def test_invalid_participant_id_rejected(client):
    response = client.post(
        "/api/score",
        headers={"X-Participant-Id": "not-a-uuid"},
        json={"item_id": "dua", "raw_input": "gõ nhịp"},
    )
    assert response.status_code == 400


def test_admin_can_observe_ai_generated_codes(client):
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    )
    assert submitted.status_code == 200

    app.dependency_overrides[require_admin] = lambda: object()
    response = client.get("/api/admin/items/codebooks")
    assert response.status_code == 200
    codebook = response.json()[0]
    assert codebook["calibration_status"] == "COLLECTING"
    assert codebook["qualifying_participant_count"] == 1
    assert codebook["codes"][0]["validation_status"] == "ACCEPTED"
    assert codebook["codes"][0]["response_count"] == 1
    assert codebook["codes"][0]["contributing_response_count"] == 1
    assert codebook["codes"][0]["contributing_idea_count"] == 1


def test_admin_sees_all_mapping_evidence_and_curator_decisions(client):
    participant_id = create_participant(client)
    headers = {"X-Participant-Id": participant_id}
    payload = {"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"}

    assert client.post("/api/score", headers=headers, json=payload).status_code == 200
    # Lượt lặp cũng đóng góp vào tần suất và là bằng chứng Curator đã match code.
    assert client.post("/api/score", headers=headers, json=payload).status_code == 200

    app.dependency_overrides[require_admin] = lambda: object()
    codebook = client.get("/api/admin/items/dua/codebook").json()
    assert codebook["qualifying_response_count"] == 2
    assert codebook["qualifying_participant_count"] == 1
    assert codebook["contributing_idea_count"] == 2
    code = codebook["codes"][0]
    assert code["response_count"] == 2
    assert code["participant_count"] == 1
    assert code["idea_count"] == 2
    assert code["contributing_response_count"] == 2
    assert code["contributing_participant_count"] == 1
    assert code["contributing_idea_count"] == 2
    assert code["frequency"] == 1.0

    audit = client.get("/api/admin/items/dua/curator-audit")
    assert audit.status_code == 200
    decisions = audit.json()
    assert decisions["create_new_count"] == 1
    assert decisions["match_existing_count"] == 1
    assert decisions["invalid_count"] == 0
    assert {row["decision"] for row in decisions["decisions"]} == {
        "CREATE_NEW",
        "MATCH_EXISTING",
    }
    assert all(row["code_name"] == "làm cọc đánh dấu cây" for row in decisions["decisions"])


def test_admin_can_audit_ideas_rejected_by_extraction(client, monkeypatch):
    def mock_extraction(_item, _raw, _existing_codes):
        return (
            IdeaExtractionResult(
                ideas=[
                    ExtractedIdea(
                        original="trời hôm nay đẹp",
                        normalized="trời hôm nay đẹp",
                        status="INVALID",
                        reason="Không mô tả cách sử dụng đồ vật.",
                    ),
                    ExtractedIdea(
                        original="làm cọc lần nữa",
                        normalized="làm cọc đánh dấu",
                        status="DUPLICATE",
                        reason="Trùng công dụng với ý trước.",
                    ),
                ]
            ),
            CuratorResult(decisions=[]),
        )

    monkeypatch.setattr(response_controller, "_mock_mapping", mock_extraction)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "nội dung kiểm thử"},
    )
    assert submitted.status_code == 200

    app.dependency_overrides[require_admin] = lambda: object()
    audit = client.get("/api/admin/items/dua/extraction-audit")
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["invalid_count"] == 1
    assert payload["duplicate_count"] == 1
    assert {idea["status"] for idea in payload["ideas"]} == {"INVALID", "DUPLICATE"}
    assert payload["ideas"][0]["participant_id"] == participant_id

    summary = client.get("/api/admin/items/dua/codebook").json()
    assert summary["extraction_invalid_count"] == 1
    assert summary["extraction_duplicate_count"] == 1


def test_admin_can_audit_an_idea_rejected_by_curator(client, monkeypatch):
    def mock_curator_invalid(item, _raw, _existing_codes):
        return (
            IdeaExtractionResult(
                ideas=[
                    ExtractedIdea(
                        original="ném lên mặt trăng",
                        normalized="ném đũa lên mặt trăng",
                        status="VALID",
                        uses_target_object=True,
                        object_used=item.name,
                        target_object_role="Đũa là vật được ném.",
                    )
                ]
            ),
            CuratorResult(
                decisions=[
                    CuratorDecision(
                        idea_index=0,
                        decision="INVALID",
                        code_name="Ném đũa lên mặt trăng",
                        confidence=0.98,
                        reason="Công dụng bất khả thi.",
                    )
                ]
            ),
        )

    monkeypatch.setattr(response_controller, "_mock_mapping", mock_curator_invalid)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "ném lên mặt trăng"},
    )
    assert submitted.status_code == 200

    app.dependency_overrides[require_admin] = lambda: object()
    audit = client.get("/api/admin/items/dua/curator-audit")
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["invalid_count"] == 1
    assert payload["decisions"][0]["decision"] == "INVALID"
    assert payload["decisions"][0]["code_name"] == "Ném đũa lên mặt trăng"


def test_admin_can_request_full_remap(client, monkeypatch):
    app.dependency_overrides[require_admin] = lambda: object()
    monkeypatch.setattr(
        "app.controllers.admin_controller.reprocess_item_mappings", lambda _item_id: 2
    )
    response = client.post("/api/admin/items/dua/remap")
    assert response.status_code == 200
    assert response.json() == {"processed": 2}


def test_admin_can_accept_an_uncertain_code(client, monkeypatch):
    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm móc treo"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["scoring_status"] == "PENDING_REVIEW"

    app.dependency_overrides[require_admin] = lambda: object()
    before = client.get("/api/admin/items/dua/codebook").json()
    uncertain = before["codes"][0]
    assert uncertain["validation_status"] == "UNCERTAIN"
    assert before["contributing_idea_count"] == 0

    accepted = client.patch(
        f"/api/admin/items/dua/codes/{uncertain['id']}",
        json={"validation_status": "ACCEPTED", "admin_locked": True},
    )
    assert accepted.status_code == 200
    code = accepted.json()["codes"][0]
    assert code["validation_status"] == "ACCEPTED"
    assert code["admin_locked"] is True
    assert code["contributing_idea_count"] == 1
    assert accepted.json()["contributing_idea_count"] == 1

    detail = client.get(f"/api/responses/{submitted.json()['response_id']}").json()
    assert detail["scoring_status"] == "COLLECTING"
    assert detail["mapping"]["ideas"][0]["status"] == "VALID"


def test_accepting_uncertain_code_scores_once_when_item_is_ready(client, monkeypatch):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    item = db.get(Item, "dua")
    item.scoring_min_participants = 1
    item.scoring_min_responses = 1
    db.commit()
    next(database, None)

    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm móc treo"},
    )
    assert submitted.json()["scoring_status"] == "PENDING_REVIEW"

    app.dependency_overrides[require_admin] = lambda: object()
    uncertain = client.get("/api/admin/items/dua/codebook").json()["codes"][0]
    accepted = client.patch(
        f"/api/admin/items/dua/codes/{uncertain['id']}",
        json={"validation_status": "ACCEPTED", "admin_locked": True},
    )
    assert accepted.status_code == 200

    detail = client.get(f"/api/responses/{submitted.json()['response_id']}").json()
    assert detail["scoring_status"] == "FINAL"
    assert detail["scoring"]["fluency"] == 1
    assert detail["scoring"]["flexibility"] == 1


def test_threshold_backfills_once_and_new_data_does_not_change_final_score(client):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    item = db.get(Item, "dua")
    item.scoring_min_participants = 2
    item.scoring_min_responses = 2
    db.commit()
    next(database, None)

    first_participant = create_participant(client, "first@example.test")
    second_participant = create_participant(client, "second@example.test")
    first = client.post(
        "/api/score",
        headers={"X-Participant-Id": first_participant},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    ).json()
    assert first["scoring_status"] == "COLLECTING"

    second = client.post(
        "/api/score",
        headers={"X-Participant-Id": second_participant},
        json={"item_id": "dua", "raw_input": "làm thanh gõ nhịp"},
    ).json()
    assert second["scoring_status"] == "FINAL"
    assert client.get(f"/api/responses/{first['response_id']}").json()["scoring_status"] == "FINAL"

    database = app.dependency_overrides[get_db]()
    db = next(database)
    first_row = db.get(Response, first["response_id"])
    frozen_score = dict(first_row.scoring)
    frozen_scored_at = first_row.scored_at
    frozen_basis = dict(first_row.scoring_meta["frequency_basis"])
    assert frozen_basis["qualifying_response_count"] == 2
    next(database, None)

    third = client.post(
        "/api/score",
        headers={"X-Participant-Id": second_participant},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    ).json()
    assert third["scoring_status"] == "FINAL"

    database = app.dependency_overrides[get_db]()
    db = next(database)
    first_row = db.get(Response, first["response_id"])
    assert first_row.scoring == frozen_score
    assert first_row.scored_at == frozen_scored_at
    assert first_row.scoring_meta["frequency_basis"] == frozen_basis
    next(database, None)


def test_admin_can_reject_an_uncertain_code(client, monkeypatch):
    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm móc treo"},
    )
    app.dependency_overrides[require_admin] = lambda: object()
    uncertain = client.get("/api/admin/items/dua/codebook").json()["codes"][0]

    rejected = client.patch(
        f"/api/admin/items/dua/codes/{uncertain['id']}",
        json={"validation_status": "REJECTED", "admin_locked": True},
    )
    assert rejected.status_code == 200
    code = rejected.json()["codes"][0]
    assert code["validation_status"] == "REJECTED"
    assert code["admin_locked"] is True
    assert code["contributing_idea_count"] == 0

    detail = client.get(f"/api/responses/{submitted.json()['response_id']}").json()
    assert detail["scoring_status"] == "COLLECTING"
    assert detail["mapping"]["ideas"][0]["status"] == "INVALID"
    assert detail["mapping"]["ideas"][0]["is_valid"] is False


def test_admin_can_merge_an_uncertain_code_and_resolve_pending(client, monkeypatch):
    participant_id = create_participant(client)
    accepted_response = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    )
    assert accepted_response.status_code == 200

    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    pending_response = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm móc treo"},
    )
    assert pending_response.json()["scoring_status"] == "PENDING_REVIEW"

    app.dependency_overrides[require_admin] = lambda: object()
    codes = client.get("/api/admin/items/dua/codebook").json()["codes"]
    source = next(code for code in codes if code["validation_status"] == "UNCERTAIN")
    target = next(code for code in codes if code["validation_status"] == "ACCEPTED")
    merged = client.post(
        f"/api/admin/items/dua/codes/{source['id']}/merge",
        json={"target_code_id": target["id"]},
    )
    assert merged.status_code == 200
    merged_source = next(code for code in merged.json()["codes"] if code["id"] == source["id"])
    assert merged_source["maturity_status"] == "MERGED"

    detail = client.get(f"/api/responses/{pending_response.json()['response_id']}").json()
    assert detail["scoring_status"] == "COLLECTING"
    assert detail["mapping"]["ideas"][0]["code"] == target["name"]
    assert detail["mapping"]["ideas"][0]["status"] == "VALID"


def test_admin_can_delete_one_code_without_deleting_raw_response(client):
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    )
    response_id = submitted.json()["response_id"]
    app.dependency_overrides[require_admin] = lambda: object()
    codebook = client.get("/api/admin/items/codebooks").json()[0]
    code_id = codebook["codes"][0]["id"]

    deleted = client.delete(f"/api/admin/items/dua/codes/{code_id}")
    assert deleted.status_code == 200
    assert deleted.json()["codes"] == []

    detail = client.get(f"/api/responses/{response_id}")
    assert detail.status_code == 200
    assert detail.json()["raw_input"] == "làm cọc đánh dấu cây"
    assert detail.json()["scoring"] is None
    assert detail.json()["scoring_status"] == "PENDING_REVIEW"


def test_delete_all_codes_resets_mapping_but_keeps_responses_eligible_for_remap(client):
    participant_id = create_participant(client)
    first = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    )
    app.dependency_overrides[require_admin] = lambda: object()

    reset = client.delete("/api/admin/items/dua/codes")
    assert reset.status_code == 200
    assert reset.json()["codes"] == []
    assert reset.json()["qualifying_participant_count"] == 1
    assert reset.json()["qualifying_response_count"] == 1
    assert reset.json()["calibration_status"] == "COLLECTING"
    assert client.get(f"/api/responses/{first.json()['response_id']}").status_code == 200
    detail = client.get(f"/api/responses/{first.json()['response_id']}").json()
    assert detail["scoring_status"] == "COLLECTING"
    assert detail["scoring"] is None

    # Sau reset, response cũ vẫn đóng góp và response mới được cộng thêm bình thường.
    second = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm thanh chống cây"},
    )
    assert second.status_code == 200
    refreshed = client.get("/api/admin/items/codebooks").json()[0]
    assert refreshed["qualifying_participant_count"] == 1
    assert refreshed["qualifying_response_count"] == 2

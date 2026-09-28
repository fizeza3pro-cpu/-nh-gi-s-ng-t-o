import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.controllers import response_controller
from app.controllers import response_worker
from app.db import Base, get_db
from app.main import app
from app.models.models import (
    CodeMaturityStatus,
    CodeValidationStatus,
    Item,
    ItemCalibrationStatus,
    ItemCode,
    Participant,
    Response,
    ResponseIdea,
    ResponseScoringStatus,
)
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
            "ai_usage_group": "LOW",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_participant_email_does_not_grant_access(client, monkeypatch):
    """Biết email hoặc UUID không đủ để đọc hoặc sửa hồ sơ."""
    monkeypatch.setattr(main_mod.settings, "participant_token_required", True)
    payload = {"email": "secure@example.test", "full_name": "Nguyễn Minh Anh",
               "age": 20, "gender": "female", "occupation": "Sinh viên", "ai_usage_group": "LOW"}
    identity = client.post("/api/participants", json=payload).json()
    assert identity["access_token"]
    assert client.post("/api/participants/identify", json={"email": payload["email"]}).status_code == 403
    assert client.post("/api/participants", json={**payload, "full_name": "Người khác"}).status_code == 403
    headers = {"X-Participant-Id": identity["id"]}
    assert client.get("/api/participants/me/responses", headers=headers).status_code == 401
    headers["X-Participant-Token"] = identity["access_token"]
    assert client.get("/api/participants/me/responses", headers=headers).status_code == 200
    restored = client.post("/api/participants/identify", json={
        "email": payload["email"], "access_token": identity["access_token"]})
    assert restored.status_code == 200
    assert restored.json()["participant"]["id"] == identity["id"]


def test_survey_session_enforces_deadline_and_idempotency(client, monkeypatch):
    """Một phiên có đồng hồ server và chỉ nhận một nội dung dù đổi request_id."""
    from app.models.models import SurveySession
    monkeypatch.setattr(main_mod.settings, "survey_session_required", True)
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    headers = {"X-Participant-Id": create_participant(client)}
    payload = {"item_id": "dua", "responses": ["làm móc treo"], "wait_for_completion": False}
    assert client.post("/api/score", headers=headers, json=payload).status_code == 400
    assert client.post("/api/survey-sessions", headers=headers,
                       json={"item_id": "dua", "consent": False}).status_code == 400
    session = client.post("/api/survey-sessions", headers=headers,
                          json={"item_id": "dua", "consent": True}).json()
    assert (datetime.fromisoformat(session["deadline_at"]) - datetime.fromisoformat(session["started_at"])).total_seconds() == 180
    repeated = client.post("/api/survey-sessions", headers=headers,
                           json={"item_id": "dua", "consent": True}).json()
    assert repeated["id"] == session["id"]
    payload["survey_session_id"] = session["id"]
    first = client.post("/api/score", headers=headers, json=payload)
    assert first.status_code == 200
    assert client.post("/api/score", headers=headers, json=payload).json()["response_id"] == first.json()["response_id"]
    assert client.post("/api/score", headers=headers, json={**payload, "responses": ["ý khác"]}).status_code == 409
    second = client.post("/api/survey-sessions", headers=headers,
                         json={"item_id": "dua", "consent": True}).json()
    database = app.dependency_overrides[get_db]()
    db = next(database)
    db.get(SurveySession, second["id"]).deadline_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    db.commit()
    next(database, None)
    assert client.post("/api/score", headers=headers,
                       json={**payload, "survey_session_id": second["id"]}).status_code == 409
    other = {"X-Participant-Id": create_participant(client)}
    assert client.post("/api/score", headers=other, json=payload).status_code == 403


def test_analysis_export_is_private_and_checksummed(client):
    import hashlib
    import json
    participant_id = create_participant(client)
    client.post("/api/score", headers={"X-Participant-Id": participant_id},
                json={"item_id": "dua", "responses": ["làm móc treo"]})
    assert client.get("/api/admin/exports/analysis.json").status_code == 401
    app.dependency_overrides[require_admin] = lambda: object()
    response = client.get("/api/admin/exports/analysis.json")
    assert response.status_code == 200
    artifact = response.json()
    serialized = json.dumps(artifact["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert artifact["sha256"] == hashlib.sha256(serialized.encode()).hexdigest()
    assert participant_id not in serialized
    assert "Nguyễn Minh Anh" not in serialized
    assert artifact["payload"]["prompt_hashes"]


def test_resolver_retries_automatically_without_admin(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    monkeypatch.setattr(main_mod.settings, "resolver_retry_seconds", 1)
    database = app.dependency_overrides[get_db]()
    db = next(database)
    engine = db.get_bind()
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))
    original = response_controller._mock_mapping
    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    headers = {"X-Participant-Id": create_participant(client)}
    response_id = client.post("/api/score", headers=headers,
        json={"item_id": "dua", "responses": ["làm móc treo"], "wait_for_completion": False}).json()["response_id"]
    assert response_worker.run_one_job()
    db.expire_all()
    row = db.get(Response, response_id)
    assert row.scoring_status == ResponseScoringStatus.PENDING_REVIEW
    old_id = db.scalar(select(ResponseIdea.id).where(ResponseIdea.response_id == response_id))
    row.resolution_next_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(response_controller, "_mock_mapping", original)
    assert response_worker.run_one_job()
    db.expire_all()
    row = db.get(Response, response_id)
    assert row.scoring_status == ResponseScoringStatus.COLLECTING
    assert row.resolution_attempts == 1
    assert db.scalar(select(ResponseIdea.id).where(ResponseIdea.response_id == response_id)) == old_id
    assert client.get(f"/api/responses/{response_id}", headers=headers).json()["resolution_pending"] is False
    next(database, None)


def test_idempotency_compares_original_input_cells(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    headers = {"X-Participant-Id": create_participant(client)}
    payload = {"item_id": "dua", "responses": ["ý một\ný hai"],
               "request_id": str(uuid.uuid4()), "wait_for_completion": False}
    assert client.post("/api/score", headers=headers, json=payload).status_code == 200
    assert client.post("/api/score", headers=headers,
                       json={**payload, "responses": ["ý một", "ý hai"]}).status_code == 409


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


def test_participant_form_updates_existing_profile(client):
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
            "ai_usage_group": "HIGH",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == participant_id
    assert response.json()["full_name"] == "Tên gửi lại không ghi đè"
    assert response.json()["ai_usage_group"] == "HIGH"
    assert "age" not in response.json()
    assert "gender" not in response.json()
    assert "occupation" not in response.json()


def test_participant_history_only_returns_current_participant_responses(client):
    first_participant = create_participant(client, "history-one@example.test")
    second_participant = create_participant(client, "history-two@example.test")
    first = client.post(
        "/api/score",
        headers={"X-Participant-Id": first_participant},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu"},
    )
    client.post(
        "/api/score",
        headers={"X-Participant-Id": second_participant},
        json={"item_id": "dua", "raw_input": "làm thanh gõ nhịp"},
    )

    assert client.get("/api/participants/me/responses").status_code == 401
    history = client.get(
        "/api/participants/me/responses",
        headers={"X-Participant-Id": first_participant},
    )
    assert history.status_code == 200
    assert [row["response_id"] for row in history.json()] == [
        first.json()["response_id"]
    ]


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
    assert returning.json()["participant"]["ai_usage_group"] == "LOW"
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
            "ai_usage_group": "HIGH",
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


def test_score_and_participant_result_roundtrip(client):
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

    assert client.get(f"/api/responses/{response_id}").status_code == 401
    detail = client.get(
        f"/api/responses/{response_id}", headers={"X-Participant-Id": participant_id}
    )
    assert detail.status_code == 200
    assert detail.json()["response_id"] == response_id

    # Danh sách toàn bộ lượt làm vẫn là dữ liệu quản trị.
    assert client.get("/api/responses").status_code == 401


def test_queued_response_survives_navigation_and_reuses_new_code(client, monkeypatch):
    """Bài được commit trước khi worker chạy; hai bài cùng nghĩa chỉ có một mã."""
    database = app.dependency_overrides[get_db]()
    db = next(database)
    engine = db.get_bind()
    item = db.get(Item, "dua")
    item.scoring_min_participants = 1
    item.scoring_min_ideas = 1
    db.commit()
    next(database, None)

    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))

    first_person = create_participant(client)
    second_person = create_participant(client)
    first_header = {"X-Participant-Id": first_person}
    second_header = {"X-Participant-Id": second_person}
    request_id = str(uuid.uuid4())
    first = client.post(
        "/api/score", headers=first_header,
        json={"item_id": "dua", "responses": ["làm đồ trang trí Noel"], "request_id": request_id},
    )
    assert first.status_code == 200
    first_id = first.json()["response_id"]
    assert first.json()["processing_state"] == "QUEUED"
    assert first.json()["mapping"]["ideas"] == []
    duplicate_submit = client.post(
        "/api/score", headers=first_header,
        json={"item_id": "dua", "responses": ["làm đồ trang trí Noel"], "request_id": request_id},
    )
    assert duplicate_submit.json()["response_id"] == first_id
    second = client.post(
        "/api/score", headers=second_header,
        json={"item_id": "dua", "responses": ["làm đồ trang trí Noel"]},
    )
    second_id = second.json()["response_id"]
    assert client.get("/api/participants/me/responses", headers=first_header).json()[0]["processing_state"] == "QUEUED"
    assert client.get(f"/api/responses/{first_id}", headers=second_header).status_code == 404

    for _ in range(4):
        assert response_worker.run_one_job()
    first_done = client.get(f"/api/responses/{first_id}", headers=first_header).json()
    second_done = client.get(f"/api/responses/{second_id}", headers=second_header).json()
    assert first_done["processing_state"] == second_done["processing_state"] == "DONE"
    assert first_done["scoring_status"] == second_done["scoring_status"] == "FINAL"
    database = app.dependency_overrides[get_db]()
    db = next(database)
    assert len(db.scalars(select(ItemCode).where(ItemCode.item_id == "dua")).all()) == 1
    assert len(db.scalars(select(Response).where(Response.item_id == "dua")).all()) == 2
    next(database, None)


def test_submit_can_wait_on_same_post_without_client_polling(client, monkeypatch):
    """Frontend được phép giữ POST chờ; bài vẫn phải được commit trước lúc chờ."""
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    participant_id = create_participant(client)
    observed: dict[str, str] = {}

    def fake_wait(db, response_id: str, current_participant_id: str):
        row = db.get(Response, response_id)
        assert row is not None
        assert row.processing_state == "QUEUED"
        observed["response_id"] = response_id
        observed["participant_id"] = current_participant_id
        return response_controller._to_response(row)

    monkeypatch.setattr(response_controller, "_wait_for_response_completion", fake_wait)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={
            "item_id": "dua",
            "responses": ["làm đồ trang trí Noel"],
            "request_id": str(uuid.uuid4()),
            "wait_for_completion": True,
        },
    )

    assert submitted.status_code == 200
    assert observed == {
        "response_id": submitted.json()["response_id"],
        "participant_id": participant_id,
    }


def test_browser_ready_waits_for_scoring_after_mapping():
    """DONE của mapping chưa phải kết quả cuối nếu item ACTIVE vẫn thiếu scoring."""
    item = Item(
        id="dua",
        name="Đũa",
        calibration_status=ItemCalibrationStatus.ACTIVE,
    )
    row = Response(
        participant_id=str(uuid.uuid4()),
        item_id=item.id,
        item=item,
        raw_input="làm đồ trang trí",
        mapping={"ideas": []},
        scoring={},
        processing_state="DONE",
        scoring_status=ResponseScoringStatus.COLLECTING,
    )

    assert response_controller._response_is_ready_for_browser(row) is False
    row.scoring_status = ResponseScoringStatus.PENDING_REVIEW
    assert response_controller._response_is_ready_for_browser(row) is True


def test_stale_codebook_epoch_rechecks_before_create(client, monkeypatch):
    """Quyết định CREATE_NEW từ codebook cũ phải xét lại mã mới xuất hiện."""
    database = app.dependency_overrides[get_db]()
    db = next(database)
    engine = db.get_bind()
    next(database, None)


    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))
    participant_id = create_participant(client)
    response = client.post(
        "/api/score", headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "responses": ["làm đồ trang trí Noel"]},
    )
    original_mock = response_controller._mock_mapping
    injected = False

    def concurrent_create(item, raw, codes):
        nonlocal injected
        if not injected and not codes:
            injected = True
            with Session(engine) as transaction:
                item_row = transaction.get(Item, "dua")
                item_row.codebook_epoch += 1
                transaction.add(ItemCode(
                    item_id="dua", name="làm đồ trang trí Noel",
                    normalized_name="lam do trang tri noel",
                    description="Dùng đũa làm đồ trang trí Noel.",
                ))
                transaction.commit()
        return original_mock(item, raw, codes)

    monkeypatch.setattr(response_controller, "_mock_mapping", concurrent_create)
    assert response_worker.run_one_job()
    detail = client.get(
        f"/api/responses/{response.json()['response_id']}",
        headers={"X-Participant-Id": participant_id},
    ).json()
    assert detail["processing_state"] == "DONE"
    database = app.dependency_overrides[get_db]()
    db = next(database)
    row = db.get(Response, response.json()["response_id"])
    assert row.mapping_meta["stale_rechecks"] == 1
    assert len(db.scalars(select(ItemCode).where(ItemCode.item_id == "dua")).all()) == 1
    next(database, None)


def test_admin_can_view_and_retry_failed_saved_response(client, monkeypatch):
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score", headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "responses": ["làm dấu trang"]},
    ).json()
    response_id = submitted["response_id"]
    database = app.dependency_overrides[get_db]()
    db = next(database)
    row = db.get(Response, response_id)
    row.processing_state = "FAILED"
    row.processing_attempts = 3
    db.commit()
    next(database, None)

    assert client.get(f"/api/admin/responses/{response_id}").status_code == 401
    app.dependency_overrides[require_admin] = lambda: object()
    assert client.get(f"/api/admin/responses/{response_id}").json()["processing_state"] == "FAILED"
    retry = client.post(f"/api/admin/responses/{response_id}/retry")
    assert retry.status_code == 200
    assert retry.json()["processing_state"] == "QUEUED"
    assert client.post(f"/api/admin/responses/{response_id}/retry").status_code == 409


def test_expired_worker_lease_reclaims_saved_response(client, monkeypatch):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    engine = db.get_bind()
    next(database, None)
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score", headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "responses": ["làm giá đỡ"]},
    ).json()
    database = app.dependency_overrides[get_db]()
    db = next(database)
    row = db.get(Response, submitted["response_id"])
    row.processing_state = "RUNNING"
    row.processing_claim_token = "old-worker"
    row.processing_attempts = 1
    row.processing_lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    next(database, None)

    assert response_worker.run_one_job()
    detail = client.get(
        f"/api/responses/{submitted['response_id']}",
        headers={"X-Participant-Id": participant_id},
    ).json()
    assert detail["processing_state"] == "DONE"
    assert detail["mapping"]["ideas"]
    response_worker._run_mapping(submitted["response_id"], "old-worker")
    database = app.dependency_overrides[get_db]()
    db = next(database)
    assert len(db.scalars(select(ResponseIdea).where(ResponseIdea.response_id == submitted["response_id"])).all()) == 1
    next(database, None)


def test_expired_final_lease_marks_saved_response_failed(client, monkeypatch):
    """Worker chết sau lần thử cuối không để bài RUNNING mãi trong lịch sử."""
    database = app.dependency_overrides[get_db]()
    db = next(database)
    engine = db.get_bind()
    next(database, None)
    monkeypatch.setattr(main_mod.settings, "async_processing_enabled", True)
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score", headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "responses": ["làm giá đỡ"]},
    ).json()
    database = app.dependency_overrides[get_db]()
    db = next(database)
    row = db.get(Response, submitted["response_id"])
    row.processing_state = "RUNNING"
    row.processing_claim_token = "worker-da-chet"
    row.processing_attempts = response_worker.settings.processing_max_attempts
    row.processing_lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    next(database, None)

    assert response_worker.run_one_job()
    detail = client.get(
        f"/api/responses/{submitted['response_id']}",
        headers={"X-Participant-Id": participant_id},
    ).json()
    assert detail["processing_state"] == "FAILED"
    assert detail["mapping"]["ideas"] == []
    assert response_worker.run_one_job() is False


def test_worker_can_prioritize_scoring_when_mapping_queue_is_busy(monkeypatch):
    """Worker có lượt ưu tiên chấm để không bỏ đói bài đã phân mã."""
    claimed_kinds = []

    def no_job(kind):
        claimed_kinds.append(kind)
        return None

    monkeypatch.setattr(response_worker, "_claim", no_job)
    monkeypatch.setattr(response_worker, "_expire_exhausted", lambda: False)
    monkeypatch.setattr(response_worker, "_wake_one_unresolved", lambda: False)
    monkeypatch.setattr(response_worker, "_recount_one_item", lambda: False)
    assert response_worker.run_one_job(prefer_scoring=True) is False
    assert claimed_kinds == ["resolution", "scoring", "mapping"]


def test_cluster_audit_groups_pending_ideas_without_mutating_responses(client):
    """Báo cáo cụm có guard admin và không dùng ý của bài EXCLUDED."""
    participant_id = create_participant(client)
    database = app.dependency_overrides[get_db]()
    db = next(database)
    code = ItemCode(
        item_id="dua", name="Trang trí bằng đũa",
        normalized_name="trang tri bang dua", description="Dùng đũa làm đồ trang trí.",
        embedding=[1.0, 0.0], embedding_model="semantic-v1",
        functional_signature={"goal": "trang trí", "object_role": "vật liệu", "mechanism": "ghép nối"},
    )
    db.add(code)
    db.flush()
    code_id = code.id
    for index, vector in enumerate(([1.0, 0.0], [0.98, 0.2], [-1.0, 0.0])):
        excluded = index == 2
        response = Response(
            participant_id=participant_id, item_id="dua", raw_input=f"Ý {index}",
            mapping={"ideas": []}, scoring={}, processing_state="DONE",
            scoring_status=(
                ResponseScoringStatus.EXCLUDED if excluded
                else ResponseScoringStatus.PENDING_REVIEW
            ),
        )
        db.add(response)
        db.flush()
        db.add(ResponseIdea(
            response_id=response.id, original=f"Ý {index}", normalized=f"Trang trí {index}",
            mapping_status="VALID", embedding=list(vector), embedding_model="semantic-v1",
            review_status="PENDING",
            functional_signature={"goal": "trang trí", "object_role": "vật liệu", "mechanism": "ghép nối"},
        ))
    db.commit()
    next(database, None)

    endpoint = "/api/admin/items/dua/cluster-audit"
    assert client.get(endpoint).status_code == 401
    app.dependency_overrides[require_admin] = lambda: object()
    report = client.get(endpoint).json()
    assert report["decision_mode"] == "SHADOW"
    assert report["total_pending_ideas"] == 2
    assert report["vectorized_ideas"] == 2
    assert len(report["proposals"]) == 1
    assert report["proposals"][0]["member_count"] == 2
    assert report["proposals"][0]["nearest_codes"][0]["code_id"] == code_id
    limited = client.get(endpoint, params={"limit": 1}).json()
    assert limited["sampled_ideas"] == 1
    assert limited["truncated"] is True
    assert client.get("/api/admin/items/khong-co/cluster-audit").status_code == 404

    database = app.dependency_overrides[get_db]()
    db = next(database)
    assert db.scalar(select(ResponseIdea.code_id).where(ResponseIdea.original == "Ý 0")) is None
    assert db.scalar(select(Response.scoring_status).where(Response.raw_input == "Ý 0")) == ResponseScoringStatus.PENDING_REVIEW
    next(database, None)


def test_score_accepts_ten_rows_and_rejects_an_eleventh(client):
    participant_id = create_participant(client)
    headers = {"X-Participant-Id": participant_id}
    ideas = [f"Ý tưởng sáng tạo số {index}" for index in range(1, 11)]

    accepted = client.post(
        "/api/score",
        headers=headers,
        json={"item_id": "dua", "responses": ideas},
    )
    assert accepted.status_code == 200
    assert accepted.json()["scoring_status"] == "COLLECTING"
    assert accepted.json()["raw_input"] == "\n".join(ideas)

    rejected = client.post(
        "/api/score",
        headers=headers,
        json={"item_id": "dua", "responses": ideas + ["Ý tưởng thứ 11"]},
    )
    assert rejected.status_code == 422


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
    assert "codes" not in codebook

    detail = client.get("/api/admin/items/dua/codebook").json()
    assert detail["codes"][0]["validation_status"] == "ACCEPTED"
    assert detail["codes"][0]["response_count"] == 1
    assert detail["codes"][0]["contributing_response_count"] == 1
    assert detail["codes"][0]["contributing_idea_count"] == 1


def test_admin_can_export_grouped_scores_csv(client):
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    )
    assert submitted.status_code == 200

    app.dependency_overrides[require_admin] = lambda: object()
    response = client.get("/api/admin/exports/responses.csv")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="aut-response-scores.csv"'
    )
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["participant_id"] == participant_id
    assert rows[0]["ai_usage_group"] == "LOW"
    assert rows[0]["item_id"] == "dua"
    assert rows[0]["scoring_status"] == "COLLECTING"
    assert rows[0]["fluency"] == ""
    assert rows[0]["originality"] == ""


def test_admin_cannot_mutate_append_only_codebook(client):
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "responses": ["Dùng làm cọc đánh dấu cây"]},
    )
    assert submitted.status_code == 200

    app.dependency_overrides[require_admin] = lambda: object()
    code_id = client.get("/api/admin/items/dua/codebook").json()["codes"][0]["id"]

    assert client.patch(
        f"/api/admin/items/dua/codes/{code_id}", json={"name": "Tên mới"}
    ).status_code == 404
    assert client.delete(f"/api/admin/items/dua/codes/{code_id}").status_code == 404
    assert client.delete("/api/admin/items/dua/codes").status_code == 404
    assert client.post("/api/admin/items/dua/remap").status_code == 404


def test_admin_codebook_is_paginated_and_filtered_in_backend(client):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    db.add_all(
        [
            ItemCode(
                id=str(uuid.uuid4()),
                item_id="dua",
                name=f"Mã {index:02d}",
                normalized_name=f"ma-{index:02d}",
                validation_status=(
                    CodeValidationStatus.REJECTED
                    if index >= 22
                    else CodeValidationStatus.ACCEPTED
                ),
                maturity_status=CodeMaturityStatus.ACTIVE,
                confidence=0.99,
                created_by="TEST",
            )
            for index in range(25)
        ]
    )
    db.commit()
    next(database, None)

    app.dependency_overrides[require_admin] = lambda: object()
    second_page = client.get(
        "/api/admin/items/dua/codebook?page=2&page_size=10&code_filter=ALL"
    )
    assert second_page.status_code == 200
    payload = second_page.json()
    assert payload["code_page"] == 2
    assert payload["code_page_size"] == 10
    assert payload["code_total"] == 25
    assert payload["code_page_count"] == 3
    assert len(payload["codes"]) == 10

    rejected = client.get(
        "/api/admin/items/dua/codebook?page=1&page_size=10&code_filter=REJECTED"
    ).json()
    assert rejected["code_total"] == 3
    assert len(rejected["codes"]) == 3
    assert all(code["validation_status"] == "REJECTED" for code in rejected["codes"])
    assert client.get("/api/admin/items/dua/codebook?page_size=101").status_code == 422


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
    assert all(row["functional_signature"]["goal"] for row in decisions["decisions"])
    created = next(row for row in decisions["decisions"] if row["decision"] == "CREATE_NEW")
    assert all(created["mapping_evidence"]["policy_gates"].values())


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
    assert payload["decisions"][0]["code_name"] is None


def test_admin_can_resolve_pending_idea_by_creating_code(client, monkeypatch):
    """Ca AI không đủ căn cứ phải có thể được duyệt mà vẫn giữ audit gốc."""
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
    queue = client.get("/api/admin/items/dua/mapping-reviews").json()
    assert queue["pending_count"] == 1
    review = queue["reviews"][0]
    assert review["original"] == "làm móc treo"
    assert review["review_payload"]["proposal"]["code_name"] == "Móc treo từ đũa"
    epoch = client.get("/api/admin/items/dua/codebook").json()["codebook_epoch"]

    resolved = client.post(
        f"/api/admin/items/dua/mapping-reviews/{review['idea_id']}/resolve",
        json={
            "action": "CREATE_NEW",
            "expected_codebook_epoch": epoch,
            "code_name": "Móc và giá treo từ đũa",
            "code_description": "Dùng đũa làm phần móc hoặc thanh chịu lực để treo đồ.",
            "functional_signature": {
                "goal": "treo đồ vật",
                "object_role": "móc hoặc thanh chịu lực",
                "mechanism": "uốn hoặc ghép để giữ vật",
            },
            "inclusion_rules": ["Đũa trực tiếp giữ vật ở trạng thái treo."],
            "exclusion_rules": ["Không gồm dùng đũa làm đồ trang trí không chịu lực."],
            "positive_examples": ["làm móc treo"],
            "note": "Ý hợp lệ và khác chức năng với sổ mã hiện tại.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolution"] == "CREATE_NEW"
    assert resolved.json()["scoring_status"] == "COLLECTING"
    assert client.get("/api/admin/items/dua/mapping-reviews").json()["pending_count"] == 0

    detail = client.get(
        f"/api/responses/{submitted.json()['response_id']}",
        headers={"X-Participant-Id": participant_id},
    ).json()
    assert detail["mapping"]["ideas"][0]["code"] == "Móc và giá treo từ đũa"
    assert detail["mapping"]["ideas"][0]["curator_decision"] == "ADMIN_CREATE_NEW"


def test_admin_review_rejects_stale_codebook_epoch(client, monkeypatch):
    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    participant_id = create_participant(client)
    client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm móc treo"},
    )
    app.dependency_overrides[require_admin] = lambda: object()
    review = client.get("/api/admin/items/dua/mapping-reviews").json()["reviews"][0]

    database = app.dependency_overrides[get_db]()
    db = next(database)
    item = db.get(Item, "dua")
    item.codebook_epoch += 1
    db.commit()
    next(database, None)

    rejected = client.post(
        f"/api/admin/items/dua/mapping-reviews/{review['idea_id']}/resolve",
        json={
            "action": "MARK_INVALID",
            "expected_codebook_epoch": 0,
            "note": "kiểm tra stale",
        },
    )
    assert rejected.status_code == 409


def test_admin_can_mark_pending_idea_invalid_with_audit_reason(client, monkeypatch):
    monkeypatch.setattr(response_controller, "_mock_mapping", uncertain_mapping)
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm móc treo"},
    ).json()
    app.dependency_overrides[require_admin] = lambda: object()
    review = client.get("/api/admin/items/dua/mapping-reviews").json()["reviews"][0]
    epoch = client.get("/api/admin/items/dua/codebook").json()["codebook_epoch"]

    resolved = client.post(
        f"/api/admin/items/dua/mapping-reviews/{review['idea_id']}/resolve",
        json={
            "action": "MARK_INVALID",
            "expected_codebook_epoch": epoch,
            "note": "Câu không mô tả được công dụng có nghĩa của đũa.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    detail = client.get(
        f"/api/responses/{submitted['response_id']}",
        headers={"X-Participant-Id": participant_id},
    ).json()
    idea = detail["mapping"]["ideas"][0]
    assert idea["status"] == "INVALID"
    assert idea["code"] is None
    assert idea["curator_decision"] == "ADMIN_MARK_INVALID"
    assert idea["reason"] == "Câu không mô tả được công dụng có nghĩa của đũa."


@pytest.mark.skip(reason="Thao tác remap đã bị loại trong sổ mã append-only.")
def test_admin_can_request_full_remap(client, monkeypatch):
    app.dependency_overrides[require_admin] = lambda: object()
    monkeypatch.setattr(
        "app.controllers.admin_controller.reprocess_item_mappings", lambda _item_id: 2
    )
    response = client.post("/api/admin/items/dua/remap")
    assert response.status_code == 200
    assert response.json() == {"processed": 2}


@pytest.mark.skip(reason="Code không còn chờ admin chấp nhận.")
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


@pytest.mark.skip(reason="Hệ thống mới chấm trực tiếp và không có code uncertain.")
def test_accepting_uncertain_code_scores_once_when_item_is_ready(client, monkeypatch):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    item = db.get(Item, "dua")
    item.scoring_min_participants = 1
    item.scoring_min_ideas = 1
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


@pytest.mark.skip(reason="Ngưỡng chờ và backfill đã được thay bằng chấm trực tiếp.")
def test_threshold_backfills_once_and_new_data_does_not_change_final_score(client):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    item = db.get(Item, "dua")
    item.scoring_min_participants = 2
    item.scoring_min_ideas = 2
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


@pytest.mark.skip(reason="Admin mới chỉ kiểm toán, không thay quyết định code.")
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


@pytest.mark.skip(reason="Sổ mã append-only không hỗ trợ gộp mã.")
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
    assert merged_source["merged_into_id"] == target["id"]
    assert merged_source["merged_into_name"] == target["name"]

    detail = client.get(f"/api/responses/{pending_response.json()['response_id']}").json()
    assert detail["scoring_status"] == "COLLECTING"
    assert detail["mapping"]["ideas"][0]["code"] == target["name"]
    assert detail["mapping"]["ideas"][0]["status"] == "VALID"
    assert client.patch(
        f"/api/admin/items/dua/codes/{source['id']}",
        json={"name": "Không được sửa"},
    ).status_code == 409
    assert client.delete(f"/api/admin/items/dua/codes/{source['id']}").status_code == 409
    assert client.delete(f"/api/admin/items/dua/codes/{target['id']}").status_code == 409


@pytest.mark.skip(reason="Sổ mã append-only không hỗ trợ gộp mã.")
def test_merge_keeps_final_score_and_mapping_snapshot(client):
    database = app.dependency_overrides[get_db]()
    db = next(database)
    item = db.get(Item, "dua")
    item.scoring_min_participants = 1
    item.scoring_min_ideas = 1
    db.commit()
    next(database, None)

    participant_id = create_participant(client)
    headers = {"X-Participant-Id": participant_id}
    source_response = client.post(
        "/api/score",
        headers=headers,
        json={"item_id": "dua", "raw_input": "Mã nguồn"},
    ).json()
    target_response = client.post(
        "/api/score",
        headers=headers,
        json={"item_id": "dua", "raw_input": "Mã đích"},
    ).json()
    assert source_response["scoring_status"] == "FINAL"
    assert target_response["scoring_status"] == "FINAL"
    frozen_scoring = source_response["scoring"]
    frozen_mapping = source_response["mapping"]

    app.dependency_overrides[require_admin] = lambda: object()
    codes = client.get("/api/admin/items/dua/codebook").json()["codes"]
    source = next(code for code in codes if code["name"] == "Mã nguồn")
    target = next(code for code in codes if code["name"] == "Mã đích")
    merged = client.post(
        f"/api/admin/items/dua/codes/{source['id']}/merge",
        json={"target_code_id": target["id"]},
    )
    assert merged.status_code == 200

    detail = client.get(f"/api/responses/{source_response['response_id']}").json()
    assert detail["scoring_status"] == "FINAL"
    assert detail["scoring"] == frozen_scoring
    assert detail["mapping"] == frozen_mapping

    database = app.dependency_overrides[get_db]()
    db = next(database)
    response_row = db.get(Response, source_response["response_id"])
    idea = db.scalar(
        select(ResponseIdea).where(ResponseIdea.response_id == source_response["response_id"])
    )
    assert idea.code_id == target["id"]
    assert "requires_manual_rescore" not in response_row.scoring_meta
    assert response_row.scoring_meta["codebook_changes"][-1]["type"] == "CODE_MERGE"
    next(database, None)


@pytest.mark.skip(reason="Sổ mã append-only không hỗ trợ gộp mã.")
def test_merge_requires_an_active_accepted_target(client):
    source_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    database = app.dependency_overrides[get_db]()
    db = next(database)
    db.add_all(
        [
            ItemCode(
                id=source_id,
                item_id="dua",
                name="Mã nguồn hợp lệ",
                normalized_name="ma-nguon-hop-le",
                validation_status=CodeValidationStatus.ACCEPTED,
                maturity_status=CodeMaturityStatus.ACTIVE,
                confidence=0.99,
            ),
            ItemCode(
                id=target_id,
                item_id="dua",
                name="Mã đích đã loại",
                normalized_name="ma-dich-da-loai",
                validation_status=CodeValidationStatus.REJECTED,
                maturity_status=CodeMaturityStatus.ACTIVE,
                confidence=0.99,
            ),
        ]
    )
    db.commit()
    next(database, None)

    app.dependency_overrides[require_admin] = lambda: object()
    response = client.post(
        f"/api/admin/items/dua/codes/{source_id}/merge",
        json={"target_code_id": target_id},
    )
    assert response.status_code == 409
    assert "đang hoạt động và đã được chấp nhận" in response.json()["detail"]


@pytest.mark.skip(reason="Mã đã dùng để tính điểm là bất biến.")
def test_admin_can_delete_one_code_without_deleting_raw_response(client):
    participant_id = create_participant(client)
    submitted = client.post(
        "/api/score",
        headers={"X-Participant-Id": participant_id},
        json={"item_id": "dua", "raw_input": "làm cọc đánh dấu cây"},
    )
    response_id = submitted.json()["response_id"]
    app.dependency_overrides[require_admin] = lambda: object()
    codebook = client.get("/api/admin/items/dua/codebook").json()
    code_id = codebook["codes"][0]["id"]

    deleted = client.delete(f"/api/admin/items/dua/codes/{code_id}")
    assert deleted.status_code == 200
    assert deleted.json()["codes"] == []

    detail = client.get(f"/api/responses/{response_id}")
    assert detail.status_code == 200
    assert detail.json()["raw_input"] == "làm cọc đánh dấu cây"
    assert detail.json()["scoring"] is None
    assert detail.json()["scoring_status"] == "PENDING_REVIEW"


@pytest.mark.skip(reason="Sổ mã append-only không hỗ trợ xoá toàn bộ mã.")
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

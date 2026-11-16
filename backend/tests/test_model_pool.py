"""Kiểm thử quota bằng SQLite và provider giả; tuyệt đối không gọi model thật."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.core.deps import require_admin
from app.models.models import Item, Participant, PipelineAudit, Response, ResponseScoringStatus
from app.models.model_pool import ManagedModel, ModelPoolEvent, ModelPoolSettings, ModelQuota, ModelTokenRequest
from app.pipeline import model_pool as pool
from app.pipeline.llm import chat_json, collect_llm_calls, LLMJSONError
from app.pipeline.pool_errors import ModelPoolChanged, ModelPoolWait
from app.schemas.model_pool import ModelBalanceUpdate, ManagedModelUpdate, PoolSettingsUpdate
from app.controllers import model_controller, response_worker
from app.main import app
from tests.fake_llm import FakeClient

REQUEST = {"model": "legacy", "messages": [{"role": "user", "content": "test"}], "max_tokens": 1024}
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(pool, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "byteplus_model_pool_available", True)
    monkeypatch.setattr(settings, "llm_provider", "byteplus")
    monkeypatch.setattr(settings, "byteplus_api_key", "test-only-key")
    monkeypatch.setattr(settings, "byteplus_model", "model-a")
    with Session(engine) as db:
        pool.initialize(db)
        db.commit()
    yield engine
    engine.dispose()


def activate(engine, balances=(500000, 500000)):
    with Session(engine) as db:
        for slot, balance in enumerate(balances, 1):
            row = db.get(ManagedModel, slot)
            quota = db.get(ModelQuota, row.quota_id) if row.quota_id else ModelQuota(quota_key=f"base-{slot}")
            db.add(quota)
            quota.confirmed_remaining = balance
            quota.confirmed_at = pool.now()
            db.flush()
            row.model_id = f"model-{slot}"
            row.quota_id = quota.id
            row.enabled = True
        db.get(ModelPoolSettings, 1).enabled = True
        db.commit()


def completion(content='{"ok": true}'):
    return {"content": content, "usage": USAGE}


def error(code, status=429):
    exc = RuntimeError(code)
    exc.body = {"error": {"code": code}}
    exc.status_code = status
    return exc


def test_initialization_is_once_only_and_does_not_assume_full_balance(engine, monkeypatch):
    monkeypatch.setattr(settings, "byteplus_model", "changed-env")
    with Session(engine) as db:
        pool.initialize(db)
        db.commit()
        assert db.get(ManagedModel, 1).model_id == "model-a"
        assert db.get(ModelPoolSettings, 1).enabled is False
        assert db.scalar(select(func.count(ManagedModel.slot))) == 5
        assert db.scalar(select(ModelQuota.confirmed_remaining)) is None


def test_reserves_input_and_output_before_threshold_and_settles_actual_usage(engine):
    budget = pool.estimate_tokens(REQUEST)
    activate(engine, (10000 + budget - 1, 500000))
    client = FakeClient([completion()])
    result, meta = chat_json(client, **{key: value for key, value in REQUEST.items() if key == "model"},
        prompt="test", max_tokens=1024, temperature=0, provider="byteplus", stage="idea_extraction")
    assert result == {"ok": True}
    assert meta["model"] == "model-2"
    assert client.chat.completions.requests[0]["model"] == "model-2"
    with Session(engine) as db:
        quota = db.get(ModelQuota, db.get(ManagedModel, 2).quota_id)
        assert quota.spent_tokens == 120 and quota.reserved_tokens == 0
        assert pool.remaining(quota) == 500000 - 120
        assert db.scalar(select(ModelPoolSettings.active_slot)) == 2
        assert db.scalar(select(func.count(ModelTokenRequest.id))) == 1
    assert collect_llm_calls(meta)[0]["model"] == "model-2"


def test_byteplus_quota_error_switches_model_but_rate_limit_does_not(engine):
    activate(engine)
    client = FakeClient([error("SetLimitExceeded"), completion()])
    _, meta = chat_json(client, model="legacy", prompt="test", temperature=0, max_tokens=1024,
                        provider="byteplus", stage="code_curator", max_retries=0)
    assert [r["model"] for r in client.chat.completions.requests] == ["model-1", "model-2"]
    assert meta["model"] == "model-2"
    with Session(engine) as db:
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).exhausted
        assert db.scalar(select(func.count(ModelTokenRequest.id))) == 2
    rate = FakeClient([error("RateLimitExceeded")])
    with pytest.raises(LLMJSONError):
        chat_json(rate, model="legacy", prompt="test", temperature=0, max_tokens=1024,
                  provider="byteplus", max_retries=0)
    assert rate.chat.completions.calls == 1
    with Session(engine) as db:
        assert not db.get(ModelQuota, db.get(ManagedModel, 2).quota_id).exhausted


def test_account_error_stops_pool_instead_of_fanning_out_to_five_models(engine):
    activate(engine)
    client = FakeClient([error("InvalidApiKey", 401)])
    with pytest.raises(ModelPoolWait):
        chat_json(client, model="legacy", prompt="test", temperature=0, provider="byteplus", max_retries=2)
    assert client.chat.completions.calls == 1
    assert not pool.has_capacity()
    with Session(engine) as db:
        assert db.get(ModelPoolSettings, 1).blocked_reason == "ACCOUNT_OR_KEY_ERROR"


def test_invalid_json_is_charged_and_each_retry_keeps_its_actual_model(engine, monkeypatch):
    activate(engine)
    monkeypatch.setattr("app.pipeline.llm.time.sleep", lambda _: None)
    client = FakeClient([completion("broken JSON"), completion()])
    _, meta = chat_json(client, model="legacy", prompt="test", temperature=0, provider="byteplus", max_retries=1)
    assert meta["usage"]["total_tokens"] == 240
    with Session(engine) as db:
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).spent_tokens == 240
    assert all(call["model"] == "model-1" for call in collect_llm_calls(meta))


def test_unknown_usage_keeps_reservation_and_expired_lease_is_not_refunded(engine):
    activate(engine, (500000,))
    hold = pool.reserve(REQUEST, "code_challenger", "call-test")
    pool.settle(hold, error=TimeoutError())
    with Session(engine) as db:
        row = db.get(ModelTokenRequest, hold.id)
        assert row.status == "UNKNOWN" and row.total_tokens is None
        quota = db.get(ModelQuota, row.quota_id)
        assert quota.reserved_tokens == pool.estimate_tokens(REQUEST)
        assert quota.spent_tokens == 0
    second = pool.reserve(REQUEST, "code_challenger", "another-call")
    with Session(engine) as db:
        db.get(ModelTokenRequest, second.id).lease_until = pool.now() - timedelta(seconds=1)
        db.commit()
    assert pool.has_capacity()
    with Session(engine) as db:
        assert db.get(ModelTokenRequest, second.id).status == "UNKNOWN"
        assert db.get(ModelQuota, quota.id).reserved_tokens == pool.estimate_tokens(REQUEST) * 2


def test_concurrent_reservations_do_not_spend_same_available_tokens(engine):
    budget = pool.estimate_tokens(REQUEST)
    activate(engine, (10000 + budget,))
    def reserve_one():
        try:
            return pool.reserve(REQUEST, "scoring", "concurrent")
        except ModelPoolWait:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve_one(), range(2)))
    assert sum(row is not None for row in results) == 1
    with Session(engine) as db:
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).reserved_tokens == budget


def test_settlement_is_idempotent_and_deduplicates_provider_request_id(engine):
    activate(engine)
    fake = FakeClient([completion()]).chat.completions.create(**REQUEST)
    first = pool.reserve(REQUEST, "scoring", "one")
    pool.settle(first, completion=fake)
    pool.settle(first, completion=fake)
    second = pool.reserve(REQUEST, "scoring", "two")
    pool.settle(second, completion=fake)
    with Session(engine) as db:
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).spent_tokens == 120
        assert db.get(ModelTokenRequest, second.id).status == "DUPLICATE"


def test_scoring_group_holds_single_model_and_releases_unused_budget(engine):
    activate(engine)
    client = FakeClient([completion(), completion()])
    with pool.scoring_group("test", 1024, 3) as group:
        with Session(engine) as db:
            db.get(ModelPoolSettings, 1).active_slot = 2
            db.commit()
        for _ in range(2):
            _, meta = chat_json(client, model="legacy", prompt="test", temperature=0,
                                max_tokens=1024, provider="byteplus", max_retries=0)
            assert meta["model"] == group.model_id
    with Session(engine) as db:
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).reserved_tokens == 0
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).spent_tokens == 240


def test_quota_exhausted_inside_scoring_group_does_not_mix_models(engine):
    activate(engine)
    client = FakeClient([error("SetLimitExceeded")])
    with pytest.raises(ModelPoolChanged):
        with pool.scoring_group("test", 1024, 3):
            chat_json(client, model="legacy", prompt="test", temperature=0,
                      provider="byteplus", max_tokens=1024)
    assert client.chat.completions.calls == 1
    with Session(engine) as db:
        assert db.get(ModelQuota, db.get(ManagedModel, 1).quota_id).reserved_tokens == 0


def test_shared_base_model_quota_cannot_be_spent_twice(engine):
    activate(engine)
    with Session(engine) as db:
        first = db.get(ManagedModel, 1)
        second = db.get(ManagedModel, 2)
        second.quota_id = first.quota_id
        db.get(ModelQuota, first.quota_id).exhausted = True
        db.commit()
    with pytest.raises(ModelPoolWait):
        pool.reserve(REQUEST, "audit", "shared")


def test_all_five_exhausted_models_wait_without_sixth_provider_call(engine):
    activate(engine, (500000,) * 5)
    client = FakeClient([error("SetLimitExceeded")])
    with pytest.raises(ModelPoolWait):
        chat_json(client, model="legacy", prompt="test", temperature=0, provider="byteplus")
    assert client.chat.completions.calls == 5
    assert [row["model"] for row in client.chat.completions.requests] == [f"model-{slot}" for slot in range(1, 6)]
    assert not pool.has_capacity()


def test_disabling_auto_switch_keeps_current_model_and_still_accounts_tokens(engine):
    activate(engine)
    with Session(engine) as db:
        config = db.get(ModelPoolSettings, 1)
        config.active_slot = 2
        config.auto_switch = False
        db.commit()
    client = FakeClient([completion()])
    chat_json(client, model="legacy", prompt="test", temperature=0, provider="byteplus")
    assert client.chat.completions.requests[0]["model"] == "model-2"
    with Session(engine) as db:
        db.get(ModelQuota, db.get(ManagedModel, 2).quota_id).exhausted = True
        db.commit()
    with pytest.raises(ModelPoolWait):
        chat_json(client, model="legacy", prompt="test", temperature=0, provider="byteplus")
    assert client.chat.completions.calls == 1


def test_scoring_restarts_three_run_majority_after_model_quota_failure(engine, monkeypatch):
    from app.pipeline.scoring import run_scoring
    from app.schemas.schemas import Item as ItemSchema, PerIdeaScore
    activate(engine)
    monkeypatch.setattr(settings, "llm_max_retries", 0)
    data = json.dumps({"elaboration_analysis": [{"idea_id": "idea", "target": "", "mechanism": "", "context": "", "goal": ""}]})
    client = FakeClient([completion(data), error("SetLimitExceeded"), completion(data), completion(data), completion(data), completion('{}')])
    _, meta = run_scoring(ItemSchema(id="test", name="Đũa", description=""), 1, 1, ["Que chỉ"],
        [PerIdeaScore(idea_id="idea", original="làm que chỉ", normalized="que chỉ", code="Que chỉ", originality=0, elaboration=1)], client, runs=3)
    assert meta["model"] == "model-2"
    assert len(meta["discarded_model_groups"]) == 1
    assert all(row["model"] == "model-2" for row in meta["llm_runs"])
    assert [row["model"] for row in client.chat.completions.requests][:5] == ["model-1", "model-1", "model-2", "model-2", "model-2"]
    with Session(engine) as db:
        assert all(row.reserved_tokens == 0 for row in db.scalars(select(ModelQuota)))
        assert db.scalar(select(func.sum(ModelQuota.spent_tokens))) == 600


def test_thinking_parameters_follow_actual_model_capability(engine):
    activate(engine)
    with Session(engine) as db:
        db.get(ManagedModel, 1).thinking_mode = "unsupported"
        db.commit()
    client = FakeClient([completion()])
    pool.complete(client, {**REQUEST, "reasoning_effort": "high", "extra_body": {"thinking": {"type": "enabled"}}},
                  provider="byteplus", stage="audit", call_id="capability")
    actual = client.chat.completions.requests[0]
    assert "reasoning_effort" not in actual and "extra_body" not in actual


def test_admin_balance_reconciliation_and_revision_guard(engine):
    activate(engine)
    hold = pool.reserve(REQUEST, "audit", "unknown")
    actor = SimpleNamespace(id="admin-test")
    with Session(engine) as db:
        revision = db.get(ModelPoolSettings, 1).revision
        payload = ModelBalanceUpdate(expected_revision=revision, remaining_tokens=123456, note="Đã đối chiếu console")
        with pytest.raises(Exception) as failure:
            model_controller.update_balance(db, 1, payload, actor)
        assert failure.value.status_code == 409
    pool.settle(hold, error=TimeoutError())
    with Session(engine) as db:
        result = model_controller.update_balance(db, 1, payload, actor)
        assert result["models"][0]["remaining_tokens"] == 123456
        assert result["models"][0]["reserved_tokens"] == 0
        assert db.get(ModelTokenRequest, hold.id).status == "RECONCILED"
        with pytest.raises(Exception) as stale:
            model_controller.update_settings(db, PoolSettingsUpdate(expected_revision=revision, enabled=True), actor)
        assert stale.value.status_code == 409


def test_admin_api_requires_auth_and_never_returns_key(engine):
    def dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    try:
        with TestClient(app) as client:
            assert client.get("/api/admin/models").status_code == 401
            app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="test-admin")
            response = client.get("/api/admin/models")
            assert response.status_code == 200
            assert len(response.json()["models"]) == 5
            assert "test-only-key" not in response.text
            assert client.put("/api/admin/models/6", json={}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_admin_can_configure_confirm_and_enable_models_entirely_from_tab(engine, monkeypatch):
    def dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="test-admin")
    try:
        with TestClient(app) as client:
            snapshot = client.get("/api/admin/models").json()
            rejected = client.patch("/api/admin/models/settings", json={"expected_revision": snapshot["revision"], "enabled": True})
            assert rejected.status_code == 422
            model = {"label": "Dự phòng", "model_id": "model-b", "quota_key": "base-b", "enabled": False}
            response = client.put("/api/admin/models/2", json={"expected_revision": snapshot["revision"], **model})
            assert response.status_code == 200, response.text
            snapshot = response.json()
            response = client.post("/api/admin/models/2/balance", json={"expected_revision": snapshot["revision"],
                "remaining_tokens": 234567, "note": "Đã kiểm tra trên console"})
            assert response.status_code == 200, response.text
            snapshot = response.json()
            assert snapshot["models"][1]["remaining_tokens"] == 234567
            model["enabled"] = True
            snapshot = client.put("/api/admin/models/2", json={"expected_revision": snapshot["revision"], **model}).json()
            response = client.patch("/api/admin/models/settings", json={"expected_revision": snapshot["revision"], "enabled": True})
            assert response.status_code == 200, response.text
            snapshot = response.json()
            assert snapshot["enabled"] is True
            monkeypatch.setattr(settings, "byteplus_model", "new-env-value")
            assert client.get("/api/admin/models").json()["models"][0]["model_id"] == "model-a"
            assert client.put("/api/admin/models/3", json={"expected_revision": snapshot["revision"], **model}).status_code == 409
            assert client.patch("/api/admin/models/settings", json={"expected_revision": 0, "enabled": False}).status_code == 409
            assert client.post("/api/admin/models/2/balance", json={"expected_revision": snapshot["revision"],
                "quota_limit": 100, "remaining_tokens": 101, "note": "Số dư không hợp lệ"}).status_code == 422
            assert "test-only-key" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_missing_migration_keeps_legacy_inference_working_without_schema_errors(monkeypatch):
    empty = create_engine("sqlite://")
    monkeypatch.setattr(pool, "SessionLocal", lambda: Session(empty))
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "byteplus_model_pool_available", True)
    client = FakeClient([completion()])
    data, meta = chat_json(client, model="legacy", prompt="test", temperature=0, provider="byteplus")
    assert data == {"ok": True} and meta["model"] == "legacy"
    empty.dispose()


def test_waiting_for_models_does_not_consume_worker_attempt(engine, monkeypatch):
    activate(engine, (0,))
    monkeypatch.setattr(response_worker, "SessionLocal", lambda: Session(engine))
    with Session(engine) as db:
        db.add(Item(id="test", name="Đũa"))
        participant = Participant()
        db.add(participant)
        db.flush()
        row = Response(participant_id=participant.id, item_id="test", raw_input="test", mapping={}, scoring={},
            processing_state="RUNNING", processing_claim_token="claim", processing_attempts=1)
        db.add(row)
        db.commit()
        response_id = row.id
    response_worker._record_failure(response_id, "claim", "mapping", ModelPoolWait())
    with Session(engine) as db:
        row = db.get(Response, response_id)
        assert row.processing_state == "QUEUED" and row.processing_attempts == 0
        assert row.processing_error == "MODEL_POOL_WAIT"
        assert row.scoring_status == ResponseScoringStatus.COLLECTING
        assert db.scalar(select(PipelineAudit.event)) == "MODEL_POOL_WAIT"
    assert not response_worker.run_one_job()

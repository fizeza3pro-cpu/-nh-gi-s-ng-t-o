"""Kiểm tra khóa và tranh chấp trên PostgreSQL riêng, không dùng DATABASE_URL khảo sát."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.config import settings
from app.controllers import participant_controller, response_controller
from app.models.models import Item, Participant, Response
from app.schemas.schemas import ParticipantCreate, ScoreRequest
from scripts.prepare_database import prepare_database


@pytest.fixture()
def pg_engine(monkeypatch):
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Cần TEST_POSTGRES_URL trỏ tới PostgreSQL kiểm thử riêng.")
    schema = "aut_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema} -clock_timeout=3000 -cstatement_timeout=10000"})
    monkeypatch.setattr(settings, "async_processing_enabled", True)
    monkeypatch.setattr(settings, "survey_session_required", False)
    monkeypatch.setattr(settings, "participant_token_required", True)
    try:
        prepare_database(engine)
        prepare_database(engine)
        with Session(engine) as db:
            db.add(Item(id="test-item", name="Đũa", description="Đồ vật kiểm thử"))
            db.commit()
        yield engine
    finally:
        engine.dispose()
        # Chỉ xóa schema ngẫu nhiên do chính fixture này vừa tạo.
        assert schema.startswith("aut_test_") and len(schema) == 41
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_duplicate_wait_releases_item_lock_on_postgres(pg_engine, monkeypatch):
    with Session(pg_engine) as db:
        participant = Participant(ai_usage_group="LOW")
        db.add(participant)
        db.commit()
        participant_id = participant.id
    request = ScoreRequest(item_id="test-item", responses=["gõ nhịp"], request_id=uuid.uuid4(), wait_for_completion=True)

    def wait_with_other_connection(db, response_id, _participant_id):
        # Nếu request gốc giữ FOR UPDATE, NOWAIT trên connection khác sẽ báo lỗi.
        with Session(pg_engine) as worker:
            worker.scalar(select(Item).where(Item.id == "test-item").with_for_update(nowait=True))
            return response_controller._to_response(worker.get(Response, response_id))

    monkeypatch.setattr(response_controller, "_wait_for_response_completion", wait_with_other_connection)
    with Session(pg_engine) as db:
        first = response_controller.create_response(db, request, db.get(Participant, participant_id))
    with Session(pg_engine) as db:
        second = response_controller.create_response(db, request, db.get(Participant, participant_id))
        assert first.response_id == second.response_id
        assert db.scalar(select(func.count(Response.id))) == 1


def test_simultaneous_profile_creation_has_no_server_error(pg_engine):
    barrier = Barrier(2)
    payload = ParticipantCreate(email="race@example.test", full_name="Nguyễn Văn An", age=20,
                                gender="male", occupation="Sinh viên", ai_usage_group="LOW")

    def create():
        with Session(pg_engine) as db:
            barrier.wait(timeout=5)
            try:
                return 201, participant_controller.create_participant(db, payload).access_token
            except HTTPException as exc:
                return exc.status_code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert sorted(status for status, _ in results) in ([201, 403], [201, 409])
    assert sum(bool(token) for _, token in results) == 1
    with Session(pg_engine) as db:
        assert db.scalar(select(func.count(Participant.id))) == 1

"""Kiểm thử cấu hình triển khai, giới hạn tải và xung đột hồ sơ."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.controllers.participant_controller import _commit_profile, _email_hash
from app.core.rate_limit import RequestLimiter


def production_settings(**overrides):
    return Settings(_env_file=None, database_url="sqlite://", llm_provider="byteplus", app_env="production",
                    **{"jwt_secret": "a" * 32, "participant_email_secret": "b" * 32,
                       "cors_origins": "https://survey.example.test", **overrides})


@pytest.mark.parametrize("overrides", [{"jwt_secret": "change-me-in-env"},
                                      {"participant_email_secret": None}, {"cors_origins": "*"}])
def test_production_rejects_unsafe_configuration(overrides):
    with pytest.raises(ValidationError):
        production_settings(**overrides)


def test_jwt_rotation_does_not_change_email_lookup(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "participant_email_secret", "stable-email-secret")
    before = _email_hash("person@example.test")
    monkeypatch.setattr(settings, "jwt_secret", "rotated-jwt-secret")
    assert _email_hash("person@example.test") == before


def test_rate_limit_recovery_and_bounded_memory():
    limiter = RequestLimiter(max_keys=2)
    limiter.check(("login", "a"), 1, now=100)
    with pytest.raises(HTTPException) as error:
        limiter.check(("login", "a"), 1, now=110)
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "50"
    limiter.check(("login", "a"), 1, now=160)
    limiter.check(("login", "b"), 1, now=160)
    limiter.check(("login", "c"), 1, now=160)
    assert len(limiter.entries) == 2


def test_profile_conflict_rolls_back_without_returning_token():
    db = Mock()
    db.commit.side_effect = IntegrityError("insert", {}, Exception("unique conflict"))
    with pytest.raises(HTTPException) as error:
        _commit_profile(db)
    assert error.value.status_code == 409
    db.rollback.assert_called_once()


def test_database_preparation_is_repeatable_and_refuses_unversioned_data():
    from sqlalchemy import create_engine, inspect, text
    from scripts.prepare_database import prepare_database
    engine = create_engine("sqlite://")
    prepare_database(engine)
    prepare_database(engine)
    assert {"participants", "responses", "alembic_version"}.issubset(inspect(engine).get_table_names())
    other = create_engine("sqlite://")
    with other.begin() as connection:
        connection.execute(text("CREATE TABLE important_data (id INTEGER PRIMARY KEY)"))
    with pytest.raises(RuntimeError, match="chưa có Alembic version"):
        prepare_database(other)
    assert inspect(other).get_table_names() == ["important_data"]
    engine.dispose()
    other.dispose()

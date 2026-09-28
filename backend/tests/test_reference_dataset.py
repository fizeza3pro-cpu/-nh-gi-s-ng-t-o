import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import BACKEND_ENV_FILE, Settings
from app.config import settings
from app.controllers.response_controller import _client
from app.pipeline.dynamic_mapping import run_idea_extraction
from app.pipeline.reference_dataset import (
    load_reference_cases,
    reference_cases_json,
    select_reference_cases,
)
from app.schemas.schemas import Item
from tests.fake_llm import FakeClient


def test_reference_dataset_has_unique_ids_and_all_pipeline_stages():
    cases = load_reference_cases()
    ids = [case["id"] for case in cases]

    assert len(cases) >= 12
    assert len(ids) == len(set(ids))
    assert {case["stage"] for case in cases} == {"extraction", "curator", "challenger"}


def test_reference_retrieval_is_limited_and_stage_scoped():
    selected = select_reference_cases(
        "challenger",
        item_name="Gạch",
        query_texts=["Nung gạch để tích nhiệt rồi sưởi chân"],
        limit=3,
    )

    assert len(selected) == 3
    assert all(case["stage"] == "challenger" for case in selected)
    assert selected[0]["id"] == "CH-CREATE-HEAT-01"


def test_extraction_prompt_contains_retrieved_reference_cases():
    response = json.dumps(
        {
            "ideas": [
                {
                    "line_index": 0,
                    "original": "Nung gạch để sưởi chân",
                    "normalized": "Dùng gạch nóng để giữ ấm",
                    "status": "VALID",
                    "duplicate_of_index": None,
                    "uses_target_object": True,
                    "object_used": "Gạch",
                    "target_object_role": "Vật tích nhiệt",
                    "functional_signature": {
                        "goal": "giữ ấm",
                        "object_role": "vật tích nhiệt",
                        "mechanism": "hấp thụ và truyền nhiệt",
                        "transformation": "nung nóng",
                        "target": "chân",
                        "context": "",
                    },
                    "reason": "",
                }
            ]
        },
        ensure_ascii=False,
    )
    client = FakeClient([response])

    result, meta = run_idea_extraction(
        Item(id="gach", name="Gạch", description="Một viên gạch"),
        ["Nung gạch để sưởi chân"],
        client,
    )

    prompt = client.chat.completions.requests[0]["messages"][0]["content"]
    assert result.ideas[0].status == "VALID"
    assert "VÍ DỤ THAM KHẢO ĐÃ ĐƯỢC GÁN NHÃN" in prompt
    assert "Câu ngắn vẫn hợp lệ" in prompt
    assert meta["provider"] in {"byteplus", "groq", "cloudflare"}


def test_settings_can_switch_between_three_providers_without_changing_code():
    byteplus = Settings(
        _env_file=None,
        database_url="sqlite://",
        llm_provider="BYTEPLUS",
        byteplus_api_key="byteplus-key",
        byteplus_model="byteplus-model",
        byteplus_code_curator_model="byteplus-curator",
    )
    groq = Settings(
        _env_file=None,
        database_url="sqlite://",
        llm_provider="GROQ",
        groq_api_key="groq-key",
        groq_model="groq-model",
        groq_code_curator_model="groq-curator",
        groq_reasoning_effort="low",
    )
    cloudflare = Settings(
        _env_file=None,
        database_url="sqlite://",
        llm_provider="CLOUDFLARE",
        cloudflare_api_token="cloudflare-token",
        cloudflare_account_id="account-123",
        cloudflare_model="@cf/test/default-model",
        cloudflare_code_curator_model="@cf/test/curator-model",
        cloudflare_max_tokens=3072,
    )

    assert byteplus.active_llm_api_key == "byteplus-key"
    assert byteplus.active_llm_model == "byteplus-model"
    assert byteplus.active_curator_model == "byteplus-curator"
    assert groq.active_llm_api_key == "groq-key"
    assert groq.active_llm_base_url == "https://api.groq.com/openai/v1"
    assert groq.active_llm_model == "groq-model"
    assert groq.active_curator_model == "groq-curator"
    assert groq.active_reasoning_effort == "low"
    assert byteplus.active_reasoning_effort == "minimal"
    assert cloudflare.active_llm_api_key == "cloudflare-token"
    assert cloudflare.active_llm_base_url == (
        "https://api.cloudflare.com/client/v4/accounts/account-123/ai/v1"
    )
    assert cloudflare.active_llm_model == "@cf/test/default-model"
    assert cloudflare.active_curator_model == "@cf/test/curator-model"
    assert cloudflare.active_reasoning_effort is None
    assert cloudflare.active_max_tokens == 3072
    assert groq.active_max_tokens is None


def test_settings_always_load_env_from_backend_directory():
    assert BACKEND_ENV_FILE == Path(__file__).resolve().parents[1] / ".env"
    assert Settings.model_config["env_file"] == BACKEND_ENV_FILE


def test_settings_rejects_missing_provider_instead_of_falling_back_to_byteplus(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with pytest.raises(ValidationError, match="llm_provider"):
        Settings(_env_file=None, database_url="sqlite://")


def test_openai_compatible_client_uses_selected_groq_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "groq_base_url", "https://api.groq.com/openai/v1")

    client = _client()

    assert str(client.base_url) == "https://api.groq.com/openai/v1/"
    assert client.api_key == "test-groq-key"
    assert client.max_retries == 0


def test_openai_compatible_client_uses_selected_cloudflare_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "cloudflare")
    monkeypatch.setattr(settings, "cloudflare_api_token", "test-cloudflare-token")
    monkeypatch.setattr(settings, "cloudflare_account_id", "account-456")

    client = _client()

    assert str(client.base_url) == (
        "https://api.cloudflare.com/client/v4/accounts/account-456/ai/v1/"
    )
    assert client.api_key == "test-cloudflare-token"
    assert client.max_retries == 0


def test_reference_prompt_is_compact_and_omits_redundant_stage():
    selected = reference_cases_json(
        "extraction",
        item_name="Gạch",
        query_texts=["Nung gạch để sưởi chân"],
        limit=2,
    )

    assert '"stage"' not in selected
    assert "\n" not in selected

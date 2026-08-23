import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
import app.storage as storage_mod
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Buộc mock mode + ghi response vào thư mục tạm để không đụng data thật.
    monkeypatch.setattr(main_mod.settings, "mock_mode", True)
    monkeypatch.setattr(storage_mod, "RESPONSES_DIR", tmp_path)
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_items(client):
    r = client.get("/api/items")
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()}
    assert "dua" in ids


def test_score_then_history_roundtrip(client):
    r = client.post("/api/score", json={"item_id": "dua", "raw_input": "gõ nhịp, làm cọc cây, đo nước"})
    assert r.status_code == 200
    body = r.json()
    rid = body["response_id"]
    assert body["scoring"]["fluency"] >= 1

    # Có trong danh sách lịch sử.
    lst = client.get("/api/responses").json()
    assert any(row["response_id"] == rid for row in lst)

    # Lấy chi tiết lại được.
    detail = client.get(f"/api/responses/{rid}")
    assert detail.status_code == 200
    assert detail.json()["response_id"] == rid


def test_score_empty_input_rejected(client):
    r = client.post("/api/score", json={"item_id": "dua", "raw_input": "   "})
    assert r.status_code == 400


def test_unknown_item_404(client):
    r = client.post("/api/score", json={"item_id": "khong_ton_tai", "raw_input": "abc"})
    assert r.status_code == 404

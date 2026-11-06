import json
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.controllers import code_audit_worker as worker, response_controller
from app.models.models import Item, ItemCode, Participant, Response, ResponseIdea, PipelineAudit
from tests.fake_llm import FakeClient


def test_auto_audit_merges_only_after_member_checks(monkeypatch):
    """Gộp xuyên response, giữ mã đích và đồng bộ cả centroid cùng JSON hiển thị."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    signature = {"goal": "chứa đồ", "object_role": "vật chứa", "mechanism": "khoang rỗng"}
    with Session(engine) as db:
        db.add_all([Item(id="balo", name="Balo", description="Balo có khoang"), Participant(id="person")])
        for key, text in [("a", "đựng sách"), ("z", "đựng quân nhu")]:
            db.add(ItemCode(id=key, item_id="balo", name=f"Balo chứa {key}", normalized_name=key,
                description="Dùng Balo làm vật chứa", functional_signature=signature,
                inclusion_rules=["Chứa đồ bên trong khoang balo"], exclusion_rules=["Không gồm đốt làm nhiên liệu"],
                positive_examples=[text], embedding=[1., 0.], embedding_model="test"))
            db.add(Response(id=f"response-{key}", participant_id="person", item_id="balo", raw_input=text,
                            mapping={"ideas": []}, processing_state="DONE"))
            db.add(ResponseIdea(id=f"idea-{key}", response_id=f"response-{key}", code_id=key,
                original=text, normalized=text, mapping_status="VALID", embedding=[1., 0.], embedding_model="test"))
        db.commit()
    def verdict(source):
        return {"source_text": source, "relation": "SAME_CATEGORY", "goal_match": True,
                "role_match": True, "exclusion_hit": False, "evidence": source, "reason": "Cùng chức năng chứa"}
    client = FakeClient([json.dumps(verdict("đựng quân nhu"), ensure_ascii=False),
                         json.dumps({"checks": [verdict("đựng sách"), verdict("đựng quân nhu")]}, ensure_ascii=False)])
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(worker, "configured_embedding_model", lambda: "test")
    monkeypatch.setattr(worker.settings, "mock_mode", False)
    monkeypatch.setattr("app.pipeline.clients.chat_client", lambda: client)
    assert worker.run_one_audit()
    assert not worker.run_one_audit()
    with Session(engine) as db:
        assert db.get(ItemCode, "z").merged_into_id == "a"
        assert db.get(ItemCode, "z").centroid_count == 0
        assert db.get(ItemCode, "a").centroid_count == 2
        assert db.get(ResponseIdea, "idea-z").code_id == "a"
        assert db.get(Response, "response-z").mapping["ideas"][0]["code"] == "Balo chứa a"
        assert db.get(Item, "balo").calibration_dirty
        assert db.scalar(select(PipelineAudit)).payload["reason"] == "MERGED"


def test_explicit_codebook_conflict_is_audited_before_unrelated_similar_pair(monkeypatch):
    """Chọn đúng cặp tranh chấp trước; nhận việc không đồng nghĩa được phép gộp."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Item(id="item", name="Đồ vật"), Participant(id="p")])
        for key in ("a", "b", "z"):
            signature = {"goal": key if key == "z" else "chứa đồ", "object_role": key, "mechanism": key}
            db.add(ItemCode(id=key, item_id="item", name=key, normalized_name=key,
                            functional_signature=signature, positive_examples=[f"ý {key}"],
                            embedding=[0., 1.] if key == "z" else [1., 0.], embedding_model="test"))
        db.add(Response(id="r", participant_id="p", item_id="item", raw_input="ý đang chờ", mapping={}))
        db.add(ResponseIdea(id="i", response_id="r", original="ý đang chờ", normalized="ý đang chờ",
            mapping_status="VALID", mapping_evidence={"policy_gates": {"codebook_conflict": True},
                "existing_code_evaluations": [{"source": "FINAL_ADJUDICATOR", "verdict": "MATCH", "code_id": key}
                                              for key in ("a", "z")]}))
        db.commit()
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    job = worker._claim()
    assert {job[3]["id"], job[4]["id"]} == {"a", "z"}
    with Session(engine) as db:
        assert db.scalar(select(PipelineAudit)).payload["trigger"] == "CODEBOOK_CONFLICT"
        assert all(db.get(ItemCode, key).merged_into_id is None for key in ("a", "b", "z"))

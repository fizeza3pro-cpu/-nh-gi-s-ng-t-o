"""Chạy ca hồi quy qua provider thật trên DB kiểm thử riêng, lưu báo cáo token."""
import json
import os
import sys
import uuid
from pathlib import Path


def main():
    from dotenv import dotenv_values
    isolated = dotenv_values(".validation.env")["DATABASE_URL"]
    if ":55439/" not in isolated:
        raise RuntimeError("Chỉ chạy trên PostgreSQL thử nghiệm cổng 55439.")
    os.environ["DATABASE_URL"] = isolated
    from app.controllers import response_worker
    from app.config import settings
    from app.db import SessionLocal
    from app.models.models import Item, Participant, Response, ResponseIdea
    from sqlalchemy import select
    settings.mock_mode = False
    suffix = uuid.uuid4().hex[:8]
    participant = str(uuid.uuid4())
    cases = [
        ("balo", "Balo quân nhu", "Balo có khoang chứa và quai đeo.", [
            ["dùng để đựng đồ quân nhu", "bỏ sách vào làm cặp đi học"],
            ["dùng làm nguyên liệu đốt", "dùng để đựng đồ khi bơi qua sông", "tặng cho anh ba xỉn"],
        ]),
        ("xeng", "Xẻng công binh", "Dụng cụ đào nhỏ gọn.", [
            ["dùng để đào hầm hào", "dùng để đóng cọc", "đào công sự dã chiến", "dùng để xúc than"],
        ]),
    ]
    results = []
    edge_cases = "--edge-cases" in sys.argv
    if edge_cases:
        cases = [("vo-dan", "Vỏ đạn", "Vỏ kim loại đã rỗng.", [[
            "làm đồ chơi", "làm trang sức", "làm chặn giấy", "dùng để dọa người khác",
            "tặng cho bạn An", "tặng cho bạn Bình", "dùng để gãi lưng",
        ]])]
    output=Path('../.artifacts/live-edge-acceptance.json' if edge_cases else '../.artifacts/live-acceptance.json')
    if "--resume" in sys.argv:
        results = json.loads(output.read_text(encoding="utf-8"))
        for result in results:
            for _ in range(settings.resolver_max_attempts):
                with SessionLocal() as db:
                    row = db.get(Response, result["response_id"])
                    resolving = bool((row.mapping or {}).get("ideas"))
                    if resolving and (row.scoring_status.value != "PENDING_REVIEW" or row.resolution_attempts >= settings.resolver_max_attempts):
                        break
                    token = str(uuid.uuid4())
                    row.processing_state = "RUNNING"
                    row.processing_claim_token = token
                    db.commit()
                response_worker._run_mapping(result["response_id"], token, resolving=resolving)
            with SessionLocal() as db:
                row = db.get(Response, result["response_id"])
                result.update(mapping=row.mapping, metadata=row.mapping_meta,
                              resolution_attempts=row.resolution_attempts, error=None)
            print(json.dumps({key: value for key, value in result.items() if key != "metadata"}, ensure_ascii=False), flush=True)
        output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        assert all(idea["coding_state"] in {"ASSIGNED", "NOT_APPLICABLE"}
                   for result in results for idea in result["mapping"]["ideas"]), "Còn ý chưa phân loại"
        if edge_cases:
            ideas = results[0]["mapping"]["ideas"]
            assert all(idea["status"] == "VALID" for idea in ideas[:5] + ideas[6:])
            assert ideas[5]["status"] == "DUPLICATE", "Đổi người nhận không tạo công dụng mới"
            for left, right in [(0, 1), (2, 3), (4, 6)]:
                assert ideas[left]["code"] != ideas[right]["code"], "Hai chức năng bị gộp sai"
            return
        first = results[0]["mapping"]["ideas"]
        second = results[1]["mapping"]["ideas"]
        assert first[0]["code"] == first[1]["code"] == second[1]["code"], "Nhóm chứa đồ chưa thống nhất"
        assert len({second[index]["code"] for index in range(3)}) == 3, "Nhiên liệu/chứa/quà bị gộp"
        return
    with SessionLocal() as db:
        db.add(Participant(id=participant, full_name="Kiểm thử tự động"))
        db.commit()
    for prefix, name, description, submissions in cases:
        item_id = f"live-{suffix}-{prefix}"
        with SessionLocal() as db:
            db.add(Item(id=item_id, name=name, description=description))
            db.commit()
        for lines in submissions:
            token = str(uuid.uuid4())
            with SessionLocal() as db:
                row = Response(participant_id=participant, item_id=item_id, raw_input="\n".join(lines),
                    input_lines=lines, request_id=str(uuid.uuid4()), processing_state="RUNNING",
                    processing_claim_token=token, mapping={"ideas": []}, data_source="DEV")
                db.add(row); db.commit(); response_id=row.id
            try:
                response_worker._run_mapping(response_id, token)
                error = None
            except Exception as exc:
                error = {"type": type(exc).__name__, "metadata": getattr(exc, "metadata", {})}
            with SessionLocal() as db:
                row=db.get(Response,response_id)
                result={"response_id":response_id,"item":name,"error":error,"mapping":row.mapping,"metadata":row.mapping_meta}
                results.append(result)
                print(json.dumps({k:v for k,v in result.items() if k!='metadata'},ensure_ascii=False),flush=True)
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

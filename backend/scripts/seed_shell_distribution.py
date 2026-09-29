"""Tạo 5 người và 15 lượt mô phỏng có phân bố 150 ý; không giả mạo dữ liệu thực nghiệm."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models.models import Item, ItemCode, Participant, Response, ResponseIdea, ResponseScoringStatus, PipelineAudit
from app.pipeline.shell_reference import plan_shell_reference
from app.pipeline.codebook_service import (
    originality_for_response, refresh_item_scoring_state, refresh_final_frequency_scores,
    qualifying_participant_count, qualifying_idea_count, _code_live_counts,
    item_is_ready_for_scoring,
)
from app.schemas.schemas import MappingResult, ScoringResult
from app.pipeline.scoring import count_meaningful_words


CORPUS = "shell-synthetic-distribution-150"
# Phân bố giả định phục vụ kiểm thử; không phải ước lượng từ dân số khảo sát.
COUNTS = {"container": 30, "jewelry": 24, "ornament": 20, "model": 16, "gift": 12,
          "recycle": 8, "sale": 8, "weight": 7, "sound": 6, "play": 4, "count": 3,
          "marker": 3, "support": 2, "teaching": 1, "dig": 1, "housing": 1,
          "electric": 1, "thermal": 1, "evidence": 1, "symbol": 1}
VARIANTS = {
    "container": ["Làm lọ cắm hoa", "Làm hộp đựng bút"],
    "jewelry": ["Làm mặt dây chuyền", "Làm khuyên tai"],
    "ornament": ["Đính làm họa tiết trên áo", "Trang trí khung ảnh"],
    "model": ["Ghép mô hình xe để trưng bày", "Ghép tượng con chim để trưng bày"],
    "gift": ["Tặng làm quà kỷ niệm"], "recycle": ["Tái chế thu hồi kim loại làm nguyên liệu"],
    "sale": ["Bán nguyên vỏ lấy tiền"], "weight": ["Làm vật chặn giấy"],
    "sound": ["Làm chuông gió"], "play": ["Làm quân cờ"], "count": ["Làm vật học đếm"],
    "marker": ["Đánh dấu vị trí gieo hạt"], "support": ["Làm chân kê mô hình"],
    "teaching": ["Làm mẫu vật minh họa lịch sử"], "dig": ["Làm dụng cụ xới đất"],
    "housing": ["Làm vỏ bảo vệ bộ máy đồng hồ nhỏ"],
    "electric": ["Làm tiếp điểm dẫn điện trong mô hình"],
    "thermal": ["Làm chi tiết tản nhiệt"], "evidence": ["Lưu làm vật chứng của sự kiện"],
    "symbol": ["Làm biểu tượng trong tác phẩm về hòa bình"],
}


def seed_id(kind, index):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"aut/{CORPUS}/{kind}/{index}"))


def build_corpus():
    """Chia đều 15 lượt; hai ý cùng mã trong một lượt phải là hai sản phẩm khác nhau."""
    buckets = [[] for _ in range(15)]
    for key, count in COUNTS.items():
        for _ in range(count):
            candidates = [i for i, bucket in enumerate(buckets)
                          if len(bucket) < 10 and sum(k == key for k, _, _ in bucket) < len(VARIANTS[key])]
            if not candidates:
                raise ValueError(f"Không thể xếp mã {key} mà vẫn giữ giới hạn 10 ý.")
            index = min(candidates, key=lambda i: (len(buckets[i]), i))
            variant = sum(k == key for k, _, _ in buckets[index])
            text = VARIANTS[key][variant]
            # Chỉ chấm thêm bối cảnh khi câu mô phỏng thực sự chứa đoạn này.
            details = {"context": "trong giờ thực hành"} if index % 3 == 1 else {}
            if details:
                text += " trong giờ thực hành"
            buckets[index].append((key, text, details))
    return buckets


def populate(db):
    """Nạp nguyên tử corpus đã gán mã có kiểm soát, dùng công thức thật để tính Originality."""
    if settings.survey_data_source != "PILOT":
        raise RuntimeError("Corpus này chỉ được phép bổ sung vào mẫu PILOT.")
    item = db.scalar(select(Item).where(Item.id == "vo_dan").with_for_update())
    if item is None:
        raise RuntimeError("Thiếu đồ vật Vỏ đạn.")
    prior = db.scalars(select(Response).where(Response.id.in_([seed_id("response", i) for i in range(15)]))).all()
    if prior:
        if len(prior) != 15 or any(row.data_source != "SYNTHETIC" or row.mapping_meta.get("corpus") != CORPUS for row in prior):
            raise RuntimeError("Corpus cũ thiếu hoặc xung đột; không ghi đè dữ liệu.")
        return {"created": 0, "reason": "Corpus đã tồn tại"}
    plan = plan_shell_reference(db.scalars(select(ItemCode).where(ItemCode.item_id == item.id)).all())
    if any(match is None for _, match in plan):
        raise RuntimeError("Cần nạp đủ bộ mã tham chiếu trước.")
    codes = {entry["key"]: match for entry, match in plan}
    people = [Participant(id=seed_id("participant", i), full_name=f"[SYNTHETIC] Người mô phỏng {i + 1}",
                          occupation="Dữ liệu kiểm thử tự tạo") for i in range(5)]
    db.add_all(people)
    db.flush()
    rows = []
    evidence = {}
    for index, bucket in enumerate(build_corpus()):
        row = Response(id=seed_id("response", index), participant_id=people[index % 5].id,
                       item_id=item.id, raw_input="\n".join(text for _, text, _ in bucket),
                       input_lines=[text for _, text, _ in bucket], data_source="SYNTHETIC",
                       protocol="SYNTHETIC_TOP10", processing_state="DONE",
                       mapping={"ideas": []}, mapping_completed_at=datetime.now(timezone.utc),
                       mapping_meta={"source": "SYNTHETIC", "corpus": CORPUS, "calibration_source": "PILOT",
                                     "mapping_method": "CURATED_FIXTURE", "empirical_frequency": False},
                       scoring_status=ResponseScoringStatus.COLLECTING)
        db.add(row)
        db.flush()
        mapped = []
        for line, (key, text, details) in enumerate(bucket):
            code = codes[key]
            idea_id = seed_id("idea", f"{index}:{line}")
            evidence[idea_id] = details
            db.add(ResponseIdea(id=idea_id, response_id=row.id, code_id=code.id, original=text,
                                normalized=text, line_index=line, coding_state="ASSIGNED", mapping_status="VALID",
                                functional_signature=code.functional_signature, curator_decision="SYNTHETIC_FIXTURE",
                                reason="Ý minh họa do AI biên soạn; không phải quan sát khảo sát.",
                                mapping_evidence={"source": "SYNTHETIC", "corpus": CORPUS}))
            mapped.append({"idea_id": idea_id, "original": text, "normalized": text, "code": code.name,
                           "status": "VALID", "line_index": line, "functional_signature": code.functional_signature,
                           "reason": "[SYNTHETIC] Ý minh họa được gán mã có kiểm soát."})
        row.mapping = MappingResult.model_validate({"ideas": mapped}).model_dump()
        rows.append(row)
    old_threshold = item.scoring_min_participants
    item.scoring_min_participants = 5
    db.flush()
    refresh_item_scoring_state(db, item)
    if not item_is_ready_for_scoring(db, item):
        raise RuntimeError("Chưa đủ điều kiện chấm hoặc đồ vật đang tạm dừng; hủy nạp corpus.")
    for row in rows:
        fluency, flexibility, names, per_idea, basis = originality_for_response(db, row)
        scored = [score.model_copy(update={"elaboration": 1 + len(evidence[score.idea_id]),
                   "elaboration_details": evidence[score.idea_id],
                   "meaningful_word_count": count_meaningful_words(score.original, item.name),
                   "note": "[SYNTHETIC] Bằng chứng chi tiết do bộ dữ liệu kiểm thử cung cấp."}) for score in per_idea]
        result = ScoringResult(fluency=fluency, flexibility=flexibility, flexibility_codes=names,
                              originality=sum(s.originality for s in scored), elaboration=sum(s.elaboration for s in scored),
                              per_idea_scores=scored, summary_vi="[DỮ LIỆU MÔ PHỎNG] Phân bố giả định để kiểm tra chấm điểm, không phải kết quả nghiên cứu.")
        row.scoring = result.model_dump()
        row.scoring_meta = {"source": "SYNTHETIC", "frequency_basis": basis, "elaboration_method": "CURATED_FIXTURE"}
        for field in ("fluency", "flexibility", "originality", "elaboration"):
            setattr(row, field, getattr(result, field))
        row.scoring_status = ResponseScoringStatus.FINAL
        row.scored_at = datetime.now(timezone.utc)
    db.flush()
    refresh_final_frequency_scores(db, item.id)
    item.scores_dirty = True
    db.add(PipelineAudit(item_id=item.id, event="SYNTHETIC_CORPUS_IMPORTED", payload={
        "corpus": CORPUS, "participants": 5, "responses": 15, "ideas": 150,
        "previous_min_participants": old_threshold, "min_participants": 5,
        "assumed_counts": COUNTS, "calibration_source": "PILOT", "empirical": False}))
    counts = _code_live_counts(db, item.id)
    denominator = sum(value[2] for value in counts.values())
    return {"created": 15, "participants_added": 5, "ideas_added": 150,
            "qualifying_participants": qualifying_participant_count(db, item.id),
            "qualifying_ideas": qualifying_idea_count(db, item.id),
            "min_participants": item.scoring_min_participants, "min_ideas": item.scoring_min_ideas,
            "synthetic_originality_distribution": dict(Counter(s["originality"] for row in rows for s in row.scoring["per_idea_scores"])),
            "frequencies": [{"key": key, "seed_count": COUNTS[key], "combined_count": counts[codes[key].id][2],
                             "frequency": counts[codes[key].id][2] / denominator} for key in COUNTS]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"participants": 5, "responses": 15, "ideas": sum(COUNTS.values()), "counts": COUNTS}))
    if not args.apply:
        return
    artifact = Path(__file__).resolve().parents[2] / ".artifacts"
    artifact.mkdir(exist_ok=True)
    with SessionLocal() as db, db.begin():
        item = db.scalar(select(Item).where(Item.id == "vo_dan").with_for_update())
        if item is None:
            raise RuntimeError("Thiếu đồ vật Vỏ đạn.")
        saved = {"item": {c.name: getattr(item, c.name) for c in Item.__table__.columns},
                 "responses": [{c.name: getattr(row, c.name) for c in Response.__table__.columns}
                               for row in db.scalars(select(Response).where(Response.item_id == item.id)).all()]}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = artifact / f"shell-before-synthetic-{stamp}.json"
        backup.write_text(json.dumps(saved, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        report = populate(db)
    report["backup"] = str(backup)
    (artifact / "shell-synthetic-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()

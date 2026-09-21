"""Nạp corpus kiểm thử đa dạng, đủ ngưỡng chấm điểm cho đồ vật Đũa.

Script có thể chạy lại: chỉ dữ liệu mang tiền tố seed của chính script bị thay thế;
response và participant có sẵn của nghiên cứu được giữ nguyên.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from sqlalchemy import delete, func, inspect, select

from app.config import settings
from app.controllers.response_controller import reprocess_item_scores_in_session
from app.db import SessionLocal
from app.models.models import (
    CodeMaturityStatus,
    CodeValidationStatus,
    Item,
    ItemCode,
    Participant,
    Response,
    ResponseIdea,
    ResponseScoringStatus,
)
from app.pipeline.codebook_service import refresh_item_scoring_state


ITEM_ID = "dua"
PARTICIPANT_PREFIX = "seed-participant-"
RESPONSE_PREFIX = "seed-dua-response-"
CODE_PREFIX = "seed-dua-code-"


COMMON_USES = [
    ("go_nhip", "Nhạc cụ gõ bằng đũa", "Gõ hai chiếc đũa để tạo nhịp"),
    ("danh_dau", "Cọc đánh dấu bằng đũa", "Cắm đũa làm cọc đánh dấu vị trí"),
    ("que_do", "Que đo bằng đũa", "Dùng đũa làm que đo độ sâu"),
]

MEDIUM_USES = [
    ("chong_cay", "Thanh chống cây bằng đũa", "Dùng đũa chống cây non"),
    ("thu_cong", "Khung thủ công bằng đũa", "Ghép đũa thành khung thủ công"),
    ("mo_hinh", "Mô hình kiến trúc bằng đũa", "Dựng mô hình kiến trúc bằng đũa"),
    ("kep_giay", "Kẹp giấy bằng đũa", "Buộc hai đũa thành kẹp giữ giấy"),
    ("ve_mau", "Dụng cụ vẽ bằng đũa", "Chấm đầu đũa vào màu để tạo hoa văn"),
    ("truyen_tin", "Tín hiệu bằng đũa", "Gõ đũa theo nhịp để truyền tín hiệu"),
]

UNCOMMON_USES = [
    ("khoa_tui", "Chốt khoá túi bằng đũa", "Luồn đũa làm chốt khoá miệng túi"),
    ("la_ban", "Kim la bàn nổi bằng đũa", "Cân đũa trên mặt nước để quan sát hướng"),
    ("may_det", "Thanh dẫn sợi dệt bằng đũa", "Dùng đũa dẫn sợi trong khung dệt nhỏ"),
    ("gia_dien_thoai", "Giá điện thoại bằng đũa", "Ghép đũa thành giá đỡ điện thoại"),
]

RARE_USES = [
    ("bong_nang", "Đồng hồ bóng nắng bằng đũa", "Dùng bóng đũa để ước lượng thời gian"),
    ("am_thoa", "Bộ cộng hưởng âm bằng đũa", "Ghép đũa thành bộ cộng hưởng âm thanh nhỏ"),
    ("ma_noi", "Mã nổi xúc giác bằng đũa", "Xếp đầu đũa thành ký hiệu xúc giác"),
    ("loc_nuoc", "Khung lọc nước bằng đũa", "Đan đũa thành khung giữ nhiều lớp vật liệu lọc"),
    ("con_lan", "Con lăn vận chuyển bằng đũa", "Xếp đũa song song làm con lăn cho vật nhẹ"),
    ("ban_do_noi", "Bản đồ nổi bằng đũa", "Bẻ và ghép đũa thành đường biên bản đồ nổi"),
]


def _code_id(slug: str) -> str:
    return f"{CODE_PREFIX}{slug}"


def _participant(index: int) -> Participant:
    token = f"aut-scoring-seed-v1-{index:02d}"
    return Participant(
        id=f"{PARTICIPANT_PREFIX}{index:02d}",
        full_name=f"Người kiểm thử {index:02d}",
        email_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        email_masked=f"seed{index:02d}***@example.test",
        email_verified_at=datetime.now(timezone.utc),
        age=18 + (index % 25),
        gender=["male", "female", "other", "prefer_not_to_say"][index % 4],
        occupation=["Sinh viên", "Giáo viên", "Thiết kế", "Kỹ thuật viên"][index % 4],
        device_hash=hashlib.sha256(f"{token}-device".encode("utf-8")).hexdigest(),
    )


def _uses_for_response(index: int) -> list[tuple[str, str, str]]:
    uses = [COMMON_USES[index % len(COMMON_USES)], MEDIUM_USES[index % len(MEDIUM_USES)]]
    if index < 12:
        uses.append(UNCOMMON_USES[index % len(UNCOMMON_USES)])
    if index < len(RARE_USES):
        uses.append(RARE_USES[index])
    return uses


def main() -> None:
    with SessionLocal() as db:
        item = db.get(Item, ITEM_ID)
        if item is None:
            raise RuntimeError("Không tìm thấy item 'dua'; hãy chạy migration/seed item trước.")

        # Chỉ thay thế corpus do script này quản lý, không đụng dữ liệu khảo sát thật.
        db.execute(delete(Response).where(Response.id.like(f"{RESPONSE_PREFIX}%")))
        db.execute(delete(ItemCode).where(ItemCode.id.like(f"{CODE_PREFIX}%")))
        db.execute(delete(Participant).where(Participant.id.like(f"{PARTICIPANT_PREFIX}%")))
        db.flush()

        participants = [_participant(index) for index in range(1, 33)]
        db.add_all(participants)

        all_uses = COMMON_USES + MEDIUM_USES + UNCOMMON_USES + RARE_USES
        codes = {
            slug: ItemCode(
                id=_code_id(slug),
                item_id=ITEM_ID,
                name=name,
                normalized_name=f"seed {slug}",
                description=normalized,
                validation_status=CodeValidationStatus.ACCEPTED,
                maturity_status=CodeMaturityStatus.ACTIVE,
                confidence=0.99,
                relevance_reason="Dữ liệu kiểm thử có kiểm soát.",
                created_by="TEST_SEED",
                admin_locked=True,
            )
            for slug, name, normalized in all_uses
        }
        db.add_all(codes.values())
        db.flush()

        for index in range(120):
            uses = _uses_for_response(index)
            response = Response(
                id=f"{RESPONSE_PREFIX}{index:03d}",
                participant_id=participants[index % len(participants)].id,
                item_id=ITEM_ID,
                raw_input="\n".join(use[2] for use in uses),
                mapping={
                    "ideas": [
                        {
                            "original": normalized,
                            "normalized": f"{normalized} trong tình huống kiểm thử {index + 1}",
                            "code": name,
                            "status": "VALID",
                            "is_valid": True,
                            "reason": "Ý hợp lệ trong corpus kiểm thử.",
                        }
                        for _, name, normalized in uses
                    ]
                },
                mapping_meta={"source": "TEST_SEED_V1"},
                scoring={},
                scoring_meta={},
                scoring_status=ResponseScoringStatus.COLLECTING,
            )
            db.add(response)
            db.flush()
            db.add_all(
                [
                    ResponseIdea(
                        response_id=response.id,
                        code_id=codes[slug].id,
                        original=normalized,
                        normalized=f"{normalized} trong tình huống kiểm thử {index + 1}",
                        mapping_status="VALID",
                        curator_decision="TEST_SEED",
                        confidence=0.99,
                        reason="Ý hợp lệ trong corpus kiểm thử.",
                    )
                    for slug, _, normalized in uses
                ]
            )

        db.flush()
        refresh_item_scoring_state(db, item)
        previous_mock_mode = settings.mock_mode
        settings.mock_mode = True
        try:
            scored = reprocess_item_scores_in_session(db, ITEM_ID)
        finally:
            settings.mock_mode = previous_mock_mode
        db.commit()

        response_count = db.scalar(
            select(func.count()).select_from(Response).where(Response.item_id == ITEM_ID)
        ) or 0
        participant_count = db.scalar(
            select(func.count(func.distinct(Response.participant_id))).where(
                Response.item_id == ITEM_ID
            )
        ) or 0
        score_distribution = db.execute(
            select(Response.originality, func.count(Response.id))
            .where(Response.id.like(f"{RESPONSE_PREFIX}%"))
            .group_by(Response.originality)
            .order_by(Response.originality)
        ).all()
        version_tables = {
            name
            for name in inspect(db.get_bind()).get_table_names()
            if name in {"codebook_versions", "codebook_version_codes"}
        }
        print(
            f"Đã nạp 120 response seed; item '{ITEM_ID}' hiện có "
            f"{response_count} response, {participant_count} người và vừa chấm {scored} lượt."
        )
        print(f"Phân bố Originality của seed: {score_distribution}")
        print(f"Bảng version còn tồn tại: {sorted(version_tables)}")


if __name__ == "__main__":
    main()

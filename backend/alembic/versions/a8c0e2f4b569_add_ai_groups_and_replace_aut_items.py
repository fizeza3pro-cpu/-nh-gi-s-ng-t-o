"""Thêm nhóm sử dụng AI và thay bộ vật thể AUT.

Revision ID: a8c0e2f4b569
Revises: f6b8d0e2a347
Create Date: 2026-09-23

Migration này có chủ đích xoá toàn bộ response và codebook của bộ vật thể cũ.
Hồ sơ người tham gia và tài khoản quản trị được giữ lại.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c0e2f4b569"
down_revision: Union[str, Sequence[str], None] = "f6b8d0e2a347"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clear_survey_data() -> None:
    """Xoá theo thứ tự khoá ngoại, chỉ trong phạm vi dữ liệu khảo sát AUT."""
    statements = (
        "DELETE FROM response_ideas",
        "UPDATE item_codes SET merged_into_id = NULL",
        "DELETE FROM item_codes",
        "DELETE FROM responses",
        "DELETE FROM items",
    )
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("ai_usage_group", sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f("ix_participants_ai_usage_group"),
        "participants",
        ["ai_usage_group"],
        unique=False,
    )
    op.alter_column(
        "items",
        "scoring_min_responses",
        new_column_name="scoring_min_ideas",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    _clear_survey_data()
    op.execute(
        """
        INSERT INTO items (
            id, name, description, calibration_status,
            scoring_min_participants, scoring_min_ideas
        ) VALUES
            ('balo_quan_nhu', 'Balo quân nhu',
             'Trang bị cá nhân dùng hằng ngày, có nhiều khoang và dây đeo.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('bi_dong_nuoc', 'Bi đông nước',
             'Bình đựng nước cá nhân dạng trụ, thường làm bằng kim loại hoặc nhựa cứng.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('xeng_cong_binh', 'Xẻng công binh',
             'Dụng cụ đào nhỏ gọn dùng trong hoạt động công binh và dã ngoại.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('mu_coi', 'Mũ cối',
             'Mũ bảo hộ có dạng vòm, quen thuộc trong môi trường quân đội.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('vo_dan', 'Vỏ đạn',
             'Phần vỏ kim loại rỗng còn lại sau khi viên đạn đã được sử dụng.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('thung_dan', 'Thùng đạn',
             'Thùng hình hộp chắc chắn dùng để chứa và vận chuyển đạn dược.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('ni_long_ao_mua', 'Ni lông (áo mưa)',
             'Tấm vật liệu ni lông mềm, chống nước, thường được dùng làm áo mưa.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('kinh_lup', 'Kính lúp',
             'Thấu kính cầm tay dùng để quan sát vật thể ở kích thước phóng đại.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('ong_nghiem', 'Ống nghiệm',
             'Ống nhỏ hình trụ dùng trong phòng thí nghiệm để chứa mẫu hoặc chất lỏng.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('can_tieu_ly', 'Cân tiểu ly',
             'Dụng cụ cân nhỏ dùng để đo khối lượng với độ chính xác cao.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('ghim_kep_giay', 'Ghim kẹp giấy',
             'Kẹp kim loại nhỏ dùng để giữ các tờ giấy cùng nhau.',
             'COLLECTING'::item_calibration_status, 24, 150),
            ('cuon_chi', 'Cuộn chỉ',
             'Sợi chỉ dài được quấn quanh một lõi nhỏ thành cuộn.',
             'COLLECTING'::item_calibration_status, 24, 150)
        """
    )


def downgrade() -> None:
    """Khôi phục danh mục cũ rỗng; response và codebook đã xoá không thể phục hồi."""
    _clear_survey_data()
    op.execute(
        """
        INSERT INTO items (
            id, name, description, calibration_status,
            scoring_min_participants, scoring_min_ideas
        ) VALUES
            ('chai_nhua', 'Chai nhựa',
             'Chai nhựa đựng nước uống dùng một lần hoặc tái sử dụng',
             'COLLECTING'::item_calibration_status, 30, 100),
            ('day_thung', 'Dây thừng',
             'Đoạn dây thừng dùng để buộc, kéo đồ vật',
             'COLLECTING'::item_calibration_status, 30, 100),
            ('dua', 'Đũa',
             'Dụng cụ dùng để gắp thức ăn khi ăn cơm',
             'COLLECTING'::item_calibration_status, 30, 100),
            ('non_la', 'Nón lá',
             'Nón đội đầu truyền thống làm từ lá, dùng khi đi ngoài trời',
             'COLLECTING'::item_calibration_status, 30, 100),
            ('to_bao', 'Tờ báo cũ',
             'Tờ báo giấy đã đọc xong, không còn dùng để đọc tin tức nữa',
             'COLLECTING'::item_calibration_status, 30, 100)
        """
    )
    op.alter_column(
        "items",
        "scoring_min_ideas",
        new_column_name="scoring_min_responses",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.drop_index(op.f("ix_participants_ai_usage_group"), table_name="participants")
    op.drop_column("participants", "ai_usage_group")

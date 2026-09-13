"""Xoá dữ liệu khảo sát cũ và cấu trúc codebook tĩnh.

Revision ID: a4f7c2e91b36
Revises: c8d4e6f1a902
Create Date: 2026-09-12

Migration này có chủ đích xoá vĩnh viễn response, participant và toàn bộ codebook.
Tài khoản quản trị cùng danh mục đồ vật được giữ lại.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4f7c2e91b36"
down_revision: Union[str, Sequence[str], None] = "c8d4e6f1a902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Đưa hệ thống về trạng thái thu thập sạch và bỏ cấu trúc tĩnh."""
    # Ngắt các liên kết vòng trước khi xoá theo thứ tự khoá ngoại.
    statements = (
        """UPDATE items
           SET active_codebook_version_id = NULL,
               last_version_participant_count = 0,
               calibration_status = 'COLLECTING'::item_calibration_status""",
        "UPDATE responses SET codebook_version_id = NULL",
        "DELETE FROM codebook_version_codes",
        "DELETE FROM response_ideas",
        "UPDATE item_codes SET merged_into_id = NULL",
        "DELETE FROM item_codes",
        "DELETE FROM codebook_versions",
        "DELETE FROM responses",
        "DELETE FROM participants",
    )
    for statement in statements:
        op.execute(statement)

    # Hai bảng tần suất và cột JSON này thuộc thiết kế codebook tĩnh cũ.
    op.drop_table("item_stats")
    op.drop_index(op.f("ix_item_code_counts_item_id"), table_name="item_code_counts")
    op.drop_table("item_code_counts")
    op.drop_column("items", "codes")


def downgrade() -> None:
    """Khôi phục cấu trúc tĩnh rỗng; dữ liệu đã xoá không thể phục hồi."""
    op.add_column(
        "items",
        sa.Column(
            "codes",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.create_table(
        "item_code_counts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "code", name="uq_item_code"),
    )
    op.create_index(
        op.f("ix_item_code_counts_item_id"),
        "item_code_counts",
        ["item_id"],
        unique=False,
    )
    op.create_table(
        "item_stats",
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("total_valid_responses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("norm_version", sa.String(length=255), server_default="unseeded", nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )

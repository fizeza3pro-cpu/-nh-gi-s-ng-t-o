"""Thêm hàng đợi phân xử thủ công cho từng ý chưa có mã.

Revision ID: d4f8b1c2e365
Revises: c3e7a9d0b142
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f8b1c2e365"
down_revision: Union[str, Sequence[str], None] = "c3e7a9d0b142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "response_ideas",
        sa.Column("review_status", sa.String(16), server_default="NOT_REQUIRED", nullable=False),
    )
    op.add_column(
        "response_ideas",
        sa.Column("review_payload", sa.JSON(), server_default="{}", nullable=False),
    )
    op.add_column(
        "response_ideas",
        sa.Column("review_resolution", sa.String(32), server_default="", nullable=False),
    )
    op.add_column(
        "response_ideas",
        sa.Column("review_note", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "response_ideas", sa.Column("reviewed_by", sa.String(36), nullable=True)
    )
    op.add_column(
        "response_ideas",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_response_ideas_review_status", "response_ideas", ["review_status"]
    )
    op.create_foreign_key(
        "fk_response_ideas_reviewed_by_users",
        "response_ideas",
        "users",
        ["reviewed_by"],
        ["id"],
    )
    # Dữ liệu cũ đang VALID nhưng chưa có code chính là các ca phải phân xử.
    op.execute(
        "UPDATE response_ideas SET review_status = 'PENDING' "
        "WHERE mapping_status = 'VALID' AND code_id IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_response_ideas_reviewed_by_users", "response_ideas", type_="foreignkey"
    )
    op.drop_index("ix_response_ideas_review_status", table_name="response_ideas")
    for column in (
        "reviewed_at",
        "reviewed_by",
        "review_note",
        "review_resolution",
        "review_payload",
        "review_status",
    ):
        op.drop_column("response_ideas", column)

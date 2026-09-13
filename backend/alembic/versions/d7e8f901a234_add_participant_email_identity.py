"""Thêm định danh email chưa OTP cho participant.

Revision ID: d7e8f901a234
Revises: b91d6e4f30ac
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f901a234"
down_revision: Union[str, Sequence[str], None] = "b91d6e4f30ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable để giữ nguyên participant cũ; họ sẽ gắn email ở lần quay lại tiếp theo.
    op.add_column(
        "participants", sa.Column("email_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "participants", sa.Column("email_masked", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "participants", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_participants_email_hash"),
        "participants",
        ["email_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_participants_email_hash"), table_name="participants")
    op.drop_column("participants", "email_verified_at")
    op.drop_column("participants", "email_masked")
    op.drop_column("participants", "email_hash")

"""Thêm metadata embedding và lịch sử phạm vi code tự động.

Revision ID: b9d1f3a5c680
Revises: a8c0e2f4b569
Create Date: 2026-09-25

Migration chỉ thêm metadata, không sửa hoặc xoá response/code hiện có.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9d1f3a5c680"
down_revision: Union[str, Sequence[str], None] = "a8c0e2f4b569"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_codes",
        sa.Column("embedding_model", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "item_codes",
        sa.Column("scope_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("item_codes", "scope_history")
    op.drop_column("item_codes", "embedding_model")

"""Thêm họ và tên cho người tham gia khảo sát.

Revision ID: a7c9e1f3b246
Revises: f4a6c8e0b125
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c9e1f3b246"
down_revision: Union[str, Sequence[str], None] = "f4a6c8e0b125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable để không làm mất hoặc bịa tên cho các participant đã tồn tại.
    # Họ sẽ được yêu cầu bổ sung tên ở lần nhận diện tiếp theo.
    op.add_column(
        "participants", sa.Column("full_name", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("participants", "full_name")

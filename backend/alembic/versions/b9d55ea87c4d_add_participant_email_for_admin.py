"""Lưu email đầy đủ để hiển thị cho quản trị viên.

Revision ID: b9d55ea87c4d
Revises: e7c9a1b3d568
Create Date: 2026-10-01 22:57:16.524971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Định danh phiên bản dùng bởi Alembic.
revision: str = "b9d55ea87c4d"
down_revision: Union[str, Sequence[str], None] = "e7c9a1b3d568"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Thêm cột nullable, giữ nguyên email đã che của mọi hồ sơ cũ."""
    op.add_column("participants", sa.Column("email", sa.String(length=320), nullable=True))


def downgrade() -> None:
    """Bỏ email đầy đủ; các cột định danh và email đã che vẫn được giữ."""
    op.drop_column("participants", "email")

"""Xoá tài khoản người dùng thường của hệ thống đăng nhập cũ.

Revision ID: b91d6e4f30ac
Revises: a4f7c2e91b36
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b91d6e4f30ac"
down_revision: Union[str, Sequence[str], None] = "a4f7c2e91b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Chỉ giữ tài khoản ADMIN; participant không dùng bảng users."""
    op.execute("DELETE FROM users WHERE role <> 'ADMIN'::user_role")


def downgrade() -> None:
    """Không thể khôi phục thông tin đăng nhập đã xoá."""
    pass

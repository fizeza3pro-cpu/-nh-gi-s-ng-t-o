"""Lưu lựa chọn ẩn/hiện đồ vật trên trang chọn khảo sát."""

from alembic import op
import sqlalchemy as sa

revision = "c4a6b8d0e125"
down_revision = "c2f4a6b8d013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mặc định giữ nguyên danh sách đang hiển thị; không sửa dữ liệu khảo sát.
    op.add_column("items", sa.Column("survey_visible", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("items", "survey_visible")

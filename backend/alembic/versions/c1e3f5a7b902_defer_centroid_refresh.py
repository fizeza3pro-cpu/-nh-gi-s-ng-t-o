"""Đánh dấu centroid cần cập nhật để worker dựng lại ngoài luồng lưu bài."""
from alembic import op
import sqlalchemy as sa

revision = "c1e3f5a7b902"
down_revision = "c0d2e4f6a891"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_codes", sa.Column("centroid_dirty", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("item_codes", "centroid_dirty")

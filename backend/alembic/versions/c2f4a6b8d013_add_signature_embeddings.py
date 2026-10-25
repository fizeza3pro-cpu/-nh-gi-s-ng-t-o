"""Cache ba vector chữ ký của mã, tách khỏi vector câu gốc và centroid."""
from alembic import op
import sqlalchemy as sa

revision = "c2f4a6b8d013"
down_revision = "c1e3f5a7b902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_codes", sa.Column("signature_embeddings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    # Worker kiểm tra phiên bản trước khi dựng lại; không đổi mapping hoặc điểm FINAL.
    op.execute(sa.text("UPDATE item_codes SET centroid_dirty = true"))


def downgrade() -> None:
    op.drop_column("item_codes", "signature_embeddings")

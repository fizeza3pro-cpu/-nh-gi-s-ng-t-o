"""Thêm trạng thái xử lý bền vững, epoch và bằng chứng centroid.

Revision ID: c3e7a9d0b142
Revises: b9d1f3a5c680
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3e7a9d0b142"
down_revision: Union[str, Sequence[str], None] = "b9d1f3a5c680"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("codebook_epoch", sa.Integer(), server_default="0", nullable=False))

    op.add_column("responses", sa.Column("request_id", sa.String(36), nullable=True))
    op.add_column("responses", sa.Column("processing_state", sa.String(16), server_default="DONE", nullable=False))
    op.add_column("responses", sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("responses", sa.Column("processing_claim_token", sa.String(36), nullable=True))
    op.add_column("responses", sa.Column("processing_lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("responses", sa.Column("processing_error", sa.Text(), server_default="", nullable=False))
    op.create_index("ix_responses_processing_state", "responses", ["processing_state"])
    op.create_unique_constraint("uq_response_participant_request", "responses", ["participant_id", "request_id"])

    op.add_column("item_codes", sa.Column("centroid", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("item_codes", sa.Column("centroid_sum", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("item_codes", sa.Column("prototype_vectors", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("item_codes", sa.Column("centroid_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("item_codes", sa.Column("centroid_model", sa.String(255), server_default="", nullable=False))
    op.add_column("item_codes", sa.Column("centroid_revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("item_codes", sa.Column("scope_revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("item_codes", sa.Column("drift_flag", sa.Boolean(), server_default=sa.false(), nullable=False))

    op.add_column("response_ideas", sa.Column("embedding", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("response_ideas", sa.Column("embedding_model", sa.String(255), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("response_ideas", "embedding_model")
    op.drop_column("response_ideas", "embedding")
    for name in ("drift_flag", "scope_revision", "centroid_revision", "centroid_model", "centroid_count", "prototype_vectors", "centroid_sum", "centroid"):
        op.drop_column("item_codes", name)
    op.drop_constraint("uq_response_participant_request", "responses", type_="unique")
    op.drop_index("ix_responses_processing_state", table_name="responses")
    for name in ("processing_error", "processing_lease_until", "processing_claim_token", "processing_attempts", "processing_state", "request_id"):
        op.drop_column("responses", name)
    op.drop_column("items", "codebook_epoch")

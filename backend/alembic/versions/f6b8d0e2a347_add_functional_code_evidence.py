"""Thêm chữ ký chức năng và căn cứ phân xử cho sổ mã động.

Revision ID: f6b8d0e2a347
Revises: e1a3c5d7f680
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6b8d0e2a347"
down_revision: Union[str, Sequence[str], None] = "e1a3c5d7f680"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_codes",
        sa.Column("functional_key", sa.String(length=512), server_default="", nullable=False),
    )
    op.create_index("ix_item_codes_functional_key", "item_codes", ["functional_key"])
    for column in ("functional_signature",):
        op.add_column(
            "item_codes",
            sa.Column(column, sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        )
    for column in ("inclusion_rules", "exclusion_rules", "positive_examples", "embedding"):
        op.add_column(
            "item_codes",
            sa.Column(column, sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        )

    op.add_column(
        "response_ideas",
        sa.Column("line_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "response_ideas",
        sa.Column(
            "functional_signature", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False
        ),
    )
    op.add_column(
        "response_ideas",
        sa.Column("mapping_evidence", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("response_ideas", "mapping_evidence")
    op.drop_column("response_ideas", "functional_signature")
    op.drop_column("response_ideas", "line_index")
    for column in ("embedding", "positive_examples", "exclusion_rules", "inclusion_rules", "functional_signature"):
        op.drop_column("item_codes", column)
    op.drop_index("ix_item_codes_functional_key", table_name="item_codes")
    op.drop_column("item_codes", "functional_key")

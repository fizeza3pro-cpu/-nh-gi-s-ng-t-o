"""Xoá codebook version khỏi mô hình chấm điểm realtime.

Revision ID: c9e1a3b5d468
Revises: b8d0f2a4c357
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c9e1a3b5d468"
down_revision: Union[str, Sequence[str], None] = "b8d0f2a4c357"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Điểm đã tự lưu căn cứ realtime trong scoring_meta nên không còn phụ thuộc version.
    op.drop_constraint(
        "responses_codebook_version_id_fkey", "responses", type_="foreignkey"
    )
    op.drop_index("ix_responses_codebook_version_id", table_name="responses")
    op.drop_column("responses", "codebook_version_id")

    op.drop_column("items", "active_codebook_version_id")
    op.drop_column("items", "last_version_participant_count")

    op.drop_table("codebook_version_codes")
    op.drop_table("codebook_versions")
    postgresql.ENUM(name="codebook_version_status").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    version_status = postgresql.ENUM(
        "ACTIVE", "RETIRED", name="codebook_version_status", create_type=False
    )
    version_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "codebook_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", version_status, nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "version", name="uq_codebook_item_version"),
    )
    op.create_index(
        "ix_codebook_versions_item_id", "codebook_versions", ["item_id"]
    )
    op.create_table(
        "codebook_version_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("code_id", sa.String(length=36), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("idea_count", sa.Integer(), nullable=False),
        sa.Column("frequency", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["code_id"], ["item_codes.id"]),
        sa.ForeignKeyConstraint(
            ["version_id"], ["codebook_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "code_id", name="uq_version_code"),
    )
    op.create_index(
        "ix_codebook_version_codes_version_id",
        "codebook_version_codes",
        ["version_id"],
    )

    op.add_column(
        "items",
        sa.Column(
            "last_version_participant_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "items", sa.Column("active_codebook_version_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "responses", sa.Column("codebook_version_id", sa.String(length=36), nullable=True)
    )
    op.create_index(
        "ix_responses_codebook_version_id", "responses", ["codebook_version_id"]
    )
    op.create_foreign_key(
        "responses_codebook_version_id_fkey",
        "responses",
        "codebook_versions",
        ["codebook_version_id"],
        ["id"],
    )

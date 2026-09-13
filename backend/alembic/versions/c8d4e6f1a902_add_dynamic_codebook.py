"""Thêm codebook động, snapshot và trạng thái chấm.

Revision ID: c8d4e6f1a902
Revises: f3a1c7d9e245
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8d4e6f1a902"
down_revision: Union[str, Sequence[str], None] = "f3a1c7d9e245"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


item_calibration_status = postgresql.ENUM(
    "COLLECTING", "CALIBRATING", "ACTIVE", "RECALIBRATING", "PAUSED",
    name="item_calibration_status",
    create_type=False,
)
code_validation_status = postgresql.ENUM(
    "ACCEPTED", "UNCERTAIN", "REJECTED", name="code_validation_status", create_type=False
)
code_maturity_status = postgresql.ENUM(
    "EMERGING", "STABLE", "MERGED", "ARCHIVED", name="code_maturity_status", create_type=False
)
response_scoring_status = postgresql.ENUM(
    "COLLECTING", "PENDING_REVIEW", "PROVISIONAL", "FINAL", "EXCLUDED",
    name="response_scoring_status",
    create_type=False,
)
codebook_version_status = postgresql.ENUM(
    "ACTIVE", "RETIRED", name="codebook_version_status", create_type=False
)


def upgrade() -> None:
    """Chỉ thêm cấu trúc; giữ nguyên JSON, điểm và bảng thống kê cũ."""
    bind = op.get_bind()
    for enum_type in (
        item_calibration_status,
        code_validation_status,
        code_maturity_status,
        response_scoring_status,
        codebook_version_status,
    ):
        enum_type.create(bind, checkfirst=True)

    op.add_column(
        "items",
        sa.Column(
            "calibration_status",
            item_calibration_status,
            server_default="COLLECTING",
            nullable=False,
        ),
    )
    op.add_column(
        "items",
        sa.Column("calibration_min_participants", sa.Integer(), server_default="30", nullable=False),
    )
    op.add_column(
        "items",
        sa.Column("originality_min_participants", sa.Integer(), server_default="100", nullable=False),
    )
    op.add_column(
        "items",
        sa.Column("last_version_participant_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("items", sa.Column("active_codebook_version_id", sa.String(36), nullable=True))

    op.create_table(
        "item_codes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("validation_status", code_validation_status, nullable=False),
        sa.Column("maturity_status", code_maturity_status, nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("relevance_reason", sa.Text(), server_default="", nullable=False),
        sa.Column("rejection_reason", sa.Text(), server_default="", nullable=False),
        sa.Column("source_response_id", sa.String(36), nullable=True),
        sa.Column("merged_into_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(32), server_default="LLM", nullable=False),
        sa.Column("admin_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["source_response_id"], ["responses.id"]),
        sa.ForeignKeyConstraint(["merged_into_id"], ["item_codes.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "normalized_name", name="uq_item_code_normalized_name"),
    )
    op.create_index(op.f("ix_item_codes_item_id"), "item_codes", ["item_id"])
    op.create_index(op.f("ix_item_codes_validation_status"), "item_codes", ["validation_status"])
    op.create_index(op.f("ix_item_codes_maturity_status"), "item_codes", ["maturity_status"])

    # Danh sách tĩnh chỉ được lưu làm dấu vết legacy, không tham gia codebook động.
    op.execute(
        """
        INSERT INTO item_codes (
            id, item_id, name, normalized_name, description,
            validation_status, maturity_status, confidence, relevance_reason,
            rejection_reason, created_by, admin_locked, created_at, updated_at
        )
        SELECT
            (md5(i.id || '|legacy|' || code_name)::uuid)::text,
            i.id,
            code_name,
            lower(trim(code_name)),
            'Code tĩnh trước khi chuyển sang codebook động.',
            'ACCEPTED'::code_validation_status,
            'ARCHIVED'::code_maturity_status,
            1,
            'Dữ liệu legacy — chỉ giữ để truy vết.',
            '',
            'LEGACY',
            true,
            now(),
            now()
        FROM items i
        CROSS JOIN LATERAL json_array_elements_text(COALESCE(i.codes, '[]'::json)) AS code_name
        ON CONFLICT (item_id, normalized_name) DO NOTHING
        """
    )

    op.create_table(
        "codebook_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", codebook_version_status, nullable=False),
        sa.Column("participant_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "version", name="uq_codebook_item_version"),
    )
    op.create_index(op.f("ix_codebook_versions_item_id"), "codebook_versions", ["item_id"])

    op.create_table(
        "response_ideas",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("response_id", sa.String(36), nullable=False),
        sa.Column("code_id", sa.String(36), nullable=True),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.Column("mapping_status", sa.String(16), nullable=False),
        sa.Column("curator_decision", sa.String(32), server_default="", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["response_id"], ["responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_id"], ["item_codes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_response_ideas_response_id"), "response_ideas", ["response_id"])

    op.create_table(
        "codebook_version_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("code_id", sa.String(36), nullable=False),
        sa.Column("response_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("participant_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("idea_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("frequency", sa.Float(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["codebook_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_id"], ["item_codes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "code_id", name="uq_version_code"),
    )
    op.create_index(
        op.f("ix_codebook_version_codes_version_id"),
        "codebook_version_codes",
        ["version_id"],
    )

    op.add_column(
        "responses",
        sa.Column(
            "scoring_status",
            response_scoring_status,
            server_default="FINAL",
            nullable=False,
        ),
    )
    op.add_column("responses", sa.Column("codebook_version_id", sa.String(36), nullable=True))
    op.add_column(
        "responses",
        sa.Column("calibration_eligible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("responses", sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_responses_scoring_status"), "responses", ["scoring_status"])
    op.create_index(op.f("ix_responses_codebook_version_id"), "responses", ["codebook_version_id"])
    op.create_foreign_key(
        "responses_codebook_version_id_fkey",
        "responses",
        "codebook_versions",
        ["codebook_version_id"],
        ["id"],
    )

    # Mặc định ORM cho response mới là COLLECTING; dữ liệu đang có vẫn là FINAL/không hiệu chuẩn.
    op.alter_column("responses", "scoring_status", server_default="COLLECTING")
    op.alter_column("responses", "calibration_eligible", server_default=sa.true())


def downgrade() -> None:
    """Gỡ phần động; không đụng tới JSON/điểm legacy."""
    op.drop_constraint("responses_codebook_version_id_fkey", "responses", type_="foreignkey")
    op.drop_index(op.f("ix_responses_codebook_version_id"), table_name="responses")
    op.drop_index(op.f("ix_responses_scoring_status"), table_name="responses")
    op.drop_column("responses", "scored_at")
    op.drop_column("responses", "calibration_eligible")
    op.drop_column("responses", "codebook_version_id")
    op.drop_column("responses", "scoring_status")
    op.drop_index(op.f("ix_codebook_version_codes_version_id"), table_name="codebook_version_codes")
    op.drop_table("codebook_version_codes")
    op.drop_index(op.f("ix_response_ideas_response_id"), table_name="response_ideas")
    op.drop_table("response_ideas")
    op.drop_index(op.f("ix_codebook_versions_item_id"), table_name="codebook_versions")
    op.drop_table("codebook_versions")
    op.drop_index(op.f("ix_item_codes_maturity_status"), table_name="item_codes")
    op.drop_index(op.f("ix_item_codes_validation_status"), table_name="item_codes")
    op.drop_index(op.f("ix_item_codes_item_id"), table_name="item_codes")
    op.drop_table("item_codes")
    op.drop_column("items", "active_codebook_version_id")
    op.drop_column("items", "last_version_participant_count")
    op.drop_column("items", "originality_min_participants")
    op.drop_column("items", "calibration_min_participants")
    op.drop_column("items", "calibration_status")

    bind = op.get_bind()
    for enum_type in (
        codebook_version_status,
        response_scoring_status,
        code_maturity_status,
        code_validation_status,
        item_calibration_status,
    ):
        enum_type.drop(bind, checkfirst=True)

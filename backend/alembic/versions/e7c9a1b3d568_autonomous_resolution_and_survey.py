"""Bổ sung phục hồi tự động và phiên khảo sát, giữ codebook live.

Revision ID: e7c9a1b3d568
Revises: d4f8b1c2e365
"""
from alembic import op
import sqlalchemy as sa

revision = "e7c9a1b3d568"
down_revision = "d4f8b1c2e365"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("participants", sa.Column("access_token_hash", sa.String(64), nullable=True))
    op.add_column("items", sa.Column("scores_dirty", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column in [
        sa.Column("input_lines", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("mapping_checkpoint", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("mapping_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolution_next_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_epoch", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("protocol", sa.String(64), nullable=False, server_default="LEGACY"),
        sa.Column("data_source", sa.String(16), nullable=False, server_default="PILOT"),
        sa.Column("survey_session_id", sa.String(36), nullable=True),
    ]:
        op.add_column("responses", column)
    op.create_unique_constraint("uq_response_survey_session", "responses", ["survey_session_id"])
    op.add_column("response_ideas", sa.Column("duplicate_of_index", sa.Integer(), nullable=True))
    op.add_column("response_ideas", sa.Column("coding_state", sa.String(16), nullable=False, server_default="ASSIGNED"))
    op.execute("UPDATE response_ideas SET coding_state = CASE WHEN mapping_status != 'VALID' THEN 'NOT_APPLICABLE' WHEN code_id IS NULL THEN 'RESOLVING' ELSE 'ASSIGNED' END")
    op.execute("UPDATE responses SET mapping_completed_at = created_at WHERE processing_state = 'DONE' AND scoring_status NOT IN ('PENDING_REVIEW', 'EXCLUDED')")
    op.create_table("survey_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("participant_id", sa.String(36), sa.ForeignKey("participants.id"), nullable=False),
        sa.Column("item_id", sa.String(64), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_survey_sessions_participant_id", "survey_sessions", ["participant_id"])
    op.create_index("ix_survey_sessions_item_id", "survey_sessions", ["item_id"])
    op.create_table("pipeline_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(64), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("response_id", sa.String(36), sa.ForeignKey("responses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pipeline_audits_item_id", "pipeline_audits", ["item_id"])


def downgrade():
    op.drop_table("pipeline_audits")
    op.drop_table("survey_sessions")
    op.drop_column("response_ideas", "coding_state")
    op.drop_column("response_ideas", "duplicate_of_index")
    op.drop_constraint("uq_response_survey_session", "responses", type_="unique")
    for name in ["input_lines", "mapping_checkpoint", "mapping_completed_at", "resolution_attempts", "resolution_next_at", "resolution_epoch", "protocol", "data_source", "survey_session_id"]:
        op.drop_column("responses", name)
    op.drop_column("items", "scores_dirty")
    op.drop_column("participants", "access_token_hash")

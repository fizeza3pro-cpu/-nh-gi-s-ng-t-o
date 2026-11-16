"""Thêm bộ quản lý model BytePlus; không sửa bảng hoặc dữ liệu khảo sát."""
from alembic import op
import sqlalchemy as sa

revision = "c5b7d9e1f236"
down_revision = "c4a6b8d0e125"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("model_pool_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_switch", sa.Boolean(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("active_slot", sa.Integer()),
        sa.Column("blocked_reason", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.execute(sa.text("INSERT INTO model_pool_settings (id, enabled, auto_switch, threshold, revision, blocked_reason, updated_at) VALUES (1, false, true, 10000, 0, '', CURRENT_TIMESTAMP)"))
    op.create_table("model_quotas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("quota_key", sa.String(160), unique=True, nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("confirmed_remaining", sa.Integer()),
        sa.Column("spent_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("exhausted", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)))
    op.create_table("managed_models",
        sa.Column("slot", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("model_id", sa.String(255), unique=True),
        sa.Column("quota_id", sa.String(36), sa.ForeignKey("model_quotas.id")),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("thinking_mode", sa.String(16), nullable=False),
        sa.Column("blocked_reason", sa.String(64), nullable=False),
        sa.CheckConstraint("slot >= 1 AND slot <= 5", name="ck_managed_model_slot"))
    op.create_table("model_token_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("quota_id", sa.String(36), sa.ForeignKey("model_quotas.id"), nullable=False),
        sa.Column("model_slot", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("call_id", sa.String(36), nullable=False),
        sa.Column("parent_id", sa.String(36)),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("response_id", sa.String(36)),
        sa.Column("provider_request_id", sa.String(255)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("quota_id", "call_id", "response_id", "status"):
        op.create_index(f"ix_model_token_requests_{column}", "model_token_requests", [column])
    op.create_index("ix_model_token_requests_provider_request", "model_token_requests", ["quota_id", "provider_request_id"])
    op.create_table("model_pool_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.String(36)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ("model_pool_events", "model_token_requests", "managed_models", "model_quotas", "model_pool_settings"):
        op.drop_table(table)

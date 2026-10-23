"""Đổi tên cờ ngưỡng mẫu và thêm index cho worker, không sửa điểm hay dữ liệu khảo sát."""
from alembic import op
import sqlalchemy as sa

revision = "c0d2e4f6a891"
down_revision = "b9d55ea87c4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # RENAME giữ nguyên toàn bộ giá trị; không dùng add/drop gây mất cờ đang chờ.
    op.alter_column("items", "scores_dirty", new_column_name="calibration_dirty", existing_type=sa.Boolean())
    op.create_index("ix_responses_worker_queue", "responses", ["scoring_status", "processing_state", "created_at"])
    op.create_index("ix_response_ideas_code_status", "response_ideas", ["code_id", "mapping_status"])
    op.create_index("ix_survey_sessions_participant_item_started", "survey_sessions", ["participant_id", "item_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_survey_sessions_participant_item_started", table_name="survey_sessions")
    op.drop_index("ix_response_ideas_code_status", table_name="response_ideas")
    op.drop_index("ix_responses_worker_queue", table_name="responses")
    op.alter_column("items", "calibration_dirty", new_column_name="scores_dirty", existing_type=sa.Boolean())

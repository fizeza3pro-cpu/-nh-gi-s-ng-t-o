"""Chuyển sang chấm một lần bằng dữ liệu realtime.

Revision ID: b8d0f2a4c357
Revises: a7c9e1f3b246
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d0f2a4c357"
down_revision: Union[str, Sequence[str], None] = "a7c9e1f3b246"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hai ngưỡng nay mô tả đúng hai đại lượng độc lập: số người và số response.
    op.alter_column(
        "items", "calibration_min_participants", new_column_name="scoring_min_participants"
    )
    op.alter_column(
        "items", "originality_min_participants", new_column_name="scoring_min_responses"
    )

    # Điểm tạm cũ trở thành điểm đã chốt; từ đây hệ thống không tự cập nhật điểm nữa.
    op.execute(
        "UPDATE responses SET scoring_status = 'FINAL' "
        "WHERE scoring_status = 'PROVISIONAL'"
    )
    op.drop_column("responses", "calibration_eligible")


def downgrade() -> None:
    op.add_column(
        "responses",
        sa.Column("calibration_eligible", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.alter_column(
        "items", "scoring_min_responses", new_column_name="originality_min_participants"
    )
    op.alter_column(
        "items", "scoring_min_participants", new_column_name="calibration_min_participants"
    )

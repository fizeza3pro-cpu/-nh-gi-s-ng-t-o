"""Đưa mọi lượt submit hợp lệ vào mẫu chuẩn.

Revision ID: e2c4b6d8f013
Revises: d7e8f901a234
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e2c4b6d8f013"
down_revision: Union[str, Sequence[str], None] = "d7e8f901a234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # EXCLUDED là dữ liệu đã bị admin vô hiệu hoá (ví dụ sau khi xoá codebook), nên không tự đưa lại.
    op.execute(
        """
        UPDATE responses
        SET calibration_eligible = TRUE
        WHERE scoring_status <> 'EXCLUDED'
        """
    )


def downgrade() -> None:
    # Khôi phục chính sách cũ: chỉ lượt sớm nhất của mỗi participant trên từng đồ vật là mẫu chuẩn.
    op.execute("UPDATE responses SET calibration_eligible = FALSE")
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY participant_id, item_id
                    ORDER BY created_at, id
                ) AS position
            FROM responses
            WHERE scoring_status <> 'EXCLUDED'
        )
        UPDATE responses AS response
        SET calibration_eligible = TRUE
        FROM ranked
        WHERE response.id = ranked.id
          AND ranked.position = 1
        """
    )

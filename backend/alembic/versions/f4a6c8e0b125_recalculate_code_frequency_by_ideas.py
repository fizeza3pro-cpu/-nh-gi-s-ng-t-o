"""Tính lại tần suất mã theo số ý hợp lệ.

Revision ID: f4a6c8e0b125
Revises: e2c4b6d8f013
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f4a6c8e0b125"
down_revision: Union[str, Sequence[str], None] = "e2c4b6d8f013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Đổi các snapshot cũ từ tỷ lệ theo lượt sang tỷ lệ theo từng ý."""
    op.execute(
        """
        WITH totals AS (
            SELECT version_id, SUM(idea_count) AS total_ideas
            FROM codebook_version_codes
            GROUP BY version_id
        )
        UPDATE codebook_version_codes AS entry
        SET frequency = CASE
            WHEN totals.total_ideas > 0
                THEN entry.idea_count::double precision / totals.total_ideas
            ELSE 0
        END
        FROM totals
        WHERE entry.version_id = totals.version_id
        """
    )


def downgrade() -> None:
    """Khôi phục công thức cũ theo tỷ lệ lượt của từng phiên bản."""
    op.execute(
        """
        UPDATE codebook_version_codes AS entry
        SET frequency = CASE
            WHEN version.response_count > 0
                THEN entry.response_count::double precision / version.response_count
            ELSE 0
        END
        FROM codebook_versions AS version
        WHERE entry.version_id = version.id
        """
    )

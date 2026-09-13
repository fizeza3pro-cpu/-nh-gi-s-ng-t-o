"""Thêm participant ẩn danh và chuyển response khỏi user.

Revision ID: f3a1c7d9e245
Revises: e0ca853fc1d6
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a1c7d9e245"
down_revision: Union[str, Sequence[str], None] = "e0ca853fc1d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Tạo participant, giữ dữ liệu response cũ rồi đổi khóa ngoại."""
    op.create_table(
        "participants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("occupation", sa.String(length=255), nullable=True),
        sa.Column("device_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_participants_device_hash"),
        "participants",
        ["device_hash"],
        unique=False,
    )

    # Giữ nguyên nhóm bài cũ của mỗi user bằng cách dùng lại UUID làm participant UUID.
    op.execute(
        """
        INSERT INTO participants (id, created_at)
        SELECT user_id, MIN(created_at)
        FROM responses
        WHERE user_id IS NOT NULL
        GROUP BY user_id
        """
    )
    # Bài cũ không có user được coi là một participant legacy độc lập. UUID
    # được dẫn xuất thay vì dùng response_id để không làm lộ participant_id.
    op.execute(
        """
        INSERT INTO participants (id, created_at)
        SELECT (md5(id || '-legacy-participant')::uuid)::text, created_at
        FROM responses
        WHERE user_id IS NULL
        """
    )

    # Tháo ràng buộc với users trước khi gán UUID legacy mới. Nếu cập nhật
    # trước bước này, PostgreSQL sẽ từ chối vì UUID mới không có trong users.
    op.drop_constraint("responses_user_id_fkey", "responses", type_="foreignkey")
    op.drop_index(op.f("ix_responses_user_id"), table_name="responses")
    op.execute(
        """
        UPDATE responses
        SET user_id = (md5(id || '-legacy-participant')::uuid)::text
        WHERE user_id IS NULL
        """
    )
    op.alter_column(
        "responses",
        "user_id",
        new_column_name="participant_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_index(
        op.f("ix_responses_participant_id"),
        "responses",
        ["participant_id"],
        unique=False,
    )
    op.create_foreign_key(
        "responses_participant_id_fkey",
        "responses",
        "participants",
        ["participant_id"],
        ["id"],
    )


def downgrade() -> None:
    """Đưa response về user_id; response không khớp user sẽ trở thành NULL."""
    op.drop_constraint("responses_participant_id_fkey", "responses", type_="foreignkey")
    op.drop_index(op.f("ix_responses_participant_id"), table_name="responses")
    op.alter_column(
        "responses",
        "participant_id",
        new_column_name="user_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.execute(
        """
        UPDATE responses
        SET user_id = NULL
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE users.id = responses.user_id)
        """
    )
    op.create_index(
        op.f("ix_responses_user_id"), "responses", ["user_id"], unique=False
    )
    op.create_foreign_key(
        "responses_user_id_fkey",
        "responses",
        "users",
        ["user_id"],
        ["id"],
    )
    op.drop_index(op.f("ix_participants_device_hash"), table_name="participants")
    op.drop_table("participants")

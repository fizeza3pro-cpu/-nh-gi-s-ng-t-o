"""Bỏ trạng thái lưu trữ của mã.

Revision ID: e1a3c5d7f680
Revises: d0f2b4c6e579
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e1a3c5d7f680"
down_revision: Union[str, Sequence[str], None] = "d0f2b4c6e579"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mã từng được lưu trữ chuyển thành mã bị loại để không tự hoạt động trở lại.
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE VARCHAR(32) USING maturity_status::text"
    )
    op.execute(
        "UPDATE item_codes SET "
        "validation_status = 'REJECTED', "
        "maturity_status = 'ACTIVE', "
        "rejection_reason = CASE "
        "WHEN rejection_reason IS NULL OR rejection_reason = '' "
        "THEN 'Mã được chuyển từ trạng thái lưu trữ sang đã loại.' "
        "ELSE rejection_reason END "
        "WHERE maturity_status = 'ARCHIVED'"
    )
    op.execute("DROP TYPE code_maturity_status")
    op.execute("CREATE TYPE code_maturity_status AS ENUM ('ACTIVE', 'MERGED')")
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE code_maturity_status USING maturity_status::code_maturity_status"
    )


def downgrade() -> None:
    # Không thể suy ra mã nào từng được lưu trữ; chỉ khôi phục kiểu enum cũ.
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE VARCHAR(32) USING maturity_status::text"
    )
    op.execute("DROP TYPE code_maturity_status")
    op.execute("CREATE TYPE code_maturity_status AS ENUM ('ACTIVE', 'MERGED', 'ARCHIVED')")
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE code_maturity_status USING maturity_status::code_maturity_status"
    )

"""Hợp nhất mã đang hình thành và ổn định thành mã đang hoạt động.

Revision ID: d0f2b4c6e579
Revises: c9e1a3b5d468
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d0f2b4c6e579"
down_revision: Union[str, Sequence[str], None] = "c9e1a3b5d468"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE VARCHAR(32) USING maturity_status::text"
    )
    op.execute(
        "UPDATE item_codes SET maturity_status = 'ACTIVE' "
        "WHERE maturity_status IN ('EMERGING', 'STABLE')"
    )
    op.execute("DROP TYPE code_maturity_status")
    op.execute("CREATE TYPE code_maturity_status AS ENUM ('ACTIVE', 'MERGED', 'ARCHIVED')")
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE code_maturity_status USING maturity_status::code_maturity_status"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE VARCHAR(32) USING maturity_status::text"
    )
    op.execute("UPDATE item_codes SET maturity_status = 'EMERGING' WHERE maturity_status = 'ACTIVE'")
    op.execute("DROP TYPE code_maturity_status")
    op.execute(
        "CREATE TYPE code_maturity_status AS ENUM "
        "('EMERGING', 'STABLE', 'MERGED', 'ARCHIVED')"
    )
    op.execute(
        "ALTER TABLE item_codes ALTER COLUMN maturity_status "
        "TYPE code_maturity_status USING maturity_status::code_maturity_status"
    )

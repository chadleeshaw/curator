"""Add is_admin column to credentials table.

The first user registered (id=1) is promoted to admin so that existing
single-user installations retain full access after the upgrade.
All subsequently created users default to non-admin.

Revision ID: 003
Revises: 002
Create Date: 2026-02-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"))

    # Promote the original single user (id=1) to admin so that existing
    # installations retain administrative access after the migration.
    op.execute("UPDATE credentials SET is_admin = 1 WHERE id = 1")  # noqa: S608


def downgrade() -> None:
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.drop_column("is_admin")

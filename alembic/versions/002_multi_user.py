"""Add multi-user support: user_id foreign key on all user-scoped tables.

This migration adds a non-nullable user_id column (defaulting to 1 for all
existing rows) to every table whose data is user-specific. A unique index on
the credentials.id column already provides the user anchor.

Existing single-user installations are fully forward-compatible: all rows
get user_id = 1 and the application continues to behave identically unless
the auth layer is extended to issue tokens for additional users.

Revision ID: 002
Revises: 001
Create Date: 2026-02-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that need a user_id column.  For each we add the column and backfill
# existing rows to user_id = 1.
_USER_SCOPED_TABLES = [
    "periodicals",
    "periodical_tracking",
    "discovered_issues",
    "download_submissions",
    "stacks",
    "reading_progress",
]


def upgrade() -> None:
    for table in _USER_SCOPED_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "user_id",
                    sa.Integer(),
                    nullable=True,  # nullable during migration; set NOT NULL below
                )
            )
            batch_op.create_foreign_key(
                f"fk_{table}_user_id",
                "credentials",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )

        # Backfill: assign all existing rows to user 1 (the original single user).
        op.execute(f"UPDATE {table} SET user_id = 1")  # noqa: S608

        with op.batch_alter_table(table) as batch_op:
            batch_op.create_index(f"ix_{table}_user_id", ["user_id"])

        # Enforce NOT NULL now that every row has a value.
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("user_id", nullable=False)


def downgrade() -> None:
    for table in reversed(_USER_SCOPED_TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f"ix_{table}_user_id")
            batch_op.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
            batch_op.drop_column("user_id")

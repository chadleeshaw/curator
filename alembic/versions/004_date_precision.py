"""Record whether an issue date named a day.

Month-only dates are stored at midnight on the 1st. Existing rows are
backfilled conservatively: a calendar day other than the 1st, or an explicit
day in metadata, becomes ``day``. A 1st with no explicit day stays ``month``,
including timestamps that merely have a clock time.

Revision ID: 004
Revises: 003
Create Date: 2026-11-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from core.utils.date_precision import precision_for_existing_row

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = {
    "periodicals": ("extra_metadata", "parsed_metadata", "derived_metadata"),
    "discovered_issues": ("extra_metadata",),
}


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("date_precision", sa.String(length=8), nullable=True))
    _backfill(op.get_bind())


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("date_precision")


def _backfill(connection) -> None:
    for table, columns in _TABLES.items():
        selected = ", ".join(columns)
        rows = connection.execute(sa.text(f"SELECT id, issue_date, {selected} FROM {table}")).mappings()
        for row in rows:
            payloads = [row[column] for column in columns]
            precision = precision_for_existing_row(row["issue_date"], *payloads)
            if precision is None:
                continue
            connection.execute(
                sa.text(f"UPDATE {table} SET date_precision = :precision WHERE id = :row_id"),
                {"precision": precision, "row_id": row["id"]},
            )

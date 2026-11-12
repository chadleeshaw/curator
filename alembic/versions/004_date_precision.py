"""Record whether an issue date named a day.

Month-only dates are stored at midnight on the 1st. Existing rows are
backfilled from the rules copied below. A calendar day other than the 1st,
or an explicit day in metadata, becomes ``day``. A year with no month becomes
``year``. A 1st with no explicit day stays ``month``, including timestamps
that merely have a clock time.

These rules are frozen in this revision. Later changes to the application
parser must not be imported here.

Revision ID: 004
Revises: 003
Create Date: 2026-11-12
"""

import json
from datetime import datetime
from typing import Any, Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DAY = "day"
_MONTH = "month"
_YEAR = "year"

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


def precision_for_existing_row(issue_date: Any, *payloads: Any) -> Optional[str]:
    """Precision frozen for this revision. Do not import the live helper."""
    if _payloads_name_a_day(payloads):
        return _DAY
    parsed = _as_datetime(issue_date)
    if parsed is not None and parsed.day != 1:
        return _DAY
    if _payloads_have(payloads, "year") and not _payloads_have_month(payloads):
        return _YEAR
    if parsed is None:
        return None
    return _MONTH


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _payloads_have_month(payloads) -> bool:
    return _payloads_have(payloads, "month") or _payloads_have(payloads, "month_name")


def _payloads_have(payloads, field: str) -> bool:
    return any(_has_field(payload, field) for payload in payloads)


def _has_field(payload: Any, field: str) -> bool:
    if payload is None:
        return False
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return False
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
    if isinstance(payload, dict):
        if field in payload and _value_is_present(payload[field]):
            return True
        return any(_has_field(value, field) for value in payload.values())
    if isinstance(payload, list):
        return any(_has_field(value, field) for value in payload)
    return False


def _value_is_present(value: Any) -> bool:
    if isinstance(value, dict) and "value" in value:
        return _value_is_present(value["value"])
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, int):
        return value != 0
    return True


def _payloads_name_a_day(payloads) -> bool:
    return any(_names_a_day(payload) for payload in payloads)


def _names_a_day(payload: Any) -> bool:
    if payload is None:
        return False
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return False
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return False
    if isinstance(payload, dict):
        if _is_day_value(payload.get("day")):
            return True
        return any(_names_a_day(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_names_a_day(value) for value in payload)
    return False


def _is_day_value(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return 1 <= value <= 31
    if isinstance(value, str) and value.strip().isdigit():
        return 1 <= int(value.strip()) <= 31
    return False

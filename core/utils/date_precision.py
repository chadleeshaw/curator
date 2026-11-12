"""Decide date precision for rows saved before the column existed.

The parser now records ``day``, ``month``, or ``year`` when it reads a date.
Older rows only have ``issue_date``. Month-only and year-only dates were stored
on the 1st. A calendar day other than the 1st, or an explicit ``day`` field in
stored metadata, is evidence that a day was parsed. A clock time on the 1st is
not.
"""

import json
from datetime import datetime
from typing import Any, Optional

from core.constants.date import DATE_PRECISION_DAY, DATE_PRECISION_MONTH


def precision_for_existing_row(issue_date: Any, *payloads: Any) -> Optional[str]:
    """Conservative precision for one pre-existing row.

    Returns None when there is no date to describe. A named day, including the
    1st when metadata says so, is ``day``. Everything else with a date is
    ``month``, which does not claim the 1st was a real issue day.
    """
    if _payloads_name_a_day(payloads):
        return DATE_PRECISION_DAY
    parsed = _as_datetime(issue_date)
    if parsed is None:
        return None
    if parsed.day != 1:
        return DATE_PRECISION_DAY
    return DATE_PRECISION_MONTH


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


def _payloads_name_a_day(payloads) -> bool:
    for payload in payloads:
        if _names_a_day(payload):
            return True
    return False


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

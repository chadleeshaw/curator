"""Date precision comes from what the parser named, not from midnight on the 1st."""

from core.parsers.metadata import FilenameParser
from core.utils.date_precision import precision_for_existing_row


def test_a_full_iso_date_on_the_first_is_day_precision():
    parsed = FilenameParser().extract_from_nzb_title("City Paper 2024-01-01")
    assert parsed["date_precision"] == "day"
    assert parsed["day"] == 1


def test_a_month_name_is_month_precision():
    parsed = FilenameParser().extract_from_nzb_title("City Paper January 2024")
    assert parsed["date_precision"] == "month"
    assert parsed.get("day") is None


def test_a_later_iso_day_is_day_precision():
    parsed = FilenameParser().extract_from_nzb_title("City Paper 2024-01-14")
    assert parsed["date_precision"] == "day"
    assert parsed["day"] == 14


def test_a_year_only_title_is_year_precision():
    parsed = FilenameParser().extract_from_nzb_title("City Paper 2024")
    assert parsed["date_precision"] == "year"


def test_backfill_keeps_a_bare_first_as_month_only():
    assert precision_for_existing_row("2024-01-01 00:00:00") == "month"
    assert precision_for_existing_row("2024-01-01 08:30:00") == "month"


def test_backfill_treats_any_other_day_as_known():
    assert precision_for_existing_row("2024-01-14 00:00:00") == "day"


def test_backfill_trusts_an_explicit_day_on_the_first():
    assert precision_for_existing_row("2024-01-01 00:00:00", {"day": 1}) == "day"


def test_backfill_without_a_date_stays_unset():
    assert precision_for_existing_row(None) is None

"""Date precision comes from what the parser named, not from midnight on the 1st."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from core.parsers.metadata import FilenameParser
from core.parsers.parser import Parser
from core.utils.date_precision import precision_for_existing_row


def test_a_full_iso_date_on_the_first_is_day_precision():
    parsed = FilenameParser().extract_from_nzb_title("City Paper 2024-01-01")
    assert parsed["date_precision"] == "day"
    assert parsed["day"] == 1


def test_a_spaced_month_name_filename_is_month_precision():
    from pathlib import Path

    parsed = FilenameParser().extract_from_filename(Path("Wired January 2024.pdf"))
    assert parsed["date_precision"] == "month"
    assert parsed["month"] == 1


def test_a_feed_timestamp_without_a_title_date_is_month_precision():
    parsed = Parser().parse_search_result(
        title="City Paper",
        url="http://example.com/city.nzb",
        provider="newsnab",
        publication_date=datetime(2024, 1, 14, tzinfo=UTC),
    )
    assert parsed.raw_metadata["date_precision"] == "month"


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


def test_the_migration_keeps_its_own_copy_of_the_backfill_rules():
    path = Path("alembic/versions/004_date_precision.py")
    source = path.read_text()
    assert "core.utils.date_precision" not in source
    spec = importlib.util.spec_from_file_location("migration_004_date_precision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.precision_for_existing_row("2024-01-01", {"year": 2024}) == "year"
    assert module.precision_for_existing_row("2024-01-14") == "day"
    assert module.precision_for_existing_row("2024-01-01", {"year": 2024, "month": 1}) == "month"


def test_backfill_marks_a_year_without_a_month_as_year():
    assert precision_for_existing_row("2024-01-01 00:00:00", {"year": 2024}) == "year"
    assert precision_for_existing_row("2024-01-01", {"year": {"value": 2024}}) == "year"


def test_backfill_keeps_january_when_a_month_was_stored():
    assert precision_for_existing_row("2024-01-01", {"year": 2024, "month": "January"}) == "month"

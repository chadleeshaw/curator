"""
Tests for automatic metadata enhancement from text scan and OCR results.

All scan-derived fields (year, month, volume, issue_number, special_edition)
are stored in derived_metadata with {value, source, confidence} structure.
"""

from datetime import datetime

# Path setup handled by conftest.py

from services.ocr.queue import _apply_scan_metadata_to_periodical
from models.database import Periodical


def _dval(periodical, field):
    """Helper to extract value from derived_metadata structured entry."""
    entry = (periodical.derived_metadata or {}).get(field)
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


def _derived_entry(value, source="filename", confidence=1.0):
    """Helper to create a derived_metadata structured entry for test fixtures."""
    return {"value": value, "source": source, "confidence": confidence}


def test_apply_year_from_scan():
    """Test applying year from scan when not present in metadata"""
    periodical = Periodical(
        id=1,
        title="Test Magazine",
        language="English",
        issue_date=datetime(2000, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        user_id=1,
    )

    scan_metadata = {"year": 2024, "month": 6, "issue_number": 42}

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is True
    assert _dval(periodical, "year") == 2024
    assert _dval(periodical, "month") == 6
    assert _dval(periodical, "issue_number") == 42


def test_apply_volume_from_scan():
    """Test applying volume from scan when not present"""
    periodical = Periodical(
        id=2,
        title="Tech Monthly",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        user_id=1,
    )

    scan_metadata = {"volume": 32, "issue_number": 5, "year": 2023}

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is True
    assert _dval(periodical, "volume") == 32
    assert _dval(periodical, "issue_number") == 5
    assert _dval(periodical, "year") == 2023


def test_dont_overwrite_existing_year():
    """Test that existing year from filename parsing is not overridden by low-confidence OCR"""
    periodical = Periodical(
        id=3,
        title="Science Weekly",
        language="English",
        issue_date=datetime(2023, 3, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        derived_metadata={
            "year": _derived_entry(2023),
            "month": _derived_entry(3),
        },
        user_id=1,
    )

    # OCR provides different year but with low confidence (below 70% threshold)
    scan_metadata = {
        "year": 2022,
        "year_confidence": 50,
        "month": 12,
        "month_confidence": 50,
    }

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    # Should NOT update because OCR confidence too low, falls back to filename values (same as existing)
    assert updated is False
    assert _dval(periodical, "year") == 2023  # Original preserved
    assert _dval(periodical, "month") == 3  # Original preserved


def test_dont_overwrite_existing_issue_number():
    """Test that existing issue number from filename is preserved when OCR confidence is low"""
    periodical = Periodical(
        id=4,
        title="Gaming Magazine",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        derived_metadata={
            "issue_number": _derived_entry(405),
        },
        user_id=1,
    )

    # OCR provides different issue number but with low confidence
    scan_metadata = {
        "issue_number": 404,
        "issue_number_confidence": 65,
        "year": 2024,
        "year_confidence": 85,
    }

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    # Should only update year (high confidence), not issue_number (low confidence)
    assert updated is True
    assert _dval(periodical, "issue_number") == 405  # Original preserved (OCR rejected)
    assert _dval(periodical, "year") == 2024  # OCR value applied (high confidence)


def test_apply_special_edition_flag():
    """Test applying special edition flag from scan"""
    periodical = Periodical(
        id=5,
        title="Holiday Magazine",
        language="English",
        issue_date=datetime(2024, 12, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        user_id=1,
    )

    scan_metadata = {"year": 2024, "month": 12, "special_edition": True}

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is True
    assert _dval(periodical, "special_edition") is True
    assert _dval(periodical, "year") == 2024
    assert _dval(periodical, "month") == 12


def test_partial_metadata_enhancement():
    """Test filling in only missing fields"""
    periodical = Periodical(
        id=6,
        title="Mixed Metadata",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        derived_metadata={
            "year": _derived_entry(2024),
        },
        user_id=1,
    )

    scan_metadata = {
        "year": 2024,  # Same year
        "month": 8,
        "volume": 15,
        "issue_number": 3,
    }

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is True
    assert _dval(periodical, "year") == 2024  # Unchanged
    assert _dval(periodical, "month") == 8  # Added
    assert _dval(periodical, "volume") == 15  # Added
    assert _dval(periodical, "issue_number") == 3  # Added


def test_no_update_when_all_fields_present():
    """Test that filename values are preserved when OCR confidence is low"""
    periodical = Periodical(
        id=7,
        title="Complete Magazine",
        language="English",
        issue_date=datetime(2024, 5, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        derived_metadata={
            "year": _derived_entry(2024),
            "month": _derived_entry(5),
            "volume": _derived_entry(10),
            "issue_number": _derived_entry(123),
        },
        user_id=1,
    )

    # OCR provides different values but all with low confidence (below thresholds)
    scan_metadata = {
        "year": 2023,
        "year_confidence": 50,
        "month": 4,
        "month_confidence": 50,
        "volume": 9,
        "volume_confidence": 50,
        "issue_number": 122,
        "issue_number_confidence": 50,
    }

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    # Nothing should be updated (all OCR values rejected, filename values match existing)
    assert updated is False
    assert _dval(periodical, "year") == 2024
    assert _dval(periodical, "month") == 5
    assert _dval(periodical, "volume") == 10
    assert _dval(periodical, "issue_number") == 123


def test_empty_scan_metadata():
    """Test handling of empty scan metadata"""
    periodical = Periodical(
        id=8,
        title="Empty Scan",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        user_id=1,
    )

    scan_metadata = {}

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is False
    assert periodical.derived_metadata is None


def test_none_scan_metadata():
    """Test handling of None scan metadata"""
    periodical = Periodical(
        id=9,
        title="None Scan",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        user_id=1,
    )

    updated = _apply_scan_metadata_to_periodical(periodical, None)

    assert updated is False


def test_update_issue_date_when_year_found():
    """Test that issue_date is updated when year is applied from scan"""
    created_time = datetime(2024, 1, 15, 10, 30, 0)
    periodical = Periodical(
        id=10,
        title="Date Update Test",
        language="English",
        issue_date=created_time,
        file_path="/test/path.pdf",
        extra_metadata={},
        created_at=created_time,
        user_id=1,
    )

    scan_metadata = {"year": 2023, "month": 7}

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is True
    assert _dval(periodical, "year") == 2023
    assert _dval(periodical, "month") == 7
    assert periodical.issue_date.year == 2023
    assert periodical.issue_date.month == 7


def test_month_stored_as_int():
    """Test that month numbers are stored as integers in derived_metadata"""
    test_months = [(1, 1), (6, 6), (12, 12)]

    for month_num, expected_int in test_months:
        periodical = Periodical(
            id=11,
            title="Month Test",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/path.pdf",
            extra_metadata={},
            user_id=1,
        )

        scan_metadata = {"month": month_num}
        _apply_scan_metadata_to_periodical(periodical, scan_metadata)

        assert _dval(periodical, "month") == expected_int


def test_month_name_string_normalized_to_int():
    """Test that month name strings are normalized to integers"""
    periodical = Periodical(
        id=12,
        title="Month Name Test",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
        user_id=1,
    )

    scan_metadata = {"month": "June", "month_confidence": 90}

    updated = _apply_scan_metadata_to_periodical(periodical, scan_metadata)

    assert updated is True
    assert _dval(periodical, "month") == 6  # Normalized to int


if __name__ == "__main__":
    test_apply_year_from_scan()
    test_apply_volume_from_scan()
    test_dont_overwrite_existing_year()
    test_dont_overwrite_existing_issue_number()
    test_apply_special_edition_flag()
    test_partial_metadata_enhancement()
    test_no_update_when_all_fields_present()
    test_empty_scan_metadata()
    test_none_scan_metadata()
    test_update_issue_date_when_year_found()
    test_month_stored_as_int()
    test_month_name_string_normalized_to_int()
    print("All metadata enhancement tests passed!")

"""
Tests for automatic metadata enhancement from text scan and OCR results.
"""

import sys
from pathlib import Path
from datetime import datetime

# Path setup handled by conftest.py

from services.ocr.queue import _apply_scan_metadata_to_magazine
from models.database import Periodical


def test_apply_year_from_scan():
    """Test applying year from scan when not present in metadata"""
    magazine = Periodical(
        id=1,
        title="Test Magazine",
        language="English",
        issue_date=datetime(2000, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},  # No year set
    )

    scan_metadata = {"year": 2024, "month": 6, "issue_number": 42}

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    assert updated is True
    assert magazine.extra_metadata["year"] == 2024
    assert magazine.extra_metadata["month"] == "June"
    assert magazine.extra_metadata["issue_number"] == 42


def test_apply_volume_from_scan():
    """Test applying volume from scan when not present"""
    magazine = Periodical(
        id=2,
        title="Tech Monthly",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
    )

    scan_metadata = {"volume": 32, "issue_number": 5, "year": 2023}

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    assert updated is True
    assert magazine.extra_metadata["volume"] == 32
    assert magazine.extra_metadata["issue_number"] == 5
    assert magazine.extra_metadata["year"] == 2023


def test_dont_overwrite_existing_year():
    """Test that existing year from filename parsing is not overridden by low-confidence OCR"""
    magazine = Periodical(
        id=3,
        title="Science Weekly",
        language="English",
        issue_date=datetime(2023, 3, 1),
        file_path="/test/path.pdf",
        extra_metadata={
            "year": 2023,
            "month": "March",
        },  # Already has year from filename
    )

    # OCR provides different year but with low confidence (below 70% threshold)
    scan_metadata = {
        "year": 2022,
        "year_confidence": 50,  # Below 70% general threshold and 80% year-specific threshold
        "month": 12,
        "month_confidence": 50,  # Below 60% month-specific threshold
    }

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    # Should NOT update because OCR confidence too low, falls back to filename values
    assert updated is False
    assert magazine.extra_metadata["year"] == 2023  # Original preserved
    assert magazine.extra_metadata["month"] == "March"  # Original preserved


def test_dont_overwrite_existing_issue_number():
    """Test that existing issue number from filename is preserved when OCR confidence is low"""
    magazine = Periodical(
        id=4,
        title="Gaming Magazine",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={"issue_number": 405},  # Already has issue number
    )

    # OCR provides different issue number but with low confidence
    scan_metadata = {
        "issue_number": 404,
        "issue_number_confidence": 65,  # Below default 70% threshold
        "year": 2024,
        "year_confidence": 85,  # Above threshold - will be used
    }

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    # Should only update year (high confidence), not issue_number (low confidence)
    assert updated is True
    assert magazine.extra_metadata["issue_number"] == 405  # Original preserved (OCR rejected)
    assert magazine.extra_metadata["year"] == 2024  # OCR value applied (high confidence)


def test_apply_special_edition_flag():
    """Test applying special edition flag from scan"""
    magazine = Periodical(
        id=5,
        title="Holiday Magazine",
        language="English",
        issue_date=datetime(2024, 12, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
    )

    scan_metadata = {"year": 2024, "month": 12, "special_edition": True}

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    assert updated is True
    assert magazine.extra_metadata["special_edition"] is True
    assert magazine.extra_metadata["year"] == 2024
    assert magazine.extra_metadata["month"] == "December"


def test_partial_metadata_enhancement():
    """Test filling in only missing fields"""
    magazine = Periodical(
        id=6,
        title="Mixed Metadata",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={"year": 2024},  # Has year but not month/volume
    )

    scan_metadata = {
        "year": 2024,  # Same year
        "month": 8,  # Missing in magazine
        "volume": 15,  # Missing in magazine
        "issue_number": 3,  # Missing in magazine
    }

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    assert updated is True
    assert magazine.extra_metadata["year"] == 2024  # Unchanged
    assert magazine.extra_metadata["month"] == "August"  # Added
    assert magazine.extra_metadata["volume"] == 15  # Added
    assert magazine.extra_metadata["issue_number"] == 3  # Added


def test_no_update_when_all_fields_present():
    """Test that filename values are preserved when OCR confidence is low"""
    magazine = Periodical(
        id=7,
        title="Complete Magazine",
        language="English",
        issue_date=datetime(2024, 5, 1),
        file_path="/test/path.pdf",
        extra_metadata={
            "year": 2024,
            "month": "May",
            "volume": 10,
            "issue_number": 123,
        },
    )

    # OCR provides different values but all with low confidence (below thresholds)
    scan_metadata = {
        "year": 2023,
        "year_confidence": 50,  # Below 80% year threshold
        "month": 4,
        "month_confidence": 50,  # Below 60% month threshold
        "volume": 9,
        "volume_confidence": 50,  # Below 75% volume threshold
        "issue_number": 122,
        "issue_number_confidence": 50,  # Below 75% issue_number threshold
    }

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    # Nothing should be updated (all OCR values rejected due to low confidence)
    assert updated is False
    assert magazine.extra_metadata["year"] == 2024
    assert magazine.extra_metadata["month"] == "May"
    assert magazine.extra_metadata["volume"] == 10
    assert magazine.extra_metadata["issue_number"] == 123


def test_empty_scan_metadata():
    """Test handling of empty scan metadata"""
    magazine = Periodical(
        id=8,
        title="Empty Scan",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
    )

    scan_metadata = {}

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    assert updated is False
    assert magazine.extra_metadata == {}


def test_none_scan_metadata():
    """Test handling of None scan metadata"""
    magazine = Periodical(
        id=9,
        title="None Scan",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
    )

    updated = _apply_scan_metadata_to_magazine(magazine, None)

    assert updated is False


def test_update_issue_date_when_year_found():
    """Test that issue_date is updated when year is applied from scan"""
    # Create magazine with placeholder date (same as created_at)
    created_time = datetime(2024, 1, 15, 10, 30, 0)
    magazine = Periodical(
        id=10,
        title="Date Update Test",
        language="English",
        issue_date=created_time,  # Placeholder date
        file_path="/test/path.pdf",
        extra_metadata={},
        created_at=created_time,
    )

    scan_metadata = {"year": 2023, "month": 7}

    updated = _apply_scan_metadata_to_magazine(magazine, scan_metadata)

    assert updated is True
    assert magazine.extra_metadata["year"] == 2023
    assert magazine.extra_metadata["month"] == "July"
    # issue_date should be updated since it was a placeholder
    assert magazine.issue_date.year == 2023
    assert magazine.issue_date.month == 7


def test_month_conversion_to_name():
    """Test that month numbers are correctly converted to month names"""
    magazine = Periodical(
        id=11,
        title="Month Test",
        language="English",
        issue_date=datetime(2024, 1, 1),
        file_path="/test/path.pdf",
        extra_metadata={},
    )

    # Test various months
    test_months = [(1, "January"), (6, "June"), (12, "December")]

    for month_num, expected_name in test_months:
        mag = Periodical(
            id=11,
            title="Month Test",
            language="English",
            issue_date=datetime(2024, 1, 1),
            file_path="/test/path.pdf",
            extra_metadata={},
        )

        scan_metadata = {"month": month_num}
        _apply_scan_metadata_to_magazine(mag, scan_metadata)

        assert mag.extra_metadata.get("month") == expected_name


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
    test_month_conversion_to_name()
    print("✓ All metadata enhancement tests passed!")

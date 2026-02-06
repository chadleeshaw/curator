"""
Unit tests for core/utils/metadata_builder.py

Focuses on month normalization and issue_date sync from derived metadata,
particularly the OCR/text_scan string month → int conversion pipeline.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from core.utils.metadata_builder import (
    build_derived_metadata,
    sync_issue_date_from_derived,
    _normalize_month_to_int,
)


class TestNormalizeMonthToInt:
    """Tests for _normalize_month_to_int()"""

    def test_integer_passthrough(self):
        """Integer months 1-12 pass through unchanged"""
        for m in range(1, 13):
            assert _normalize_month_to_int(m) == m

    def test_integer_out_of_range(self):
        """Out-of-range integers return None"""
        assert _normalize_month_to_int(0) is None
        assert _normalize_month_to_int(13) is None
        assert _normalize_month_to_int(-1) is None

    def test_full_month_name(self):
        """Full month names are converted correctly"""
        assert _normalize_month_to_int("January") == 1
        assert _normalize_month_to_int("February") == 2
        assert _normalize_month_to_int("March") == 3
        assert _normalize_month_to_int("December") == 12

    def test_abbreviated_month_name(self):
        """Abbreviated month names are converted correctly"""
        assert _normalize_month_to_int("jan") == 1
        assert _normalize_month_to_int("feb") == 2
        assert _normalize_month_to_int("dec") == 12

    def test_case_insensitive(self):
        """Month name matching is case-insensitive"""
        assert _normalize_month_to_int("JANUARY") == 1
        assert _normalize_month_to_int("january") == 1
        assert _normalize_month_to_int("January") == 1
        assert _normalize_month_to_int("JAN") == 1

    def test_none_input(self):
        """None returns None"""
        assert _normalize_month_to_int(None) is None

    def test_unrecognized_string(self):
        """Unrecognized strings return None"""
        assert _normalize_month_to_int("notamonth") is None
        assert _normalize_month_to_int("") is None


class TestBuildDerivedMetadataMonthNormalization:
    """Tests that build_derived_metadata normalizes string months to int"""

    def test_ocr_scan_string_month_normalized(self):
        """OCR scan string month (e.g., 'January') is normalized to int"""
        ocr_scan = {"year": 2024, "month": "January", "confidence": 85}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert derived["month"]["value"] == 1
        assert derived["month"]["source"] == "ocr_scan"

    def test_ocr_scan_string_month_backfills_month_name(self):
        """When OCR provides a string month, month_name is also populated"""
        ocr_scan = {"year": 2024, "month": "January", "confidence": 85}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert derived["month_name"]["value"] == "January"
        assert derived["month_name"]["source"] == "ocr_scan"

    def test_text_scan_string_month_normalized(self):
        """Text scan string month is normalized to int"""
        text_scan = {"year": 2024, "month": "March", "confidence": 0.75}
        derived = build_derived_metadata(text_scan=text_scan)

        assert derived["month"]["value"] == 3
        assert derived["month"]["source"] == "text_scan"

    def test_text_scan_string_month_backfills_month_name(self):
        """When text scan provides a string month, month_name is also populated"""
        text_scan = {"year": 2024, "month": "September", "confidence": 0.75}
        derived = build_derived_metadata(text_scan=text_scan)

        assert derived["month_name"]["value"] == "September"
        assert derived["month_name"]["source"] == "text_scan"

    def test_file_scan_int_month_preserved(self):
        """File scan integer month passes through unchanged"""
        file_scan = {"year": 2024, "month": 6, "confidence": 0.85}
        derived = build_derived_metadata(file_scan=file_scan)

        assert derived["month"]["value"] == 6
        assert derived["month"]["source"] == "file_scan"

    def test_ocr_string_month_wins_over_file_scan_int(self):
        """OCR string month (higher priority) wins and is normalized"""
        file_scan = {"year": 2024, "month": 1, "confidence": 0.85}
        ocr_scan = {"year": 2024, "month": "March", "confidence": 85}
        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        assert derived["month"]["value"] == 3
        assert derived["month"]["source"] == "ocr_scan"
        assert derived["month_name"]["value"] == "March"
        assert derived["month_name"]["source"] == "ocr_scan"

    def test_file_scan_month_name_preserved_when_exists(self):
        """When file_scan provides explicit month_name, it's kept even if OCR wins month"""
        file_scan = {"year": 2024, "month": 6, "month_name": "June", "confidence": 0.85}
        ocr_scan = {"year": 2024, "month": "March", "confidence": 85}
        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        # month from OCR wins (higher priority)
        assert derived["month"]["value"] == 3
        assert derived["month"]["source"] == "ocr_scan"
        # month_name from file_scan wins the normal merge (only source with month_name)
        assert derived["month_name"]["value"] == "June"
        assert derived["month_name"]["source"] == "file_scan"

    def test_month_name_derived_when_no_source_provides_it(self):
        """When no source has month_name, it's derived from the winning month int"""
        ocr_scan = {"year": 2024, "month": "September", "confidence": 85}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert derived["month"]["value"] == 9
        assert derived["month_name"]["value"] == "September"
        assert derived["month_name"]["source"] == "ocr_scan"

    def test_month_name_derived_from_file_scan_int(self):
        """When file_scan has int month but no month_name, it's derived"""
        file_scan = {"year": 2024, "month": 6, "confidence": 0.85}
        derived = build_derived_metadata(file_scan=file_scan)

        assert derived["month"]["value"] == 6
        assert derived["month_name"]["value"] == "June"
        assert derived["month_name"]["source"] == "file_scan"

    def test_unrecognized_string_month_skipped(self):
        """Unrecognized string month is skipped, falls through to lower priority"""
        file_scan = {"year": 2024, "month": 6, "confidence": 0.85}
        ocr_scan = {"year": 2024, "month": "NotAMonth", "confidence": 85}
        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        assert derived["month"]["value"] == 6
        assert derived["month"]["source"] == "file_scan"


class TestSyncIssueDateFromDerived:
    """Tests for sync_issue_date_from_derived()"""

    def test_year_and_int_month(self):
        """Standard case: year + int month → datetime"""
        derived = {
            "year": {"value": 2024, "source": "file_scan", "confidence": 0.85},
            "month": {"value": 3, "source": "file_scan", "confidence": 0.85},
        }
        result = sync_issue_date_from_derived(derived)
        assert result == datetime(2024, 3, 1)

    def test_year_and_string_month(self):
        """OCR-like case: year + string month → datetime (now handled)"""
        derived = {
            "year": {"value": 2024, "source": "ocr_scan", "confidence": 85},
            "month": {"value": "March", "source": "ocr_scan", "confidence": 85},
        }
        result = sync_issue_date_from_derived(derived)
        assert result == datetime(2024, 3, 1)

    def test_year_only(self):
        """Year without month → January 1"""
        derived = {
            "year": {"value": 2024, "source": "file_scan", "confidence": 0.85},
        }
        result = sync_issue_date_from_derived(derived)
        assert result == datetime(2024, 1, 1)

    def test_no_year(self):
        """No year → None"""
        derived = {
            "month": {"value": 3, "source": "file_scan", "confidence": 0.85},
        }
        result = sync_issue_date_from_derived(derived)
        assert result is None

    def test_none_derived(self):
        """None derived_metadata → None"""
        assert sync_issue_date_from_derived(None) is None

    def test_empty_derived(self):
        """Empty derived_metadata → None"""
        assert sync_issue_date_from_derived({}) is None

    def test_string_month_abbreviated(self):
        """Abbreviated string month names work in sync"""
        derived = {
            "year": {"value": 2024, "source": "ocr_scan", "confidence": 85},
            "month": {"value": "Sep", "source": "ocr_scan", "confidence": 85},
        }
        result = sync_issue_date_from_derived(derived)
        assert result == datetime(2024, 9, 1)

    def test_unrecognized_string_month_falls_to_january(self):
        """Unrecognized string month falls back to year-only (January 1)"""
        derived = {
            "year": {"value": 2024, "source": "ocr_scan", "confidence": 85},
            "month": {"value": "NotAMonth", "source": "ocr_scan", "confidence": 85},
        }
        result = sync_issue_date_from_derived(derived)
        assert result == datetime(2024, 1, 1)


class TestEndToEndOCRMonthFlow:
    """Integration-style tests verifying the full OCR → derived → issue_date pipeline"""

    def test_ocr_scan_with_string_month_produces_correct_date(self):
        """
        Simulates the actual OCR pipeline:
        OCR returns month as "January" string → build_derived normalizes to int →
        sync_issue_date produces correct datetime
        """
        # This is what OCR's extract_metadata_from_text returns
        ocr_scan = {
            "year": 2024,
            "month": "January",
            "issue_number": None,
            "volume": None,
            "special_edition": False,
            "detected_text": "NATIONAL GEOGRAPHIC JANUARY 2024",
            "year_confidence": 95,
            "month_confidence": 90,
            "overall_confidence": 85,
            "confidence": 85,
        }

        file_scan = {
            "parse_source": "file",
            "confidence": 0.60,
            "year": 2024,
            "title": "National Geographic",
        }

        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        # Month from OCR should be normalized to int and be the winning source
        assert derived["month"]["value"] == 1
        assert derived["month"]["source"] == "ocr_scan"

        # issue_date should work correctly now
        issue_date = sync_issue_date_from_derived(derived)
        assert issue_date == datetime(2024, 1, 1)

    def test_text_scan_with_string_month_produces_correct_date(self):
        """
        Text scan also uses OCRService.extract_metadata_from_text,
        so it also returns string months.
        """
        text_scan = {
            "year": 2023,
            "month": "December",
            "issue_number": None,
            "volume": None,
            "special_edition": False,
            "detected_text": "December 2023 Issue",
            "confidence": 0.75,
        }

        derived = build_derived_metadata(text_scan=text_scan)

        assert derived["month"]["value"] == 12
        assert derived["month"]["source"] == "text_scan"

        issue_date = sync_issue_date_from_derived(derived)
        assert issue_date == datetime(2023, 12, 1)

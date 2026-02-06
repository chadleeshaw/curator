"""
Unit tests for core/utils/metadata_builder.py

Focuses on:
- Month normalization (string → int) for OCR/text_scan sources
- Confidence resolution (per-field, overall, generic) and scale normalization (0-100 → 0-1)
- issue_date sync from derived metadata
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


class TestConfidenceResolution:
    """Tests for confidence key resolution and scale normalization"""

    def test_ocr_overall_confidence_used_when_no_confidence_key(self):
        """OCR scan with overall_confidence but no confidence key should still work"""
        ocr_scan = {
            "year": 2023,
            "month": "May",
            "issue_number": 326,
            "overall_confidence": 93,
            "year_confidence": 96,
            "month_confidence": 76,
        }
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert derived["year"]["value"] == 2023
        assert derived["year"]["source"] == "ocr_scan"
        assert derived["month"]["value"] == 5
        assert derived["month"]["source"] == "ocr_scan"

    def test_per_field_confidence_preferred_over_overall(self):
        """Per-field confidence (year_confidence) takes priority over overall_confidence"""
        ocr_scan = {
            "year": 2023,
            "overall_confidence": 50,
            "year_confidence": 96,
        }
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert derived["year"]["value"] == 2023
        assert derived["year"]["source"] == "ocr_scan"
        # Should use year_confidence (96/100 = 0.96), not overall (50/100 = 0.50)
        assert derived["year"]["confidence"] == 0.96

    def test_confidence_0_100_scale_normalized_to_0_1(self):
        """Confidence values > 1.0 are normalized to 0-1 scale"""
        ocr_scan = {"year": 2023, "overall_confidence": 85}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert derived["year"]["confidence"] == 0.85

    def test_confidence_already_0_1_scale_unchanged(self):
        """Confidence values already in 0-1 range are not modified"""
        file_scan = {"year": 2023, "confidence": 0.85}
        derived = build_derived_metadata(file_scan=file_scan)

        assert derived["year"]["confidence"] == 0.85

    def test_string_confidence_high_mapped(self):
        """String confidence 'high' maps to 0.85"""
        file_scan = {"year": 2023, "confidence": "high"}
        derived = build_derived_metadata(file_scan=file_scan)

        assert derived["year"]["confidence"] == 0.85

    def test_ocr_beats_file_scan_when_confidence_resolved(self):
        """OCR should win over file_scan when confidence is properly resolved"""
        file_scan = {
            "year": 2026,
            "month": 1,
            "confidence": "high",
            "title": "Example Magazine",
        }
        ocr_scan = {
            "year": 2023,
            "month": "May",
            "issue_number": 326,
            "overall_confidence": 93,
            "year_confidence": 96,
            "month_confidence": 76,
        }
        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        # OCR should win for year and month (higher priority)
        assert derived["year"]["value"] == 2023
        assert derived["year"]["source"] == "ocr_scan"
        assert derived["month"]["value"] == 5
        assert derived["month"]["source"] == "ocr_scan"
        # Title only from file_scan (OCR doesn't extract titles)
        assert derived["title"]["value"] == "Example Magazine"
        assert derived["title"]["source"] == "file_scan"

    def test_real_world_ocr_confidence_missing_key_scenario(self):
        """
        Reproduces a production bug where OCR found year=2023, month=May but
        derived_metadata used file_scan year=2026.

        Root cause was OCR scan having no 'confidence' key (only 'overall_confidence'
        and per-field confidences), so confidence defaulted to 0.0 which was below
        the 0.70 threshold for ocr_scan.
        """
        file_scan = {
            "parse_source": "file",
            "confidence": "high",
            "year": 2026,
            "month": 1,
            "language": "English",
            "title": "Example Magazine",
            "base_title": "Example Magazine",
            "filename": "Example Magazine (20260205_232637).pdf",
            "matched_pattern": "year_only",
        }
        text_scan = {
            "issue_number": None,
            "year": None,
            "month": None,
            "volume": None,
            "special_edition": False,
            "year_confidence": None,
            "month_confidence": None,
            "overall_confidence": None,
            "extraction_method": "pdf_text",
            "has_sufficient_metadata": False,
        }
        ocr_scan = {
            "extraction_method": "ocr_pdf_pages",
            "issue_number": 326,
            "year": 2023,
            "month": "May",
            "volume": 89147,
            "special_edition": False,
            "year_confidence": 96,
            "month_confidence": 76,
            "issue_number_confidence": 96,
            "volume_confidence": 95,
            "overall_confidence": 93,
            "ocr_available": True,
            "text_found": True,
            "used_ocr": True,
        }

        derived = build_derived_metadata(file_scan=file_scan, text_scan=text_scan, ocr_scan=ocr_scan)

        # OCR should win for year (2023, not the filename-guessed 2026)
        assert derived["year"]["value"] == 2023
        assert derived["year"]["source"] == "ocr_scan"

        # OCR should win for month (May = 5, not filename-guessed 1)
        assert derived["month"]["value"] == 5
        assert derived["month"]["source"] == "ocr_scan"

        # month_name should be derived
        assert derived["month_name"]["value"] == "May"

        # issue_date should be May 2023
        issue_date = sync_issue_date_from_derived(derived)
        assert issue_date == datetime(2023, 5, 1)

        # Title still from file_scan (OCR doesn't extract titles)
        assert derived["title"]["value"] == "Example Magazine"


class TestVolumeValidation:
    """Tests for volume validation in build_derived_metadata"""

    def test_reasonable_volume_accepted(self):
        """Volume within range is accepted from OCR"""
        ocr_scan = {"volume": 354, "volume_confidence": 80, "overall_confidence": 90}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert "volume" in derived
        assert derived["volume"]["value"] == 354
        assert derived["volume"]["source"] == "ocr_scan"

    def test_zip_code_volume_rejected(self):
        """Volume that looks like a zip code (89147) is rejected"""
        ocr_scan = {"volume": 89147, "volume_confidence": 74, "overall_confidence": 91}
        file_scan = {"confidence": "high"}
        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        assert "volume" not in derived

    def test_zip_code_volume_falls_back_to_lower_source(self):
        """When OCR volume is rejected, fall back to file_scan volume if available"""
        ocr_scan = {"volume": 89147, "volume_confidence": 74, "overall_confidence": 91}
        file_scan = {"volume": 354, "confidence": "high"}
        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        assert "volume" in derived
        assert derived["volume"]["value"] == 354
        assert derived["volume"]["source"] == "file_scan"

    def test_max_boundary_volume_accepted(self):
        """Volume exactly at max (9999) is accepted"""
        ocr_scan = {"volume": 9999, "volume_confidence": 80, "overall_confidence": 90}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert "volume" in derived
        assert derived["volume"]["value"] == 9999

    def test_over_max_volume_rejected(self):
        """Volume just above max (10000) is rejected"""
        ocr_scan = {"volume": 10000, "volume_confidence": 80, "overall_confidence": 90}
        derived = build_derived_metadata(ocr_scan=ocr_scan)

        assert "volume" not in derived

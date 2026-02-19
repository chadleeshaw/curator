"""
Tests for metadata aggregation with priority-based source selection.

All scan-derived fields (year, month, volume, issue_number, special_edition)
are stored in derived_metadata with {value, source, confidence} structure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from models.database import Periodical
from services.ocr.queue import _apply_scan_metadata_to_magazine


def _dval(magazine, field):
    """Helper to extract value from derived_metadata structured entry."""
    entry = (magazine.derived_metadata or {}).get(field)
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


def _derived_entry(value, source="filename", confidence=1.0):
    """Helper to create a derived_metadata structured entry for test fixtures."""
    return {"value": value, "source": source, "confidence": confidence}


class TestMetadataAggregation:
    """Test metadata aggregation with source priority and confidence thresholds"""

    def setup_method(self):
        """Set up test fixtures"""
        # pylint: disable=attribute-defined-outside-init
        self.magazine = Periodical()
        self.magazine.title = "Test Magazine"
        self.magazine.extra_metadata = {}

    def test_ocr_high_confidence_overrides_filename(self):
        """Test OCR with high confidence overrides filename parsing"""
        self.magazine.derived_metadata = {
            "issue_number": _derived_entry("5"),
        }

        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert _dval(self.magazine, "year") == 2024

    def test_ocr_low_confidence_rejected_uses_filename(self):
        """Test OCR with low confidence is rejected, falls back to filename"""
        self.magazine.derived_metadata = {
            "year": _derived_entry(2023),
            "issue_number": _derived_entry("5"),
        }

        scan_metadata = {
            "year": 2024,
            "year_confidence": 55,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert _dval(self.magazine, "year") == 2023

    def test_per_field_aggregation_different_sources(self):
        """Test that different fields can come from different sources"""
        self.magazine.derived_metadata = {
            "issue_number": _derived_entry(5),
        }

        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "month": 1,
            "month_confidence": 92,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert _dval(self.magazine, "year") == 2024  # From OCR
        assert _dval(self.magazine, "month") == 1  # From OCR (stored as int)
        assert _dval(self.magazine, "issue_number") == 5  # From filename (preserved)

    def test_field_specific_overrides(self):
        """Test per-field confidence threshold overrides"""
        self.magazine.derived_metadata = None

        scan_metadata = {
            "year": 2024,
            "year_confidence": 75,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {"year": {"ocr": 80}},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is False
        assert _dval(self.magazine, "year") is None

    def test_source_priority_order(self):
        """Test that source priority order is respected"""
        self.magazine.derived_metadata = {
            "year": _derived_entry(2022),
        }
        self.magazine.parsed_metadata = {
            "text_scan": {"year": 2023},
        }

        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert _dval(self.magazine, "year") == 2024

    def test_backward_compatibility_no_config(self):
        """Test backward compatibility when no config is provided"""
        self.magazine.derived_metadata = {
            "year": _derived_entry(2022),
        }

        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "extraction_method": "ocr_image",
        }

        _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, None)

        assert _dval(self.magazine, "year") == 2024

    def test_text_scan_confidence_always_100(self):
        """Test that text_scan is treated as 100% confidence"""
        self.magazine.derived_metadata = None

        scan_metadata = {
            "year": 2024,
            "extraction_method": "pdf_text",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert _dval(self.magazine, "year") == 2024

    def test_month_number_stored_as_int(self):
        """Test that month numbers are stored as integers in derived_metadata"""
        self.magazine.derived_metadata = None

        scan_metadata = {
            "month": 1,
            "month_confidence": 92,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert _dval(self.magazine, "month") == 1

    def test_all_fields_below_threshold(self):
        """Test behavior when all sources fail to meet thresholds"""
        self.magazine.derived_metadata = None

        scan_metadata = {
            "year": 2024,
            "year_confidence": 50,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is False
        assert _dval(self.magazine, "year") is None

    def test_multiple_fields_with_mixed_confidence(self):
        """Test multiple fields with varying confidence levels"""
        self.magazine.derived_metadata = None

        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "month": 6,
            "month_confidence": 65,
            "issue_number": 42,
            "issue_number_confidence": 65,
            "volume": 10,
            "volume_confidence": 80,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {
                "month": {"ocr": 60},
                "issue_number": {"ocr": 75},
                "volume": {"ocr": 75},
            },
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert _dval(self.magazine, "year") == 2024  # Passed (85% >= 70%)
        assert _dval(self.magazine, "month") == 6  # Passed (65% >= 60% override)
        assert _dval(self.magazine, "issue_number") is None  # Failed (65% < 75%)
        assert _dval(self.magazine, "volume") == 10  # Passed (80% >= 75%)

    def test_priority_order_filename_first(self):
        """Test custom priority order with filename first (old behavior)"""
        self.magazine.derived_metadata = {
            "year": _derived_entry(2022),
        }

        scan_metadata = {
            "year": 2024,
            "year_confidence": 95,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["filename", "text_scan", "ocr"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert _dval(self.magazine, "year") == 2022

    def test_no_metadata_in_scan(self):
        """Test behavior when scan_metadata is empty"""
        self.magazine.derived_metadata = {
            "year": _derived_entry(2023),
        }

        scan_metadata = {}

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is False
        assert _dval(self.magazine, "year") == 2023

    def test_special_edition_field(self):
        """Test special_edition field aggregation"""
        self.magazine.derived_metadata = None

        scan_metadata = {
            "special_edition": True,
            "special_edition_confidence": 88,
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert _dval(self.magazine, "special_edition") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

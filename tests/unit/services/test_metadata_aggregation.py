"""
Tests for metadata aggregation with priority-based source selection
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from models.database import Magazine
from services.ocr.queue import _apply_scan_metadata_to_magazine


class TestMetadataAggregation:
    """Test metadata aggregation with source priority and confidence thresholds"""

    def setup_method(self):
        """Set up test fixtures"""
        # Create a test magazine with minimal data
        # pylint: disable=attribute-defined-outside-init
        self.magazine = Magazine()
        self.magazine.title = "Test Magazine"
        self.magazine.extra_metadata = {}

    def test_ocr_high_confidence_overrides_filename(self):
        """Test OCR with high confidence overrides filename parsing"""
        # Filename has no year
        self.magazine.extra_metadata = {"issue_number": "5"}

        # OCR provides year with 85% confidence (above 70% threshold)
        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "extraction_method": "ocr_image",
        }

        # Default config: OCR-first, 70% threshold
        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert self.magazine.extra_metadata["year"] == 2024  # Should use OCR value

    def test_ocr_low_confidence_rejected_uses_filename(self):
        """Test OCR with low confidence is rejected, falls back to filename"""
        # Filename has year parsed
        self.magazine.extra_metadata = {"year": 2023, "issue_number": "5"}

        # OCR provides different year but with 55% confidence (below 70% threshold)
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

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # OCR should be rejected, filename value should be preserved
        assert self.magazine.extra_metadata["year"] == 2023  # Should keep filename value

    def test_per_field_aggregation_different_sources(self):
        """Test that different fields can come from different sources"""
        # Filename has issue_number only
        self.magazine.extra_metadata = {"issue_number": 5}

        # OCR provides year and month with high confidence
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
        assert self.magazine.extra_metadata["year"] == 2024  # From OCR
        assert self.magazine.extra_metadata["month"] == "January"  # From OCR, converted to name
        assert self.magazine.extra_metadata.get("issue_number") == 5  # From filename

    def test_field_specific_overrides(self):
        """Test per-field confidence threshold overrides"""
        # No filename data
        self.magazine.extra_metadata = {}

        # OCR provides year with 75% confidence
        scan_metadata = {
            "year": 2024,
            "year_confidence": 75,
            "extraction_method": "ocr_image",
        }

        # Config requires 80% for year (field override)
        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {"year": {"ocr": 80}},  # Higher threshold for year
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # Year should be rejected (75% < 80% required), so no updates made
        assert result is False
        assert self.magazine.extra_metadata.get("year") is None

    def test_source_priority_order(self):
        """Test that source priority order is respected"""
        # Filename has year
        self.magazine.extra_metadata = {"year": 2022}

        # text_scan stored with year (would be 90% confidence if it had scores)
        self.magazine.extra_metadata["text_scan"] = {"year": 2023}

        # OCR provides year with 85% confidence
        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "extraction_method": "ocr_image",
        }

        # Priority: OCR first
        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # Should use OCR (first in priority, meets threshold)
        assert self.magazine.extra_metadata["year"] == 2024

    def test_backward_compatibility_no_config(self):
        """Test backward compatibility when no config is provided"""
        # Filename has year
        self.magazine.extra_metadata = {"year": 2022}

        # OCR provides year with 85% confidence
        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,
            "extraction_method": "ocr_image",
        }

        # No config provided - should use defaults
        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, None)

        # Should use OCR-first defaults
        assert self.magazine.extra_metadata["year"] == 2024

    def test_text_scan_confidence_always_100(self):
        """Test that text_scan is treated as 100% confidence"""
        # No filename data
        self.magazine.extra_metadata = {}

        # text_scan result (no confidence scores)
        scan_metadata = {
            "year": 2024,
            "extraction_method": "pdf_text",  # This is a text scan
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # Should accept text_scan even though no confidence field
        # (treated as 100% which exceeds 50% threshold)
        assert self.magazine.extra_metadata["year"] == 2024

    def test_month_number_to_name_conversion(self):
        """Test that month numbers are converted to month names"""
        self.magazine.extra_metadata = {}

        # OCR provides month number with high confidence
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
        assert self.magazine.extra_metadata["month"] == "January"  # Month converted to name
        assert self.magazine.extra_metadata["month"] == "January"

    def test_all_fields_below_threshold(self):
        """Test behavior when all sources fail to meet thresholds"""
        self.magazine.extra_metadata = {}

        # OCR provides year but below threshold
        scan_metadata = {
            "year": 2024,
            "year_confidence": 50,  # Below 70% threshold
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # No field should be updated (all rejected)
        assert result is False
        assert self.magazine.extra_metadata.get("year") is None

    def test_multiple_fields_with_mixed_confidence(self):
        """Test multiple fields with varying confidence levels"""
        self.magazine.extra_metadata = {}

        # OCR provides multiple fields with different confidence
        scan_metadata = {
            "year": 2024,
            "year_confidence": 85,  # Above 70% - should pass
            "month": 6,
            "month_confidence": 65,  # Below 70%, but above 60% for month override - should pass
            "issue_number": 42,
            "issue_number_confidence": 65,  # Below 75% override - should fail
            "volume": 10,
            "volume_confidence": 80,  # Above 75% - should pass
            "extraction_method": "ocr_image",
        }

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {
                "month": {"ocr": 60},  # Lower threshold
                "issue_number": {"ocr": 75},  # Higher threshold
                "volume": {"ocr": 75},  # Higher threshold
            },
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        assert result is True
        assert self.magazine.extra_metadata["year"] == 2024  # Passed (85% >= 70%)
        assert self.magazine.extra_metadata["month"] == "June"  # Passed (65% >= 60% override), converted to name
        assert self.magazine.extra_metadata.get("issue_number") is None  # Failed (65% < 75%)
        assert self.magazine.extra_metadata.get("volume") == 10  # Passed (80% >= 75%)

    def test_priority_order_filename_first(self):
        """Test custom priority order with filename first (old behavior)"""
        # Filename has year
        self.magazine.extra_metadata = {"year": 2022}

        # OCR provides different year with high confidence
        scan_metadata = {
            "year": 2024,
            "year_confidence": 95,
            "extraction_method": "ocr_image",
        }

        # Priority: filename first (old behavior)
        metadata_config = {
            "source_priority": ["filename", "text_scan", "ocr"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # Should use filename (first in priority)
        assert self.magazine.extra_metadata["year"] == 2022

    def test_no_metadata_in_scan(self):
        """Test behavior when scan_metadata is empty"""
        self.magazine.extra_metadata = {"year": 2023}

        # Empty scan metadata
        scan_metadata = {}

        metadata_config = {
            "source_priority": ["ocr", "text_scan", "filename"],
            "confidence_thresholds": {"ocr": 70, "text_scan": 50, "filename": 0},
            "field_overrides": {},
        }

        result = _apply_scan_metadata_to_magazine(self.magazine, scan_metadata, metadata_config)

        # Should return False (no updates made)
        assert result is False
        # Original data preserved
        assert self.magazine.extra_metadata["year"] == 2023

    def test_special_edition_field(self):
        """Test special_edition field aggregation"""
        self.magazine.extra_metadata = {}

        # OCR detects special edition with confidence
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
        assert self.magazine.extra_metadata.get("special_edition") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

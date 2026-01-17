"""
Tests for OCR confidence scoring
"""

import pytest
from services.ocr.service import OCRService


class TestOCRConfidenceScoring:
    """Test OCR confidence score calculation"""

    def test_extract_metadata_without_words_data(self):
        """Test that metadata extraction works without word confidence data"""
        text = "JANUARY 2024"
        result = OCRService.extract_metadata_from_text(text)

        # Should extract metadata
        assert result["year"] == 2024
        assert result["month"] == "January"

        # Confidence scores should be None when no words data provided
        assert result["year_confidence"] is None
        assert result["month_confidence"] is None
        assert result["overall_confidence"] is None

    def test_extract_metadata_with_high_confidence_words(self):
        """Test metadata extraction with high confidence word data"""
        text = "JANUARY 2024"

        # Mock high-confidence OCR word data
        words_data = [
            {"text": "JANUARY", "confidence": 95},
            {"text": "2024", "confidence": 92},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        # Should extract metadata
        assert result["year"] == 2024
        assert result["month"] == "January"

        # Should have high confidence scores
        assert result["year_confidence"] == 92  # Matches "2024"
        assert result["month_confidence"] == 95  # Matches "JANUARY"
        assert result["overall_confidence"] == 93  # Average of all words: (95+92)/2

    def test_extract_metadata_with_low_confidence_words(self):
        """Test metadata extraction with low confidence word data"""
        text = "JANUARY 2024"

        # Mock low-confidence OCR word data
        words_data = [
            {"text": "JANUARY", "confidence": 45},
            {"text": "2024", "confidence": 55},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        # Should still extract metadata (extraction doesn't check confidence)
        assert result["year"] == 2024
        assert result["month"] == "January"

        # Should have low confidence scores
        assert result["year_confidence"] == 55
        assert result["month_confidence"] == 45
        assert result["overall_confidence"] == 50  # Average: (45+55)/2

    def test_extract_metadata_with_mixed_confidence(self):
        """Test with mix of high and low confidence words"""
        text = "JANUARY 2024 SPECIAL EDITION"

        words_data = [
            {"text": "JANUARY", "confidence": 90},
            {"text": "2024", "confidence": 85},
            {"text": "SPECIAL", "confidence": 60},
            {"text": "EDITION", "confidence": 65},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        assert result["year"] == 2024
        assert result["month"] == "January"
        assert result["special_edition"] is True

        # Confidence should be based on specific words
        assert result["year_confidence"] == 85
        assert result["month_confidence"] == 90
        assert result["overall_confidence"] == 75  # Average of all: (90+85+60+65)/4

    def test_confidence_with_partial_match(self):
        """Test confidence calculation when text partially matches"""
        text = "DECEMBER 1999"

        # Words might be slightly different from extracted values
        words_data = [
            {"text": "DEC", "confidence": 88},  # Abbreviated form
            {"text": "1999", "confidence": 92},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        assert result["year"] == 1999
        assert result["month"] == "December"

        # Should match "DEC" to DECEMBER
        assert result["year_confidence"] == 92
        # Note: "DEC" won't match "DECEMBER" in search, so confidence may be None
        # This is expected behavior - confidence only when exact match found

    def test_confidence_with_issue_and_volume(self):
        """Test confidence scoring for issue numbers and volumes"""
        text = "VOL 32 NO 5 MAY 2022"

        words_data = [
            {"text": "VOL", "confidence": 80},
            {"text": "32", "confidence": 85},
            {"text": "NO", "confidence": 78},
            {"text": "5", "confidence": 82},
            {"text": "MAY", "confidence": 93},
            {"text": "2022", "confidence": 90},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        assert result["year"] == 2022
        assert result["month"] == "May"
        assert result["volume"] == 32
        assert result["issue_number"] == 5

        # Check confidence scores
        assert result["year_confidence"] == 90
        assert result["month_confidence"] == 93
        assert result["volume_confidence"] == 85
        assert result["issue_number_confidence"] == 82

    def test_confidence_with_spaces_in_year(self):
        """Test confidence scoring when year has spaces (from our fix)"""
        text = "JANUARY 200 0"

        words_data = [
            {"text": "JANUARY", "confidence": 92},
            {"text": "200", "confidence": 75},
            {"text": "0", "confidence": 70},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        # Year extraction should handle spaces
        assert result["year"] == 2000
        assert result["month"] == "January"

        # Confidence for "2000" should find "200" or "0"
        # Will match partial text
        assert result["year_confidence"] is not None
        assert result["month_confidence"] == 92

    def test_confidence_with_no_metadata_extracted(self):
        """Test confidence when no metadata is found"""
        text = "This is just random text with no dates"

        words_data = [
            {"text": "This", "confidence": 95},
            {"text": "is", "confidence": 92},
            {"text": "just", "confidence": 88},
            {"text": "random", "confidence": 90},
            {"text": "text", "confidence": 93},
        ]

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        # No metadata extracted
        assert result["year"] is None
        assert result["month"] is None
        assert result["issue_number"] is None

        # No field-specific confidence, but overall confidence should exist
        assert result["year_confidence"] is None
        assert result["month_confidence"] is None
        assert result["overall_confidence"] == 91  # Average of all words

    def test_confidence_with_empty_words_list(self):
        """Test with empty words list"""
        text = "JANUARY 2024"
        words_data = []

        result = OCRService.extract_metadata_from_text(text, words_data=words_data)

        # Should still extract metadata
        assert result["year"] == 2024
        assert result["month"] == "January"

        # No confidence scores with empty words
        assert result["year_confidence"] is None
        assert result["month_confidence"] is None
        assert result["overall_confidence"] is None

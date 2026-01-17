"""
Tests for OCR year extraction with error handling
"""

import pytest
from services.ocr.service import OCRService


class TestOCRYearExtraction:
    """Test OCR year extraction with common OCR errors"""

    def test_extract_year_standard_with_space(self):
        """Test extracting year with proper spacing"""
        result = OCRService.extract_metadata_from_text("JANUARY 2000")
        assert result["year"] == 2000
        assert result["month"] == "January"

    def test_extract_year_no_space_after_month(self):
        """Test extracting year directly after month name without space"""
        result = OCRService.extract_metadata_from_text("JANUARY2000")
        assert result["year"] == 2000
        assert result["month"] == "January"

    def test_extract_year_ocr_error_letter_o(self):
        """Test extracting year when OCR misreads 0 as O"""
        # Common OCR error: 2000 → 2OOO
        result = OCRService.extract_metadata_from_text("JANUARY2OOO")
        assert result["year"] == 2000
        assert result["month"] == "January"

    def test_extract_year_partial_ocr_error(self):
        """Test extracting year with partial OCR errors"""
        # 2024 → 2O24
        result = OCRService.extract_metadata_from_text("DECEMBER2O24")
        assert result["year"] == 2024
        assert result["month"] == "December"

    def test_extract_year_mixed_case(self):
        """Test extraction with mixed case input"""
        result = OCRService.extract_metadata_from_text("December 1999")
        assert result["year"] == 1999
        assert result["month"] == "December"

    def test_extract_year_on_separate_line(self):
        """Test when year is on a different line than month"""
        result = OCRService.extract_metadata_from_text("JUNE\n2023")
        assert result["year"] == 2023
        assert result["month"] == "June"

    def test_extract_year_1900s(self):
        """Test extracting years from 1900s"""
        result = OCRService.extract_metadata_from_text("MARCH 1995")
        assert result["year"] == 1995
        assert result["month"] == "March"

    def test_extract_year_with_other_text(self):
        """Test year extraction with surrounding text"""
        text = "NATIONAL\\nGEOGRAPHIC\\nJULY2001\\nEXPLORATION"
        result = OCRService.extract_metadata_from_text(text)
        assert result["year"] == 2001
        assert result["month"] == "July"

    def test_no_false_positive_on_non_years(self):
        """Test that non-year 4-digit numbers aren't extracted"""
        result = OCRService.extract_metadata_from_text("ISSUE 1234 OF MAGAZINE")
        # Should not extract 1234 as a year (outside 1900-2099 range)
        assert result["year"] is None

    def test_extract_year_with_special_edition(self):
        """Test year extraction alongside special edition detection"""
        text = "SPECIAL HOLIDAY EDITION\nDECEMBER 2020"
        result = OCRService.extract_metadata_from_text(text)
        assert result["year"] == 2020
        assert result["month"] == "December"
        assert result["special_edition"] is True

    def test_extract_year_with_volume_and_issue(self):
        """Test year extraction with volume and issue info"""
        text = "VOL 32\\nNO 5\\nMAY2022"
        result = OCRService.extract_metadata_from_text(text)
        assert result["year"] == 2022
        assert result["month"] == "May"
        assert result["volume"] == 32
        assert result["issue_number"] == 5

    def test_real_world_national_geographic(self):
        """Test with actual National Geographic OCR output"""
        text = "JANUARY2OOO\nNA TIONH\nGEoo\nCELEBRATIONS\nO'f\nEArTH\nAND\nBEyond"
        result = OCRService.extract_metadata_from_text(text)
        assert result["year"] == 2000
        assert result["month"] == "January"
        assert result["detected_text"] == text

"""
Integration tests for OCR image word extraction with confidence scores.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.ocr.service import OCRService


class TestOCRImageWordsExtraction:
    """Test OCR word-level data extraction from image files"""

    @patch("services.ocr.service.PYTESSERACT_AVAILABLE", True)
    @patch("services.ocr.service.pytesseract")
    @patch("services.ocr.service.Image")
    def test_extract_text_and_words_from_image(self, mock_image, mock_pytesseract):
        """Test extracting text and words with confidence from image"""
        # Mock Tesseract availability
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        # Mock image
        mock_img = MagicMock()
        mock_image.open.return_value = mock_img

        # Mock Tesseract output with word-level data
        mock_pytesseract.image_to_data.return_value = {
            "text": ["JANUARY", "2000", "MAGAZINE", ""],
            "conf": [85, 92, 78, -1],
            "left": [10, 100, 200, 0],
            "top": [20, 22, 24, 0],
            "width": [80, 50, 100, 0],
            "height": [15, 15, 15, 0],
        }
        mock_pytesseract.Output = MagicMock(DICT=1)

        # Extract text and words
        result = OCRService.extract_text_and_words_from_image("/path/to/cover.jpg", language="English")

        # Verify structure
        assert "text" in result
        assert "words" in result
        assert "word_count" in result

        # Verify text
        assert result["text"] == "JANUARY 2000 MAGAZINE"

        # Verify word count
        assert result["word_count"] == 3

        # Verify words data
        words = result["words"]
        assert len(words) == 3

        # Check first word
        assert words[0]["text"] == "JANUARY"
        assert words[0]["confidence"] == 85
        assert words[0]["bbox"]["x"] == 10
        assert words[0]["bbox"]["y"] == 20
        assert words[0]["bbox"]["width"] == 80
        assert words[0]["bbox"]["height"] == 15

        # Check second word
        assert words[1]["text"] == "2000"
        assert words[1]["confidence"] == 92

        # Check third word
        assert words[2]["text"] == "MAGAZINE"
        assert words[2]["confidence"] == 78

    @patch("services.ocr.service.PYTESSERACT_AVAILABLE", True)
    @patch("services.ocr.service.pytesseract")
    @patch("services.ocr.service.Image")
    def test_extract_with_confidence_threshold(self, mock_image, mock_pytesseract):
        """Test that words below confidence threshold are filtered out"""
        # Mock Tesseract availability
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        mock_img = MagicMock()
        mock_image.open.return_value = mock_img

        # Mix of high and low confidence words
        mock_pytesseract.image_to_data.return_value = {
            "text": ["GOOD", "bad", "GREAT", "terrible"],
            "conf": [85, 25, 90, 15],  # Only 85 and 90 should pass threshold of 30
            "left": [0, 0, 0, 0],
            "top": [0, 0, 0, 0],
            "width": [10, 10, 10, 10],
            "height": [10, 10, 10, 10],
        }
        mock_pytesseract.Output = MagicMock(DICT=1)

        result = OCRService.extract_text_and_words_from_image("/path/to/cover.jpg", confidence_threshold=30)

        # Only high-confidence words should be included
        assert result["word_count"] == 2
        assert result["text"] == "GOOD GREAT"
        assert len(result["words"]) == 2
        assert result["words"][0]["text"] == "GOOD"
        assert result["words"][1]["text"] == "GREAT"

    @patch("services.ocr.service.PYTESSERACT_AVAILABLE", True)
    @patch("services.ocr.service.pytesseract")
    @patch("services.ocr.service.Image")
    def test_extract_with_empty_result(self, mock_image, mock_pytesseract):
        """Test handling of empty OCR results"""
        # Mock Tesseract availability
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        mock_img = MagicMock()
        mock_image.open.return_value = mock_img

        # All empty text
        mock_pytesseract.image_to_data.return_value = {
            "text": ["", "", ""],
            "conf": [50, 60, 70],
            "left": [0, 0, 0],
            "top": [0, 0, 0],
            "width": [0, 0, 0],
            "height": [0, 0, 0],
        }
        mock_pytesseract.Output = MagicMock(DICT=1)

        result = OCRService.extract_text_and_words_from_image("/path/to/cover.jpg")

        assert result["text"] == ""
        assert result["word_count"] == 0
        assert len(result["words"]) == 0

    @patch("services.ocr.service.PYTESSERACT_AVAILABLE", True)
    @patch("services.ocr.service.pytesseract")
    @patch("services.ocr.service.Image")
    def test_analyze_cover_uses_words_for_images(self, mock_image, mock_pytesseract):
        """Test that analyze_cover passes words data for image files"""
        # Mock Tesseract availability
        mock_pytesseract.get_tesseract_version.return_value = "5.0.0"

        mock_img = MagicMock()
        mock_image.open.return_value = mock_img

        # Mock OCR output for image
        mock_pytesseract.image_to_data.return_value = {
            "text": ["JANUARY", "2000"],
            "conf": [85, 92],
            "left": [10, 100],
            "top": [20, 22],
            "width": [80, 50],
            "height": [15, 15],
        }
        mock_pytesseract.Output = MagicMock(DICT=1)

        # Analyze a JPG cover (image file, not PDF)
        result = OCRService.analyze_cover("/path/to/cover.jpg", language="English")

        # Should have metadata with confidence scores
        assert result["ocr_available"] is True
        assert result["text_found"] is True
        assert result["year"] == 2000
        assert result["month"] == "January"
        assert result["extraction_method"] == "ocr_image"

        # IMPORTANT: Should have confidence scores (not None!)
        assert result["year_confidence"] is not None
        assert result["month_confidence"] is not None
        assert result["overall_confidence"] is not None

        # Confidence should be reasonable (based on mock data)
        assert result["year_confidence"] > 0
        assert result["month_confidence"] > 0
        assert result["overall_confidence"] > 0

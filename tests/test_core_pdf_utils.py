"""
Tests for PDF utility functions (core/pdf_utils.py)

Test Coverage:
- PDF cover extraction
- Error handling for PDF operations
- Integration with pdf2image library
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pdf_utils import extract_cover_from_pdf
from core.constants import PDF_COVER_DPI_LOW, PDF_COVER_QUALITY


class TestExtractCoverFromPDF:
    """Test PDF cover extraction functionality"""

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_success(self, mock_convert, tmp_path):
        """Test successful cover extraction from PDF."""
        pdf_path = tmp_path / "magazine.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        # Mock the image returned from pdf2image
        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        # Verify convert_from_path was called correctly
        mock_convert.assert_called_once_with(
            str(pdf_path), first_page=1, last_page=1, dpi=PDF_COVER_DPI_LOW
        )

        # Verify image was saved
        expected_cover = output_dir / "magazine.jpg"
        mock_image.save.assert_called_once_with(
            str(expected_cover), "JPEG", quality=PDF_COVER_QUALITY
        )

        # Verify result
        assert result == expected_cover

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_creates_output_dir(self, mock_convert, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "nested" / "covers" / "dir"

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        extract_cover_from_pdf(pdf_path, output_dir)

        assert output_dir.exists()
        assert output_dir.is_dir()

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_with_custom_dpi(self, mock_convert, tmp_path):
        """Test cover extraction with custom DPI setting."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"
        custom_dpi = 300

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        extract_cover_from_pdf(pdf_path, output_dir, dpi=custom_dpi)

        mock_convert.assert_called_once_with(
            str(pdf_path), first_page=1, last_page=1, dpi=custom_dpi
        )

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_with_custom_quality(self, mock_convert, tmp_path):
        """Test cover extraction with custom JPEG quality."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"
        custom_quality = 95

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        extract_cover_from_pdf(pdf_path, output_dir, quality=custom_quality)

        expected_cover = output_dir / "test.jpg"
        mock_image.save.assert_called_once_with(
            str(expected_cover), "JPEG", quality=custom_quality
        )

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_no_images_returned(self, mock_convert, tmp_path):
        """Test handling when pdf2image returns no images."""
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_convert.return_value = []

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_import_error(self, mock_convert, tmp_path):
        """Test handling when pdf2image is not installed."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_convert.side_effect = ImportError("pdf2image not found")

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_conversion_error(self, mock_convert, tmp_path):
        """Test handling when PDF conversion fails."""
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_convert.side_effect = Exception("PDF conversion failed")

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_save_error(self, mock_convert, tmp_path):
        """Test handling when image save fails."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_image = Mock()
        mock_image.save.side_effect = IOError("Failed to save image")
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_filename_preservation(self, mock_convert, tmp_path):
        """Test that PDF filename (stem) is preserved in cover filename."""
        pdf_names = [
            "Magazine - January 2024.pdf",
            "test_file_123.pdf",
            "document with spaces.pdf",
        ]

        for pdf_name in pdf_names:
            pdf_path = tmp_path / pdf_name
            pdf_path.touch()
            output_dir = tmp_path / "covers"

            mock_image = Mock()
            mock_convert.return_value = [mock_image]

            result = extract_cover_from_pdf(pdf_path, output_dir)

            expected_name = f"{pdf_path.stem}.jpg"
            assert result.name == expected_name

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_only_first_page(self, mock_convert, tmp_path):
        """Test that only the first page is extracted."""
        pdf_path = tmp_path / "multipage.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_images = [Mock(), Mock(), Mock()]  # Multiple pages
        mock_convert.return_value = mock_images

        extract_cover_from_pdf(pdf_path, output_dir)

        # Only the first image should be saved
        mock_images[0].save.assert_called_once()
        mock_images[1].save.assert_not_called()
        mock_images[2].save.assert_not_called()

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_uses_default_constants(self, mock_convert, tmp_path):
        """Test that default DPI and quality constants are used."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        extract_cover_from_pdf(pdf_path, output_dir)

        # Verify default DPI was used
        call_args = mock_convert.call_args
        assert call_args[1]["dpi"] == PDF_COVER_DPI_LOW

        # Verify default quality was used
        save_call_args = mock_image.save.call_args
        assert save_call_args[1]["quality"] == PDF_COVER_QUALITY


class TestPDFUtilsEdgeCases:
    """Test edge cases and error conditions"""

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_with_special_characters_in_filename(self, mock_convert, tmp_path):
        """Test cover extraction with special characters in PDF name."""
        # Some filesystems have restrictions on special characters
        pdf_path = tmp_path / "mag@zine#2024.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is not None
        assert result.suffix == ".jpg"

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_output_dir_already_exists(self, mock_convert, tmp_path):
        """Test that existing output directory doesn't cause errors."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"
        output_dir.mkdir()  # Create directory first

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is not None

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_overwrites_existing_cover(self, mock_convert, tmp_path):
        """Test that existing cover is overwritten."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"
        output_dir.mkdir()

        # Create existing cover
        existing_cover = output_dir / "test.jpg"
        existing_cover.write_text("old content")

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        # Should save to the same path (overwriting)
        assert result == existing_cover
        mock_image.save.assert_called_once()


class TestPDFUtilsIntegration:
    """Integration tests for PDF utilities"""

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_covers_from_multiple_pdfs(self, mock_convert, tmp_path):
        """Test extracting covers from multiple PDF files."""
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        output_dir = tmp_path / "covers"

        pdf_files = [
            pdf_dir / "magazine1.pdf",
            pdf_dir / "magazine2.pdf",
            pdf_dir / "magazine3.pdf",
        ]

        for pdf_path in pdf_files:
            pdf_path.touch()

        # Mock convert_from_path to return a mock image each time
        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        results = []
        for pdf_path in pdf_files:
            result = extract_cover_from_pdf(pdf_path, output_dir)
            results.append(result)

        assert len(results) == 3
        assert all(r is not None for r in results)
        assert all(r.suffix == ".jpg" for r in results)
        assert len(set(r.name for r in results)) == 3  # All unique names

    @patch("core.pdf_utils.convert_from_path")
    def test_extract_cover_workflow(self, mock_convert, tmp_path):
        """Test complete workflow of cover extraction."""
        # Setup
        pdf_path = tmp_path / "test_magazine.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf content")
        output_dir = tmp_path / "extracted_covers"

        # Mock pdf2image
        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        # Execute
        cover_path = extract_cover_from_pdf(pdf_path, output_dir)

        # Verify
        assert cover_path is not None
        assert cover_path.parent == output_dir
        assert cover_path.stem == "test_magazine"
        assert output_dir.exists()
        mock_convert.assert_called_once()
        mock_image.save.assert_called_once()

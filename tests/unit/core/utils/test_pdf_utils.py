"""
Tests for PDF utility functions (core/pdf_utils.py)

Test Coverage:
- PDF cover extraction
- Error handling for PDF operations
- Integration with pdf2image library
"""

from unittest.mock import Mock, MagicMock, patch


# Path setup handled by conftest.py

from core.utils.pdf import extract_cover_from_pdf, is_landscape_page
from core.constants.files import PDF_COVER_DPI_LOW, PDF_COVER_QUALITY


class TestExtractCoverFromPDF:
    """Test PDF cover extraction functionality"""

    @patch("core.utils.pdf.convert_from_path")
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
        mock_convert.assert_called_once_with(str(pdf_path), first_page=1, last_page=1, dpi=PDF_COVER_DPI_LOW)

        # Verify image was saved
        expected_cover = output_dir / "magazine.jpg"
        mock_image.save.assert_called_once_with(str(expected_cover), "JPEG", quality=PDF_COVER_QUALITY)

        # Verify result
        assert result == expected_cover

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_with_custom_dpi(self, mock_convert, tmp_path):
        """Test cover extraction with custom DPI setting."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"
        custom_dpi = 300

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        extract_cover_from_pdf(pdf_path, output_dir, dpi=custom_dpi)

        mock_convert.assert_called_once_with(str(pdf_path), first_page=1, last_page=1, dpi=custom_dpi)

    @patch("core.utils.pdf.convert_from_path")
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
        mock_image.save.assert_called_once_with(str(expected_cover), "JPEG", quality=custom_quality)

    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_no_images_returned(self, mock_convert, tmp_path):
        """Test handling when pdf2image returns no images."""
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_convert.return_value = []

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_import_error(self, mock_convert, tmp_path):
        """Test handling when pdf2image is not installed."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_convert.side_effect = ImportError("pdf2image not found")

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_conversion_error(self, mock_convert, tmp_path):
        """Test handling when PDF conversion fails."""
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        mock_convert.side_effect = Exception("PDF conversion failed")

        result = extract_cover_from_pdf(pdf_path, output_dir)

        assert result is None

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
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

    @patch("core.utils.pdf.convert_from_path")
    def test_timestamped_filenames_produce_unique_covers(self, mock_convert, tmp_path):
        """Test that files with timestamp suffixes produce unique cover filenames.

        When two files differ only by timestamp (e.g., after deduplication),
        their covers should have different names to avoid overwriting each other.
        """
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        output_dir = tmp_path / "covers"

        # Simulate two files that differ only by timestamp suffix
        pdf_files = [
            pdf_dir / "Magazine - January2024.pdf",
            pdf_dir / "Magazine - January2024 (20260203_151457).pdf",
        ]

        for pdf_path in pdf_files:
            pdf_path.touch()

        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        results = []
        for pdf_path in pdf_files:
            result = extract_cover_from_pdf(pdf_path, output_dir)
            results.append(result)

        assert len(results) == 2
        assert all(r is not None for r in results)
        # Cover filenames must be unique - second should NOT overwrite first
        assert results[0].name != results[1].name
        assert results[0].name == "Magazine - January2024.jpg"
        assert results[1].name == "Magazine - January2024 (20260203_151457).jpg"

    @patch("core.utils.pdf.convert_from_path")
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


class TestLandscapeDetection:
    """Test landscape page detection and cropping functionality"""

    @patch("core.utils.pdf.fitz")
    def test_is_landscape_page_portrait(self, mock_fitz, tmp_path):
        """Test detection of portrait-oriented page."""
        pdf_path = tmp_path / "portrait.pdf"
        pdf_path.touch()

        # Mock PyMuPDF document with portrait page (height > width)
        mock_doc = MagicMock()
        mock_page = Mock()
        mock_rect = Mock()
        mock_rect.width = 612  # 8.5 inches at 72 DPI
        mock_rect.height = 792  # 11 inches at 72 DPI
        mock_page.rect = mock_rect
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz.open.return_value = mock_doc

        is_landscape, aspect_ratio = is_landscape_page(pdf_path, page_number=1)

        assert is_landscape is False
        assert aspect_ratio < 1.0
        mock_doc.close.assert_called_once()

    @patch("core.utils.pdf.fitz")
    def test_is_landscape_page_landscape(self, mock_fitz, tmp_path):
        """Test detection of landscape-oriented page."""
        pdf_path = tmp_path / "landscape.pdf"
        pdf_path.touch()

        # Mock PyMuPDF document with landscape page (width > height)
        mock_doc = MagicMock()
        mock_page = Mock()
        mock_rect = Mock()
        mock_rect.width = 1224  # Two pages side-by-side
        mock_rect.height = 792
        mock_page.rect = mock_rect
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz.open.return_value = mock_doc

        is_landscape, aspect_ratio = is_landscape_page(pdf_path, page_number=1)

        assert is_landscape is True
        assert aspect_ratio > 1.0
        assert abs(aspect_ratio - 1.545) < 0.01  # 1224/792 ≈ 1.545
        mock_doc.close.assert_called_once()

    @patch("core.utils.pdf.fitz")
    def test_is_landscape_page_invalid_page_number(self, mock_fitz, tmp_path):
        """Test handling of invalid page number."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 5
        mock_fitz.open.return_value = mock_doc

        # Test page number too high
        is_landscape, aspect_ratio = is_landscape_page(pdf_path, page_number=10)
        assert is_landscape is False
        assert aspect_ratio == 1.0

        # Test page number 0 (invalid)
        is_landscape, aspect_ratio = is_landscape_page(pdf_path, page_number=0)
        assert is_landscape is False
        assert aspect_ratio == 1.0

    @patch("core.utils.pdf.fitz")
    def test_is_landscape_page_error_handling(self, mock_fitz, tmp_path):
        """Test error handling during page dimension check."""
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.touch()

        mock_fitz.open.side_effect = Exception("Failed to open PDF")

        is_landscape, aspect_ratio = is_landscape_page(pdf_path)
        assert is_landscape is False
        assert aspect_ratio == 1.0

    @patch("core.utils.pdf.is_landscape_page")
    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_crops_landscape(self, mock_convert, mock_is_landscape, tmp_path):
        """Test that landscape pages are cropped to right half."""
        pdf_path = tmp_path / "landscape.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        # Mock landscape detection
        mock_is_landscape.return_value = (True, 2.0)

        # Mock a landscape image (1200x600)
        from PIL import Image

        mock_image = MagicMock(spec=Image.Image)
        mock_image.size = (1200, 600)
        mock_cropped_image = MagicMock(spec=Image.Image)
        mock_image.crop.return_value = mock_cropped_image
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        # Verify landscape detection was called
        mock_is_landscape.assert_called_once_with(pdf_path, 1)

        # Verify image was cropped (right half: from x=600 to x=1200)
        mock_image.crop.assert_called_once_with((600, 0, 1200, 600))

        # Verify cropped image was saved
        mock_cropped_image.save.assert_called_once()
        assert result == output_dir / "landscape.jpg"

    @patch("core.utils.pdf.is_landscape_page")
    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_skips_crop_for_portrait(self, mock_convert, mock_is_landscape, tmp_path):
        """Test that portrait pages are not cropped."""
        pdf_path = tmp_path / "portrait.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"

        # Mock portrait detection
        mock_is_landscape.return_value = (False, 0.77)

        # Mock a portrait image
        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir)

        # Verify landscape detection was called
        mock_is_landscape.assert_called_once_with(pdf_path, 1)

        # Verify image was NOT cropped
        mock_image.crop.assert_not_called()

        # Verify original image was saved
        mock_image.save.assert_called_once()
        assert result == output_dir / "portrait.jpg"

    @patch("core.utils.pdf.is_landscape_page")
    @patch("core.utils.pdf.convert_from_path")
    def test_extract_cover_landscape_with_custom_page(self, mock_convert, mock_is_landscape, tmp_path):
        """Test landscape detection and cropping with custom page number."""
        pdf_path = tmp_path / "multipage.pdf"
        pdf_path.touch()
        output_dir = tmp_path / "covers"
        page_number = 3

        # Mock landscape detection for page 3
        mock_is_landscape.return_value = (True, 1.8)

        # Mock landscape image
        from PIL import Image

        mock_image = MagicMock(spec=Image.Image)
        mock_image.size = (1800, 1000)
        mock_cropped_image = MagicMock(spec=Image.Image)
        mock_image.crop.return_value = mock_cropped_image
        mock_convert.return_value = [mock_image]

        result = extract_cover_from_pdf(pdf_path, output_dir, page_number=page_number)

        # Verify landscape detection was called with correct page number
        mock_is_landscape.assert_called_once_with(pdf_path, page_number)

        # Verify convert_from_path was called with correct page number
        mock_convert.assert_called_once_with(
            str(pdf_path),
            first_page=page_number,
            last_page=page_number,
            dpi=PDF_COVER_DPI_LOW,
        )

        # Verify image was cropped (right half: from x=900 to x=1800)
        mock_image.crop.assert_called_once_with((900, 0, 1800, 1000))

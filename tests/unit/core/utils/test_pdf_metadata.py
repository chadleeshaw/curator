#!/usr/bin/env python3
"""
Tests for PDF metadata embedding functionality.

The embedding writes natural text (e.g., "January 2024\nVolume 5 Issue 12")
into PDF metadata fields, which text_scan then extracts and parses normally.
"""
# pylint: disable=import-error
# pypdf is an optional dependency - tests are skipped when not available

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Path setup handled by conftest.py

from core.utils.pdf_metadata import (
    embed_metadata_in_pdf,
    _build_natural_metadata_text,
    PYPDF_AVAILABLE,
)


class TestBuildNaturalMetadataText:
    """Test building natural text from metadata."""

    def test_build_full_metadata(self):
        """Test building text with all fields."""
        metadata = {"year": 2024, "month": 3, "volume": 5, "issue_number": 12}
        result = _build_natural_metadata_text(metadata, title="Test Magazine")

        assert "Test Magazine" in result
        assert "March" in result
        assert "2024" in result
        assert "Volume 5" in result
        assert "Issue 12" in result

    def test_build_year_only(self):
        """Test with just year."""
        metadata = {"year": 2024}
        result = _build_natural_metadata_text(metadata)

        assert "2024" in result
        assert "Volume" not in result

    def test_build_year_and_month(self):
        """Test with year and month."""
        metadata = {"year": 2024, "month": 6}
        result = _build_natural_metadata_text(metadata)

        assert "June 2024" in result

    def test_build_volume_and_issue(self):
        """Test with volume and issue number."""
        metadata = {"volume": 10, "issue_number": 42}
        result = _build_natural_metadata_text(metadata)

        assert "Volume 10" in result
        assert "Issue 42" in result


class TestPdfMetadataEmbedding:
    """Test PDF metadata embedding functionality."""

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf not available")
    def test_embed_metadata_creates_natural_text(self, tmp_path):
        """Test that embedding metadata creates natural text in Subject field."""
        pdf_path = tmp_path / "test.pdf"
        self._create_minimal_pdf(pdf_path)

        metadata = {"year": 2024, "month": 3, "volume": 5, "issue_number": 12}

        result = embed_metadata_in_pdf(str(pdf_path), metadata, title="Test Magazine")

        assert result is True
        assert pdf_path.exists()

        # Verify the PDF has natural text in metadata
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        subject = reader.metadata.get("/Subject", "")

        assert "March" in subject
        assert "2024" in subject
        assert "Volume 5" in subject
        assert "Issue 12" in subject

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf not available")
    def test_embed_metadata_partial_data(self, tmp_path):
        """Test embedding with only year and month."""
        pdf_path = tmp_path / "test.pdf"
        self._create_minimal_pdf(pdf_path)

        metadata = {"year": 2023, "month": 6}

        result = embed_metadata_in_pdf(str(pdf_path), metadata)

        assert result is True

        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        subject = reader.metadata.get("/Subject", "")

        assert "June 2023" in subject

    def test_embed_fails_for_nonexistent_file(self):
        """Test that embedding fails gracefully for non-existent files."""
        result = embed_metadata_in_pdf("/nonexistent/path.pdf", {"year": 2024})
        assert result is False

    def test_embed_skips_non_pdf_files(self, tmp_path):
        """Test that non-PDF files are skipped."""
        epub_path = tmp_path / "test.epub"
        epub_path.touch()

        result = embed_metadata_in_pdf(str(epub_path), {"year": 2024})
        assert result is False

    def test_embed_fails_with_empty_metadata(self, tmp_path):
        """Test that embedding fails when there's no metadata to embed."""
        pdf_path = tmp_path / "test.pdf"
        self._create_minimal_pdf(pdf_path)

        result = embed_metadata_in_pdf(str(pdf_path), {})
        assert result is False

    def _create_minimal_pdf(self, path: Path):
        """Create a minimal valid PDF for testing."""
        if PYPDF_AVAILABLE:
            from pypdf import PdfWriter

            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)  # Letter size
            with open(path, "wb") as f:
                writer.write(f)
        else:
            # Fallback: create invalid but parseable header
            path.write_bytes(b"%PDF-1.4\n%%EOF")


class TestTextScanWithEmbeddedMetadata:
    """Test that TextScanService picks up embedded metadata via normal text extraction."""

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf not available")
    def test_text_scan_finds_embedded_metadata(self, tmp_path):
        """TextScanService should find embedded metadata in PDF metadata fields."""
        from services.text_scan_service import TextScanService

        # Create PDF with embedded natural text metadata
        pdf_path = tmp_path / "test.pdf"
        self._create_pdf_with_embedded_metadata(pdf_path)

        result = TextScanService.scan_document(str(pdf_path))

        assert result["scanned"] is True
        assert result["text_found"] is True
        assert result["year"] == 2024
        assert result["month"] == "June"  # TextScanService returns month as string
        assert result["has_sufficient_metadata"] is True

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf not available")
    def test_text_scan_extracts_volume_and_issue(self, tmp_path):
        """TextScanService should extract volume and issue from embedded metadata."""
        from services.text_scan_service import TextScanService

        pdf_path = tmp_path / "test.pdf"
        self._create_pdf_with_volume_issue(pdf_path)

        result = TextScanService.scan_document(str(pdf_path))

        assert result["scanned"] is True
        assert result.get("volume") == 10
        assert result.get("issue_number") == 42

    def _create_pdf_with_embedded_metadata(self, path: Path):
        """Create a PDF with natural text metadata in Subject field."""
        if PYPDF_AVAILABLE:
            from pypdf import PdfWriter

            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_metadata(
                {
                    "/Subject": "June 2024",
                    "/Keywords": "June 2024",
                }
            )
            with open(path, "wb") as f:
                writer.write(f)

    def _create_pdf_with_volume_issue(self, path: Path):
        """Create a PDF with volume/issue in metadata."""
        if PYPDF_AVAILABLE:
            from pypdf import PdfWriter

            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_metadata(
                {
                    "/Subject": "Volume 10 Issue 42",
                }
            )
            with open(path, "wb") as f:
                writer.write(f)

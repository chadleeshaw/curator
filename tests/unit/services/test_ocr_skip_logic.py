#!/usr/bin/env python3
"""
Test suite for OCR skip logic when text scan finds sufficient metadata.

Tests verify that OCR is skipped when text-based PDFs (True PDF, Text PDF)
have already been successfully scanned for text metadata.
"""

import pytest
from unittest.mock import MagicMock, patch

# Path setup handled by conftest.py

from services.auto_metadata import AutoMetadataService


class TestOCRSkipWhenTextScanSufficient:
    """Test that OCR is skipped when text scan finds sufficient metadata"""

    def _create_mock_periodical(self, parsed_metadata=None, extra_metadata=None):
        """Create a mock periodical with specified metadata."""
        periodical = MagicMock()
        periodical.id = 1
        periodical.parsed_metadata = parsed_metadata
        periodical.extra_metadata = extra_metadata
        periodical.cover_path = "/path/to/cover.png"
        periodical.file_path = "/path/to/file.pdf"
        return periodical

    def _create_mock_session(self, has_existing_job=False):
        """Create a mock database session."""
        session = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()

        if has_existing_job:
            filter_mock.first.return_value = MagicMock()  # Existing job
        else:
            filter_mock.first.return_value = None  # No existing job

        query_mock.filter.return_value = filter_mock
        session.query.return_value = query_mock
        return session

    def test_skip_ocr_when_text_scan_has_year(self):
        """OCR should be skipped if text scan found a year."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={"text_scan": {"year": 2024, "has_sufficient_metadata": True}}
        )
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

    def test_skip_ocr_when_text_scan_has_month(self):
        """OCR should be skipped if text scan found a month."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={"text_scan": {"month": 6, "has_sufficient_metadata": True}}
        )
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

    def test_skip_ocr_when_text_scan_has_volume(self):
        """OCR should be skipped if text scan found a volume."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={"text_scan": {"volume": 42, "has_sufficient_metadata": True}}
        )
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

    def test_queue_ocr_when_text_scan_insufficient(self):
        """OCR should be queued if text scan didn't find sufficient metadata."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={"text_scan": {"scanned": True, "text_found": False, "has_sufficient_metadata": False}}
        )
        session = self._create_mock_session(has_existing_job=False)

        result = service._should_queue_ocr(periodical, session)

        assert result is True

    def test_queue_ocr_when_no_text_scan(self):
        """OCR should be queued if no text scan exists."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(parsed_metadata={"file_scan": {"title": "Test Magazine"}})
        session = self._create_mock_session(has_existing_job=False)

        result = service._should_queue_ocr(periodical, session)

        assert result is True

    def test_queue_ocr_when_no_parsed_metadata(self):
        """OCR should be queued if no parsed_metadata at all."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(parsed_metadata=None)
        session = self._create_mock_session(has_existing_job=False)

        result = service._should_queue_ocr(periodical, session)

        assert result is True

    def test_skip_ocr_when_already_has_ocr_scan(self):
        """OCR should be skipped if OCR scan already exists."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(parsed_metadata={"ocr_scan": {"year": 2024, "month": 3}})
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

    def test_skip_ocr_when_no_cover_path(self):
        """OCR should be skipped if periodical has no cover."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(parsed_metadata={})
        periodical.cover_path = None  # No cover
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

    def test_skip_ocr_for_non_pdf_files(self):
        """OCR should be skipped for non-PDF files (EPUB, CBZ, etc.)."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(parsed_metadata={})
        periodical.file_path = "/path/to/file.epub"  # EPUB, not PDF
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False


class TestOCRQueueNeedsDateScan:
    """Test OCR queueing behavior for periodicals flagged with needs_date_scan."""

    def _create_mock_periodical(self, parsed_metadata=None, extra_metadata=None):
        """Create a mock periodical with specified metadata."""
        periodical = MagicMock()
        periodical.id = 1
        periodical.parsed_metadata = parsed_metadata
        periodical.extra_metadata = extra_metadata
        periodical.cover_path = "/path/to/cover.png"
        periodical.file_path = "/path/to/file.pdf"
        return periodical

    def _create_mock_session(self, has_existing_job=False):
        """Create a mock database session."""
        session = MagicMock()
        query_mock = MagicMock()
        filter_mock = MagicMock()

        if has_existing_job:
            filter_mock.first.return_value = MagicMock()
        else:
            filter_mock.first.return_value = None

        query_mock.filter.return_value = filter_mock
        session.query.return_value = query_mock
        return session

    def test_queue_ocr_when_needs_date_scan_and_text_scan_has_no_year(self):
        """OCR should be queued when needs_date_scan is True and text scan didn't find year."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={"text_scan": {"scanned": True, "has_sufficient_metadata": True}},  # No year
            extra_metadata={"needs_date_scan": True},
        )
        session = self._create_mock_session(has_existing_job=False)

        result = service._should_queue_ocr(periodical, session)

        assert result is True

    def test_skip_ocr_when_needs_date_scan_but_text_scan_has_year(self):
        """OCR should be skipped when needs_date_scan but text scan already found year."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={"text_scan": {"year": 2024, "has_sufficient_metadata": True}},
            extra_metadata={"needs_date_scan": True},
        )
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

    def test_queue_ocr_when_needs_date_scan_and_no_cover_path(self):
        """OCR should still be queued for needs_date_scan even without cover path."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={},
            extra_metadata={"needs_date_scan": True},
        )
        periodical.cover_path = None  # No cover, but needs_date_scan is True
        session = self._create_mock_session(has_existing_job=False)

        result = service._should_queue_ocr(periodical, session)

        assert result is True

    def test_skip_ocr_when_no_needs_date_scan_and_no_cover_path(self):
        """OCR should be skipped when no cover path and no needs_date_scan flag."""
        service = AutoMetadataService.__new__(AutoMetadataService)

        periodical = self._create_mock_periodical(
            parsed_metadata={},
            extra_metadata={"needs_date_scan": False},
        )
        periodical.cover_path = None
        session = self._create_mock_session()

        result = service._should_queue_ocr(periodical, session)

        assert result is False

"""Import results for files the downloads scanner actually sees.

Text extraction and cover rendering are stubbed. The assertions follow the
parser output that FileImporter writes, including the precision and day
rewrites the current code produces.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from core.constants.errors import ErrorCodes
from core.parsers import Parser
from models.database import Periodical, PeriodicalTracking
from services.importer.importer import FileImporter

EMPTY_SCAN = {"text_found": False, "has_sufficient_metadata": False}


@pytest.fixture
def session(test_db):
    _, session_factory = test_db
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def quiet_scans():
    """Keep OCR, text extraction, and cover rendering out of the import."""
    with (
        patch("services.importer.importer.TextScanService.scan_document", return_value=dict(EMPTY_SCAN)),
        patch("services.importer.importer.OCRService.is_available", return_value=False),
        patch("services.importer.importer.OCRService.analyze_cover", return_value=None),
        patch("services.importer.importer.extract_cover_from_pdf", return_value=None),
    ):
        yield


def _pdf(path: Path, text: str = "issue") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    return path


def _importer(downloads: Path, library: Path, *, text_scan: bool = False) -> FileImporter:
    return FileImporter(
        str(downloads),
        str(library),
        enable_text_scan=text_scan,
        parallel_workers=1,
    )


def _stored_day(value: datetime) -> tuple:
    return (value.year, value.month, value.day)


class TestAParsedFileLandsInTheLibrary:
    def test_title_date_and_precision_match_the_parser(self, tmp_path, session, quiet_scans):
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        pdf = _pdf(downloads / "City.Paper.2024-01-14.pdf", text="City Paper 14 January 2024")
        parsed = Parser().parse_file(pdf)
        importer = _importer(downloads, library, text_scan=False)

        result = importer.process_downloads(session)

        row = session.query(Periodical).one()
        assert result["success"] is True
        assert result["data"] == {"imported": 1, "failed": 0, "skipped": 0}
        assert row.title == parsed.title == "City Paper"
        assert _stored_day(row.issue_date) == _stored_day(parsed.issue_date) == (2024, 1, 14)
        assert row.date_precision == parsed.raw_metadata["date_precision"] == "day"
        assert row.language == "English"
        assert Path(row.file_path).is_file()
        assert Path(row.file_path).is_relative_to(library)
        assert not pdf.exists()
        assert row.content_hash

    def test_a_named_month_without_dots_is_month_precision(self, tmp_path, session, quiet_scans):
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        pdf = _pdf(downloads / "Wired January 2024.pdf")
        parsed = Parser().parse_file(pdf)
        importer = _importer(downloads, library, text_scan=False)

        result = importer.process_downloads(session)

        row = session.query(Periodical).one()
        assert result["data"]["imported"] == 1
        assert parsed.matched_pattern == "space_month_year"
        assert parsed.month == 1
        assert parsed.raw_metadata.get("date_precision") == "month"
        assert row.title == "Wired"
        assert _stored_day(row.issue_date) == (2024, 1, 1)
        assert row.date_precision == "month"

    def test_an_empty_text_scan_moves_a_known_day_to_the_first(self, tmp_path, session, quiet_scans):
        """sync_issue_date_from_derived always returns a datetime, so the scan flags a rewrite.

        The column keeps day precision while the stored day becomes the 1st.
        """
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        _pdf(downloads / "City.Paper.2024-01-14.pdf")
        importer = _importer(downloads, library, text_scan=True)

        result = importer.process_downloads(session)

        row = session.query(Periodical).one()
        assert result["data"] == {"imported": 1, "failed": 0, "skipped": 0}
        assert row.date_precision == "day"
        assert _stored_day(row.issue_date) == (2024, 1, 1)
        assert row.extra_metadata["needs_reorganization"] is True
        assert row.extra_metadata["reorganization_reason"] == "metadata_discovered_by_text_scan"
        assert row.parsed_metadata["text_scan"]["text_found"] is False


class TestDuplicatesAndRejectedFiles:
    def test_the_same_bytes_are_skipped_and_blacklisted_files_stay_put(self, tmp_path, session, quiet_scans):
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        original = _pdf(downloads / "National.Geographic.January.2024.pdf", text="january")
        duplicate = downloads / "National.Geographic.January.2024.copy.pdf"
        duplicate.write_bytes(original.read_bytes())
        video = downloads / "episode.mp4"
        video.write_bytes(b"video")
        program = downloads / "setup.exe"
        program.write_bytes(b"MZ")
        importer = _importer(downloads, library, text_scan=False)

        result = importer.process_downloads(session)

        row = session.query(Periodical).one()
        assert result["success"] is True
        assert result["data"] == {"imported": 1, "failed": 0, "skipped": 1}
        assert row.title == "National Geographic"
        assert row.date_precision == "month"
        assert _stored_day(row.issue_date) == (2024, 1, 1)
        assert not original.exists()
        assert not duplicate.exists()
        assert video.is_file()
        assert program.is_file()
        assert list(library.rglob("*.mp4")) == []
        assert list(library.rglob("*.exe")) == []

    def test_the_same_title_and_date_without_a_content_hash_is_skipped(self, tmp_path, session, quiet_scans):
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        library.mkdir()
        owned = Periodical(
            user_id=1,
            title="City Paper",
            issue_date=datetime(2024, 1, 14, tzinfo=timezone.utc),
            language="English",
            file_path=str(library / "already.pdf"),
            content_hash=None,
        )
        session.add(owned)
        session.commit()
        pdf = _pdf(downloads / "City.Paper.2024-01-14.pdf", text="a different scan")
        importer = _importer(downloads, library, text_scan=False)

        outcome = importer.import_supported_files(pdf, session)

        assert outcome["skip_reason"] == "duplicate_fuzzy"
        assert "periodical_id" not in outcome
        assert session.query(Periodical).count() == 1
        assert not pdf.exists()


class TestMissingFilesFailCleanly:
    def test_a_missing_file_returns_parse_error_and_adds_no_row(self, tmp_path, session, quiet_scans):
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        downloads.mkdir()
        importer = _importer(downloads, library, text_scan=False)
        missing = downloads / "City.Paper.2024-01-14.pdf"

        outcome = importer.import_supported_files(missing, session)

        assert outcome == {"skip_reason": "parse_error"}
        assert session.query(Periodical).count() == 0
        assert session.query(PeriodicalTracking).count() == 0

    def test_a_missing_downloads_directory_is_a_not_found_result(self, tmp_path, session, quiet_scans):
        missing = tmp_path / "does-not-exist"
        importer = _importer(missing, tmp_path / "library", text_scan=False)

        result = importer.process_downloads(session)

        assert result["success"] is False
        assert result["data"] == {"imported": 0, "failed": 0, "skipped": 0}
        assert result["errors"] == [
            {
                "code": ErrorCodes.FILE_NOT_FOUND,
                "message": f"Downloads directory not found: {missing}",
                "retryable": False,
            }
        ]
        assert session.query(Periodical).count() == 0


class TestPathCountryDetection:
    def test_a_tmp_directory_is_stored_as_turkmenistan(self, tmp_path, session, quiet_scans):
        """detect_country treats the /tmp/ path segment as the TM country code."""
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        pdf = _pdf(downloads / "City.Paper.2024-01-14.pdf")
        assert "/tmp/" in str(pdf)
        importer = _importer(downloads, library, text_scan=False)

        importer.process_downloads(session)

        row = session.query(Periodical).one()
        tracking = session.query(PeriodicalTracking).one()
        assert row.parsed_metadata["file_scan"]["country"] == "TM"
        assert tracking.country == "TM"
        assert tracking.title == "City Paper"

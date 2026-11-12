"""Behavior tests for the auto-metadata full scan.

Exercises path repair, derived-metadata backfill, issue-date sync, OCR and text
scan decisions, and extra-metadata cleanup through AutoMetadataService.run_full_scan.
Text extraction is mocked so the tests assert the queue decision and the metadata
that the scan writes.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from models.database import OCRJob, Periodical
from services.auto_metadata import AutoMetadataService


def _write(path: Path, content: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _add_periodical(session, file_path, **overrides) -> Periodical:
    values = {
        "user_id": 1,
        "title": "Wired",
        "issue_date": datetime(2020, 6, 15, tzinfo=UTC),
        "file_path": str(file_path),
        "category": "Magazines",
        "language": "English",
    }
    values.update(overrides)
    row = Periodical(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@pytest.fixture
def session(test_db):
    _engine, session_factory = test_db
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _service(library: Path | None) -> AutoMetadataService:
    return AutoMetadataService(
        db_manager=object(),
        library_base_dir=str(library) if library is not None else None,
    )


def _run(service, session, text_result=None):
    payload = {"scanned": False} if text_result is None else text_result
    with patch("services.auto_metadata.TextScanService.scan_document", return_value=payload) as text_scan:
        stats = service.run_full_scan(session)
    session.expire_all()
    return stats, text_scan


class TestAutoMetadataScan:
    """Full scans update rows, queue jobs, and leave the original files in place."""

    def test_fixes_a_docker_path_and_backfills_issue_date_from_the_resolved_file(self, tmp_path, session):
        library = tmp_path / "library"
        resolved = _write(library / "_Magazines" / "Inbox" / "Wired - December2024.pdf")
        _write(library / "other" / "Wired - December2024.pdf", "decoy")
        stored = "/app/local/data/_Magazines/Inbox/Wired - December2024.pdf"
        periodical = _add_periodical(session, stored, issue_date=datetime(2011, 1, 2, tzinfo=UTC))

        stats, text_scan = _run(_service(library), session)
        session.refresh(periodical)

        assert stats["total_periodicals"] == 1
        assert stats["paths_fixed"] == 1
        assert stats["derived_metadata_backfilled"] == 1
        assert stats["issue_date_synced"] == 1
        assert stats["metadata_cleaned"] == 0
        assert stats["ocr_queued"] == 0
        assert stats["text_scan_queued"] == 0
        assert stats["errors"] == 0
        assert periodical.file_path == str(resolved)
        assert resolved.read_text() == "data"
        assert periodical.issue_date.year == 2024
        assert periodical.issue_date.month == 12
        assert periodical.issue_date.day == 1
        assert periodical.parsed_metadata["file_scan"]["year"] == 2024
        assert periodical.parsed_metadata["file_scan"]["month"] == 12
        assert periodical.derived_metadata["year"]["value"] == 2024
        assert periodical.derived_metadata["year"]["source"] == "file_scan"
        assert periodical.derived_metadata["month"]["value"] == 12
        assert periodical.derived_metadata["title"]["value"] == "Wired"
        assert text_scan.call_count == 1
        assert session.query(OCRJob).count() == 0

    def test_fixes_a_path_by_filename_when_no_category_marker_matches(self, tmp_path, session):
        library = tmp_path / "library"
        resolved = _write(library / "loose" / "Wired - December2024.pdf", "loose")
        stored = "/var/lib/docker/lost/Wired - December2024.pdf"
        periodical = _add_periodical(session, stored)

        stats, _text_scan = _run(_service(library), session)
        session.refresh(periodical)

        assert stats["paths_fixed"] == 1
        assert periodical.file_path == str(resolved)
        assert resolved.read_text() == "loose"
        assert periodical.derived_metadata["year"]["value"] == 2024
        assert periodical.issue_date.month == 12

    def test_existing_path_is_not_rewritten(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Wired" / "2024" / "Wired - December2024.pdf", "here")
        _write(library / "other" / "Wired - December2024.pdf", "decoy")
        periodical = _add_periodical(session, current, issue_date=datetime(2024, 12, 1, tzinfo=UTC))

        stats, _text_scan = _run(_service(library), session)
        session.refresh(periodical)

        assert stats["paths_fixed"] == 0
        assert stats["issue_date_synced"] == 0
        assert stats["derived_metadata_backfilled"] == 1
        assert periodical.file_path == str(current)
        assert current.read_text() == "here"
        assert (library / "other" / "Wired - December2024.pdf").read_text() == "decoy"
        assert periodical.issue_date.year == 2024
        assert periodical.issue_date.month == 12
        assert periodical.issue_date.day == 1

    def test_without_a_library_directory_a_stored_scan_still_syncs_the_issue_date(self, session):
        stored = "/missing/_Magazines/Wired - December2024.pdf"
        periodical = _add_periodical(
            session,
            stored,
            parsed_metadata={"file_scan": {"year": 2018, "month": 3, "confidence": "high", "title": "Wired"}},
        )

        stats, text_scan = _run(_service(None), session)
        session.refresh(periodical)

        assert stats["paths_fixed"] == 0
        assert stats["derived_metadata_backfilled"] == 1
        assert stats["issue_date_synced"] == 1
        assert stats["text_scan_queued"] == 0
        assert text_scan.call_count == 0
        assert periodical.file_path == stored
        assert periodical.derived_metadata["year"]["value"] == 2018
        assert periodical.derived_metadata["year"]["confidence"] == 0.85
        assert periodical.derived_metadata["month"]["value"] == 3
        assert periodical.issue_date.year == 2018
        assert periodical.issue_date.month == 3

    def test_original_filename_supplements_volume_and_timestamp_date_is_synced(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Wired (20260205_235255).pdf", "renamed")
        periodical = _add_periodical(
            session,
            current,
            extra_metadata={"imported_from": "354 - Magazine354 - Vol.354.pdf"},
        )

        stats, _text_scan = _run(_service(library), session)
        session.refresh(periodical)

        file_scan = periodical.parsed_metadata["file_scan"]
        assert stats["derived_metadata_backfilled"] == 1
        assert stats["issue_date_synced"] == 1
        assert file_scan["volume"] == 354
        assert file_scan["issue_number"] == 354
        assert file_scan["year"] == 2026
        assert file_scan["month"] == 2
        assert file_scan["year_confidence"] == 0.10
        assert periodical.derived_metadata["volume"]["value"] == 354
        assert periodical.derived_metadata["volume"]["source"] == "file_scan"
        assert periodical.derived_metadata["issue_number"]["value"] == 354
        assert periodical.derived_metadata["year"]["value"] == 2026
        assert periodical.issue_date.year == 2026
        assert periodical.issue_date.month == 2
        assert current.read_text() == "renamed"

    def test_text_scan_metadata_overrides_the_filename_date(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Wired - December2024.pdf")
        periodical = _add_periodical(session, current)
        text_result = {
            "scanned": True,
            "text_found": True,
            "year": 2014,
            "month": 8,
            "confidence": 0.9,
            "has_sufficient_metadata": True,
        }

        stats, text_scan = _run(_service(library), session, text_result)
        session.refresh(periodical)

        assert stats["issue_date_synced"] == 1
        assert stats["text_scan_queued"] == 1
        assert stats["ocr_queued"] == 0
        assert text_scan.call_count == 1
        assert periodical.parsed_metadata["text_scan"]["year"] == 2014
        assert periodical.derived_metadata["year"]["value"] == 2014
        assert periodical.derived_metadata["year"]["source"] == "text_scan"
        assert periodical.derived_metadata["month"]["value"] == 8
        assert periodical.issue_date.year == 2014
        assert periodical.issue_date.month == 8
        assert session.query(OCRJob).count() == 0

    def test_cleanup_moves_scans_out_of_extra_metadata_and_ocr_wins_the_date(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Wired - December2024.pdf", "filed")
        text_scan = {
            "year": 2019,
            "month": 7,
            "confidence": 0.8,
            "scanned": True,
            "has_sufficient_metadata": True,
        }
        ocr_scan = {"year": 2021, "month": 5, "confidence": 0.95}
        periodical = _add_periodical(
            session,
            current,
            issue_date=datetime(2000, 1, 1, tzinfo=UTC),
            extra_metadata={
                "imported_from": "original-download.pdf",
                "import_method": "auto",
                "needs_date_scan": True,
                "year": 1999,
                "month": 1,
                "country": "US",
                "language": "French",
                "volume": 1,
                "issue_number": 2,
                "confidence": 0.1,
                "parse_source": "old",
                "special_edition": True,
                "full_title": "Old Title",
                "text_scan": text_scan,
                "ocr_metadata": ocr_scan,
            },
            cover_path=str(library / "cover.jpg"),
        )

        stats, scanner = _run(_service(library), session)
        session.refresh(periodical)

        assert stats["metadata_cleaned"] == 1
        assert stats["paths_fixed"] == 0
        assert stats["derived_metadata_backfilled"] == 1
        assert stats["issue_date_synced"] == 1
        assert stats["ocr_queued"] == 0
        assert stats["text_scan_queued"] == 0
        assert scanner.call_count == 0
        assert periodical.extra_metadata == {
            "imported_from": "original-download.pdf",
            "import_method": "auto",
            "needs_date_scan": True,
        }
        assert periodical.parsed_metadata["text_scan"]["year"] == 2019
        assert periodical.parsed_metadata["ocr_scan"] == ocr_scan
        assert "ocr_metadata" not in periodical.parsed_metadata
        assert periodical.derived_metadata["year"]["value"] == 2021
        assert periodical.derived_metadata["year"]["source"] == "ocr_scan"
        assert periodical.derived_metadata["month"]["value"] == 5
        assert periodical.issue_date.year == 2021
        assert periodical.issue_date.month == 5
        assert current.read_text() == "filed"
        assert session.query(OCRJob).count() == 0

    def test_queue_decisions_follow_extension_cover_and_existing_scans(self, tmp_path, session):
        library = tmp_path / "library"
        new_pdf = _write(library / "_Magazines" / "Wired - June2022.pdf", "new")
        scanned_pdf = _write(library / "_Magazines" / "Atlas - June2022.pdf", "scanned")
        epub = _write(library / "_Magazines" / "Novel - March2018.epub", "epub")
        cbz = _write(library / "_Magazines" / "Comic - January2020.cbz", "cbz")
        cover = str(library / "cover.jpg")
        new_row = _add_periodical(session, new_pdf, title="Wired", cover_path=cover)
        scanned_row = _add_periodical(
            session,
            scanned_pdf,
            title="Atlas",
            cover_path=cover,
            parsed_metadata={
                "text_scan": {
                    "year": 2016,
                    "month": 4,
                    "confidence": 0.9,
                    "scanned": True,
                    "has_sufficient_metadata": True,
                }
            },
        )
        epub_row = _add_periodical(session, epub, title="Novel", cover_path=cover)
        cbz_row = _add_periodical(session, cbz, title="Comic", cover_path=cover)
        text_result = {
            "scanned": True,
            "text_found": True,
            "year": 2017,
            "month": 9,
            "confidence": 0.88,
            "has_sufficient_metadata": True,
        }

        stats, text_scan = _run(_service(library), session, text_result)
        for row in (new_row, scanned_row, epub_row, cbz_row):
            session.refresh(row)
        jobs = session.query(OCRJob).all()

        assert stats["total_periodicals"] == 4
        assert stats["ocr_queued"] == 1
        assert stats["text_scan_queued"] == 2
        assert stats["errors"] == 0
        assert stats["derived_metadata_backfilled"] == 4
        assert sorted(Path(call.args[0]).name for call in text_scan.call_args_list) == [
            "Novel - March2018.epub",
            "Wired - June2022.pdf",
        ]
        assert len(jobs) == 1
        assert jobs[0].periodical_id == new_row.id
        assert jobs[0].status == OCRJob.StatusEnum.PENDING
        assert new_row.parsed_metadata["text_scan"]["year"] == 2017
        assert new_row.issue_date.year == 2017
        assert new_row.issue_date.month == 9
        assert epub_row.parsed_metadata["text_scan"]["month"] == 9
        assert epub_row.issue_date == new_row.issue_date
        assert scanned_row.parsed_metadata["text_scan"]["year"] == 2016
        assert scanned_row.issue_date.year == 2016
        assert scanned_row.issue_date.month == 4
        assert "text_scan" not in (cbz_row.parsed_metadata or {})
        assert cbz_row.derived_metadata["year"]["value"] == 2020
        assert cbz_row.derived_metadata["year"]["source"] == "file_scan"
        assert cbz_row.issue_date.year == 2020
        assert cbz_row.issue_date.month == 1
        assert session.query(OCRJob).filter(OCRJob.periodical_id == epub_row.id).count() == 0
        assert session.query(OCRJob).filter(OCRJob.periodical_id == cbz_row.id).count() == 0
        assert session.query(OCRJob).filter(OCRJob.periodical_id == scanned_row.id).count() == 0

    def test_missing_pdf_is_queued_for_ocr_and_skipped_for_text_scan(self, tmp_path, session):
        library = tmp_path / "library"
        library.mkdir()
        missing = "/missing/_Magazines/Inbox/Wired - December2024.pdf"
        periodical = _add_periodical(session, missing, cover_path=str(library / "cover.jpg"))

        stats, text_scan = _run(_service(library), session)
        session.refresh(periodical)
        jobs = session.query(OCRJob).all()

        assert stats["paths_fixed"] == 0
        assert stats["ocr_queued"] == 1
        assert stats["text_scan_queued"] == 0
        assert stats["derived_metadata_backfilled"] == 0
        assert text_scan.call_count == 0
        assert periodical.file_path == missing
        assert periodical.parsed_metadata is None
        assert len(jobs) == 1
        assert jobs[0].periodical_id == periodical.id
        assert jobs[0].status == OCRJob.StatusEnum.PENDING

    def test_needs_date_scan_queues_ocr_without_a_cover_when_text_has_no_year(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Science Vol.385.pdf", "vol")
        periodical = _add_periodical(
            session,
            current,
            cover_path=None,
            parsed_metadata={
                "text_scan": {"volume": 4, "scanned": True, "has_sufficient_metadata": True, "confidence": 0.8}
            },
            extra_metadata={"needs_date_scan": True},
        )

        stats, text_scan = _run(_service(library), session)
        session.refresh(periodical)

        assert stats["ocr_queued"] == 1
        assert stats["text_scan_queued"] == 0
        assert text_scan.call_count == 0
        assert session.query(OCRJob).filter(OCRJob.periodical_id == periodical.id).count() == 1
        assert periodical.extra_metadata["needs_date_scan"] is True
        assert periodical.parsed_metadata["text_scan"]["volume"] == 4

    def test_pending_job_blocks_a_new_ocr_job_and_a_completed_job_does_not(self, tmp_path, session):
        library = tmp_path / "library"
        pending_file = _write(library / "_Magazines" / "Pending - June2022.pdf")
        done_file = _write(library / "_Magazines" / "Done - June2022.pdf")
        cover = str(library / "cover.jpg")
        pending_row = _add_periodical(session, pending_file, title="Pending", cover_path=cover)
        done_row = _add_periodical(session, done_file, title="Done", cover_path=cover)
        session.add(OCRJob(periodical_id=pending_row.id, status=OCRJob.StatusEnum.PENDING))
        session.add(OCRJob(periodical_id=done_row.id, status=OCRJob.StatusEnum.COMPLETED))
        session.commit()

        stats, _text_scan = _run(
            _service(library),
            session,
            {"scanned": True, "text_found": False, "has_sufficient_metadata": False},
        )

        pending_jobs = (
            session.query(OCRJob)
            .filter(OCRJob.periodical_id == pending_row.id, OCRJob.status == OCRJob.StatusEnum.PENDING)
            .count()
        )
        done_pending = (
            session.query(OCRJob)
            .filter(OCRJob.periodical_id == done_row.id, OCRJob.status == OCRJob.StatusEnum.PENDING)
            .count()
        )
        assert stats["ocr_queued"] == 1
        assert pending_jobs == 1
        assert done_pending == 1
        assert session.query(OCRJob).filter(OCRJob.periodical_id == done_row.id).count() == 2

    def test_pdf_without_a_cover_gets_a_text_scan_and_no_ocr_job(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Wired - December2024.pdf")
        periodical = _add_periodical(session, current, cover_path=None)

        stats, text_scan = _run(
            _service(library),
            session,
            {"scanned": True, "year": 2024, "month": 12, "confidence": 0.8, "has_sufficient_metadata": True},
        )
        session.refresh(periodical)

        assert stats["ocr_queued"] == 0
        assert stats["text_scan_queued"] == 1
        assert text_scan.call_count == 1
        assert session.query(OCRJob).count() == 0
        assert periodical.parsed_metadata["text_scan"]["month"] == 12

    def test_unscanned_text_result_does_not_count_as_queued_metadata(self, tmp_path, session):
        library = tmp_path / "library"
        current = _write(library / "_Magazines" / "Wired - December2024.pdf")
        periodical = _add_periodical(session, current, cover_path=None)

        stats, text_scan = _run(_service(library), session, {"scanned": False})
        session.refresh(periodical)

        assert stats["text_scan_queued"] == 0
        assert stats["issue_date_synced"] == 1
        assert text_scan.call_count == 1
        assert "text_scan" not in (periodical.parsed_metadata or {})
        assert periodical.issue_date.year == 2024
        assert periodical.issue_date.month == 12
        assert periodical.derived_metadata["year"]["source"] == "file_scan"

    def test_one_periodical_error_does_not_roll_back_a_successful_sibling(self, tmp_path, session):
        library = tmp_path / "library"
        good_file = _write(library / "_Magazines" / "Wired - December2024.pdf", "good")
        good = _add_periodical(session, good_file, issue_date=datetime(2010, 1, 1, tzinfo=UTC))
        bad_path = "/missing/_Magazines/Nope/nope.pdf"
        bad = _add_periodical(session, bad_path, title="Broken")

        with patch(
            "services.auto_metadata.resolve_periodical_file_path",
            side_effect=RuntimeError("resolver blew up"),
        ):
            stats, _text_scan = _run(_service(library), session)
        session.refresh(good)
        session.refresh(bad)

        assert stats["total_periodicals"] == 2
        assert stats["errors"] == 1
        assert stats["paths_fixed"] == 0
        assert stats["issue_date_synced"] == 1
        assert good.file_path == str(good_file)
        assert good.issue_date.year == 2024
        assert good.issue_date.month == 12
        assert good.derived_metadata["title"]["value"] == "Wired"
        assert bad.file_path == bad_path
        assert bad.derived_metadata is None
        assert bad.issue_date.year == 2020
        assert good_file.read_text() == "good"

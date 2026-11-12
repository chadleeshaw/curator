"""Behavior tests for file reorganization and empty-directory cleanup.

Covers services.file_organizer.reorganization and services.file_organizer.cleanup
through FileOrganizer, which mixes both in. Assertions check paths, flags, and
counts on the filesystem and in the database.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from models.database import Periodical, PeriodicalTracking
from services.file_organizer import FileOrganizer


def _write(path: Path, content: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _sidecar_path(file_path: Path) -> Path:
    return file_path.with_suffix(file_path.suffix + ".curator_meta.json")


def _write_sidecar(file_path: Path, tracking_title: str, **extra) -> Path:
    payload = {"tracking_id": 1, "tracking_title": tracking_title, **extra}
    sidecar = _sidecar_path(file_path)
    sidecar.write_text(json.dumps(payload))
    return sidecar


def _add_periodical(session, file_path, **overrides) -> Periodical:
    values = {
        "user_id": 1,
        "title": "Wired",
        "issue_date": datetime(2024, 12, 1, tzinfo=UTC),
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
def library(tmp_path):
    path = tmp_path / "library"
    path.mkdir()
    return path


@pytest.fixture
def organizer(library):
    return FileOrganizer(str(library))


@pytest.fixture
def session(test_db):
    _engine, session_factory = test_db
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _magazines(library: Path) -> Path:
    category = library / "_Magazines"
    category.mkdir(exist_ok=True)
    return category


class TestBuildTargetPath:
    """Target paths built from metadata, including the default layout and patterns."""

    def test_default_layout_sanitizes_title_and_keeps_volume_in_the_filename(self, organizer):
        target_dir, filename, expected = organizer._build_target_path_info(
            {
                "title": "Wired: Special",
                "issue_date": datetime(2024, 12, 1, tzinfo=UTC),
                "language": "English",
                "issue_number": 5,
                "volume": 12,
            },
            "_Magazines",
            None,
        )

        assert target_dir == organizer.library_dir / "_Magazines" / "Wired Special" / "2024"
        assert filename == "Wired Special - Vol12 - No5 - December2024.pdf"
        assert expected == target_dir / filename

    def test_empty_pattern_uses_the_default_layout(self, organizer):
        default_dir, default_name, _default_path = organizer._build_target_path_info(
            {
                "title": "Wired",
                "issue_date": datetime(2024, 12, 1, tzinfo=UTC),
                "volume": 3,
            },
            "_Magazines",
            None,
        )
        empty_dir, empty_name, _empty_path = organizer._build_target_path_info(
            {
                "title": "Wired",
                "issue_date": datetime(2024, 12, 1, tzinfo=UTC),
                "volume": 3,
            },
            "_Magazines",
            "",
        )

        assert empty_dir == default_dir
        assert empty_name == default_name
        assert "Vol3" not in str(empty_dir)
        assert empty_name.startswith("Wired - Vol3 - ")

    def test_pattern_substitutes_language_year_and_month(self, organizer):
        target_dir, filename, expected = organizer._build_target_path_info(
            {
                "title": "Wired",
                "issue_date": datetime(2024, 12, 5, tzinfo=UTC),
                "language": None,
                "issue_number": None,
                "volume": None,
            },
            "_Magazines",
            "{category}/{language}/{title}/{year}/{month}/",
        )

        assert target_dir == organizer.library_dir / "_Magazines" / "English" / "Wired" / "2024" / "December"
        assert filename == "Wired - December2024.pdf"
        assert expected == target_dir / filename


class TestResolveVolumeAndIssue:
    """Volume and issue resolution across derived metadata, file scans, and import names."""

    def _record(self, **kwargs) -> Periodical:
        return Periodical(
            user_id=1,
            title="Wired",
            issue_date=datetime(2024, 12, 1, tzinfo=UTC),
            file_path="/tmp/wired.pdf",
            **kwargs,
        )

    def test_derived_dict_values_win_over_file_scan_and_imported_filename(self, organizer):
        periodical = self._record(
            derived_metadata={"volume": {"value": 9}, "issue_number": {"value": 4}},
            parsed_metadata={"file_scan": {"volume": 1, "issue_number": 2}},
            extra_metadata={"imported_from": "Academic Journal Vol.12 No.3.pdf"},
        )

        assert organizer._resolve_volume_and_issue(periodical) == (9, 4)

    def test_file_scan_fills_only_fields_missing_from_derived(self, organizer):
        periodical = self._record(
            derived_metadata={"volume": {"value": 9}},
            parsed_metadata={"file_scan": {"volume": 1, "issue_number": 8}},
            extra_metadata={"imported_from": "Academic Journal Vol.12 No.3.pdf"},
        )

        assert organizer._resolve_volume_and_issue(periodical) == (9, 8)

    def test_non_dict_derived_values_are_ignored(self, organizer):
        periodical = self._record(
            derived_metadata={"volume": 9, "issue_number": {"value": 4}},
            parsed_metadata={"file_scan": {"volume": 2, "issue_number": 3}},
        )

        assert organizer._resolve_volume_and_issue(periodical) == (2, 4)

    def test_imported_filename_is_parsed_when_scans_have_no_numbers(self, organizer):
        periodical = self._record(extra_metadata={"imported_from": "Academic Journal Vol.12 No.3.pdf"})

        assert organizer._resolve_volume_and_issue(periodical) == (12, 3)

    def test_missing_sources_return_none(self, organizer):
        periodical = self._record(extra_metadata={"imported_from": "Plain Notes.pdf"})

        assert organizer._resolve_volume_and_issue(periodical) == (None, None)


class TestScanForReorganization:
    """Directory scans count supported files and leave them in place."""

    def test_missing_category_directory_is_reported(self, organizer):
        result = organizer.scan_for_reorganization("Comics")

        assert result["success"] is False
        assert result["files_found"] == 0
        assert result["files_reorganized"] == 0
        assert "_Comics" in result["error"]

    def test_counts_supported_files_and_does_not_move_them(self, organizer, library):
        category = _magazines(library)
        empty = organizer.scan_for_reorganization("Magazines")
        assert empty["success"] is True
        assert empty["files_found"] == 0
        assert empty["files_reorganized"] == 0
        assert empty["pattern"] == "{category}/{title}/{year}/"

        kept = [
            _write(category / "nested" / "a.PDF", "pdf"),
            _write(category / "b.epub", "epub"),
            _write(category / "c.cbz", "cbz"),
            _write(category / "d.cbr", "cbr"),
            _write(category / "e.pdf'", "quoted"),
            _write(category / "sub" / "h.pdf", "nested-pdf"),
            _write(category / "fake.pdf" / "real.epub", "inside-dir"),
        ]
        _write(category / "f.txt", "text")
        _write(category / "g.jpg", "cover")
        (category / "fake.pdf").mkdir(exist_ok=True)

        result = organizer.scan_for_reorganization("Magazines", pattern="{category}/{title}/", dry_run=False)

        assert result["success"] is True
        assert result["files_found"] == len(kept)
        assert result["files_reorganized"] == 0
        assert result["errors"] == []
        assert result["dry_run"] is False
        assert result["pattern"] == "{category}/{title}/"
        assert result["category_dir"] == str(category)
        for path in kept:
            assert path.exists()
        assert (category / "f.txt").exists()
        assert (category / "g.jpg").exists()
        assert (category / "fake.pdf").is_dir()


class TestReorganizeFromDatabase:
    """Moving database-backed periodicals into the metadata path."""

    def test_moves_file_cover_and_deletes_database_sidecar(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "issue-bytes")
        cover = _write(source.with_suffix(".jpg"), "cover-bytes")
        sidecar = _write_sidecar(source, "Wired")
        periodical = _add_periodical(
            session,
            source,
            derived_metadata={"volume": {"value": 12}, "issue_number": {"value": 4}},
        )

        result = organizer.reorganize_from_database(session, "Magazines", dry_run=False, auto_fix_tracking=False)
        session.refresh(periodical)

        expected = library / "_Magazines" / "Wired" / "2024" / "Wired - Vol12 - No4 - December2024.pdf"
        assert result["success"] is True
        assert result["files_found"] == 1
        assert result["files_reorganized"] == 1
        assert result["files_skipped"] == 0
        assert result["errors"] == []
        assert result["dry_run"] is False
        assert result["pattern"] == "{category}/{title}/{year}/"
        assert "tracking_fixes" not in result
        assert result["changes"][0]["old_path"] == str(source)
        assert result["changes"][0]["new_path"] == str(expected)
        assert result["changes"][0]["old_folder"] == "Inbox"
        assert result["changes"][0]["new_folder"] == "2024"
        assert expected.read_text() == "issue-bytes"
        assert expected.with_suffix(".jpg").read_text() == "cover-bytes"
        assert periodical.file_path == str(expected)
        assert periodical.cover_path == str(expected.with_suffix(".jpg"))
        assert periodical.title == "Wired"
        assert not source.exists()
        assert not cover.exists()
        assert not sidecar.exists()
        assert not _sidecar_path(expected).exists()
        assert not source.parent.exists()

    def test_dry_run_reports_the_move_without_changing_files_or_rows(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "stay")
        periodical = _add_periodical(session, source)
        original_path = periodical.file_path

        result = organizer.reorganize_from_database(session, "Magazines", dry_run=True, auto_fix_tracking=False)
        session.refresh(periodical)

        assert result["dry_run"] is True
        assert result["files_found"] == 1
        assert result["files_reorganized"] == 1
        assert result["files_skipped"] == 0
        assert result["changes"][0]["new_path"].endswith("Wired - December2024.pdf")
        assert source.read_text() == "stay"
        assert periodical.file_path == original_path
        assert not (library / "_Magazines" / "Wired" / "2024").exists()

    def test_missing_file_is_skipped_and_default_tracking_fix_is_reported(self, organizer, library, session):
        _magazines(library)
        missing = library / "_Magazines" / "Inbox" / "gone.pdf"
        periodical = _add_periodical(session, missing)

        single = organizer._process_single_periodical_reorganization(
            periodical,
            session,
            "_Magazines",
            None,
            False,
            set(),
        )
        result = organizer.reorganize_from_database(session, "Magazines", dry_run=False)
        session.refresh(periodical)

        assert single == {"status": "skipped", "reason": "file_not_found"}
        assert result["success"] is True
        assert result["files_found"] == 1
        assert result["files_reorganized"] == 0
        assert result["files_skipped"] == 1
        assert result["changes"] == []
        assert result["tracking_fixes"]["fixed"] == 0
        assert result["tracking_fixes"]["message"] == "No tracking records found"
        assert periodical.file_path == str(missing)
        assert not missing.exists()

    def test_file_already_at_the_metadata_path_is_left_alone(self, organizer, library, session):
        _magazines(library)
        _target_dir, _filename, expected = organizer._build_target_path_info(
            {
                "title": "Wired",
                "issue_date": datetime(2024, 12, 1, tzinfo=UTC),
                "language": "English",
                "issue_number": None,
                "volume": None,
            },
            "_Magazines",
            None,
        )
        _write(expected, "already")
        periodical = _add_periodical(session, expected)

        single = organizer._process_single_periodical_reorganization(
            periodical,
            session,
            "_Magazines",
            None,
            False,
            set(),
        )
        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(periodical)

        assert single == {"status": "skipped", "reason": "already_correct"}
        assert result["files_reorganized"] == 0
        assert result["files_skipped"] == 1
        assert result["changes"] == []
        assert expected.read_text() == "already"
        assert periodical.file_path == str(expected)

    def test_tracking_title_becomes_the_folder_and_stored_title(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "tracked")
        tracking = PeriodicalTracking(user_id=1, olid="OLWIRED", title="Canonical Wired", language="English")
        session.add(tracking)
        session.commit()
        periodical = _add_periodical(session, source, title="Inbox Wired", tracking_id=tracking.id)

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(periodical)

        expected = library / "_Magazines" / "Canonical Wired" / "2024" / "Canonical Wired - December2024.pdf"
        assert result["files_reorganized"] == 1
        assert result["changes"][0]["title_changed"] is True
        assert result["changes"][0]["new_title"] == "Canonical Wired"
        assert expected.read_text() == "tracked"
        assert periodical.file_path == str(expected)
        assert periodical.title == "Canonical Wired"
        assert periodical.tracking_id == tracking.id
        assert not source.exists()

    def test_pattern_is_applied_to_a_database_file(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "patterned")
        periodical = _add_periodical(session, source, language=None)
        pattern = "{category}/{language}/{title}/{year}/{month}/"

        result = organizer.reorganize_from_database(session, "Magazines", pattern=pattern, auto_fix_tracking=False)
        session.refresh(periodical)

        expected = library / "_Magazines" / "English" / "Wired" / "2024" / "December" / "Wired - December2024.pdf"
        assert result["pattern"] == pattern
        assert result["files_reorganized"] == 1
        assert periodical.file_path == str(expected)
        assert expected.read_text() == "patterned"
        assert not source.exists()

    def test_epub_is_renamed_to_a_pdf_extension(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "story.epub", "EPUBDATA")
        periodical = _add_periodical(session, source)

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(periodical)

        expected = library / "_Magazines" / "Wired" / "2024" / "Wired - December2024.pdf"
        assert result["files_reorganized"] == 1
        assert expected.read_text() == "EPUBDATA"
        assert expected.suffix == ".pdf"
        assert periodical.file_path == str(expected)
        assert not source.exists()
        assert not any(category.rglob("*.epub"))

    def test_existing_destination_file_gets_a_timestamp_suffix(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "mover")
        blocker = _write(
            library / "_Magazines" / "Wired" / "2024" / "Wired - December2024.pdf",
            "blocker",
        )
        periodical = _add_periodical(session, source)

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(periodical)

        final = Path(periodical.file_path)
        assert result["files_reorganized"] == 1
        assert blocker.read_text() == "blocker"
        assert final.read_text() == "mover"
        assert final.parent == blocker.parent
        assert re.fullmatch(r"Wired - December2024 \(\d{8}_\d{6}\)\.pdf", final.name)
        assert not source.exists()

    def test_path_owned_by_another_row_is_not_taken(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "keep-me")
        _target_dir, _filename, expected = organizer._build_target_path_info(
            {
                "title": "Wired",
                "issue_date": datetime(2024, 12, 1, tzinfo=UTC),
                "language": "English",
                "issue_number": None,
                "volume": None,
            },
            "_Magazines",
            None,
        )
        owner = _add_periodical(session, expected, title="Wired")
        mover = _add_periodical(session, source, title="Wired")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(owner)
        session.refresh(mover)

        assert result["files_found"] == 2
        assert result["files_reorganized"] == 0
        assert result["files_skipped"] == 2
        assert result["errors"] == []
        assert source.read_text() == "keep-me"
        assert mover.file_path == str(source)
        assert owner.file_path == str(expected)
        assert not expected.exists()

    def test_sibling_periodical_file_keeps_the_source_directory(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "moved")
        sibling = _write(category / "Inbox" / "other.pdf", "stay")
        _add_periodical(session, source)

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)

        assert result["files_found"] == 1
        assert result["files_reorganized"] == 1
        assert sibling.read_text() == "stay"
        assert source.parent.exists()
        assert not source.exists()

    def test_record_outside_the_category_path_is_not_selected(self, organizer, library, session):
        magazines = _magazines(library)
        comics = library / "_Comics"
        magazine = _write(magazines / "Inbox" / "misplaced.pdf", "magazine")
        comic = _write(comics / "Inbox" / "issue.cbz", "comic")
        magazine_row = _add_periodical(session, magazine)
        comic_row = _add_periodical(session, comic, title="Comic", category="Comics")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(magazine_row)
        session.refresh(comic_row)

        assert result["files_found"] == 1
        assert result["files_reorganized"] == 1
        assert magazine_row.file_path.endswith("Wired - December2024.pdf")
        assert comic_row.file_path == str(comic)
        assert comic.read_text() == "comic"

    def test_exception_is_recorded_and_the_result_stays_successful(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "misplaced.pdf", "unstirred")
        periodical = _add_periodical(session, source)

        def _explode(*_args, **_kwargs):
            raise RuntimeError("disk full")

        with patch.object(organizer, "_build_target_path_info", side_effect=_explode):
            result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)
        session.refresh(periodical)

        assert result["success"] is True
        assert result["files_found"] == 1
        assert result["files_reorganized"] == 0
        assert result["files_skipped"] == 1
        assert len(result["errors"]) == 1
        assert "disk full" in result["errors"][0]
        assert str(source) in result["errors"][0]
        assert source.read_text() == "unstirred"
        assert periodical.file_path == str(source)

    def test_missing_category_commits_tracking_fix_and_drops_it_from_the_result(self, organizer, session):
        tracking = PeriodicalTracking(user_id=1, olid="OLWIRED", title="Wired", language="English")
        session.add(tracking)
        session.commit()
        periodical = _add_periodical(
            session,
            "/missing/_Magazines/gone.pdf",
            title="Wired",
            tracking_id=None,
        )

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=True)
        session.refresh(periodical)

        assert result["success"] is False
        assert result["files_found"] == 0
        assert result["files_reorganized"] == 0
        assert "_Magazines" in result["error"]
        assert "tracking_fixes" not in result
        assert periodical.tracking_id == tracking.id


class TestSidecarReorganization:
    """Files that are not in the database are moved from sidecar metadata."""

    def test_sidecar_with_integer_month_moves_file_cover_and_sidecar(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "Wired.December.2024.pdf", "sidecar-bytes")
        cover = _write(source.with_suffix(".jpg"), "cover-bytes")
        sidecar = _write_sidecar(source, "Wired", country="DE", language="English")
        unrelated = _write(category / "Keep" / "other.pdf", "unrelated")
        invalid = _write(category / "Keep" / "Other - January2020.pdf", "invalid")
        _sidecar_path(invalid).write_text("{not-json")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)

        expected = library / "_Magazines" / "Wired DE" / "2024" / "Wired DE - December2024.pdf"
        assert result["files_found"] == 1
        assert result["files_reorganized"] == 1
        assert result["files_skipped"] == 0
        assert result["changes"][0]["source"] == "sidecar"
        assert result["changes"][0]["new_title"] == "Wired DE"
        assert expected.read_text() == "sidecar-bytes"
        assert expected.with_suffix(".jpg").read_text() == "cover-bytes"
        moved_sidecar = _sidecar_path(expected)
        assert json.loads(moved_sidecar.read_text())["tracking_title"] == "Wired"
        assert json.loads(moved_sidecar.read_text())["country"] == "DE"
        assert not source.exists()
        assert not cover.exists()
        assert not sidecar.exists()
        assert not source.parent.exists()
        assert unrelated.read_text() == "unrelated"
        assert invalid.read_text() == "invalid"

    def test_dash_month_name_without_integer_month_is_stored_as_january(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "Hello - December2024.pdf", "december")
        _write_sidecar(source, "Hello")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)

        january = library / "_Magazines" / "Hello" / "2024" / "Hello - January2024.pdf"
        december = library / "_Magazines" / "Hello" / "2024" / "Hello - December2024.pdf"
        assert result["files_reorganized"] == 1
        assert result["changes"][0]["new_path"] == str(january)
        assert january.read_text() == "december"
        assert not december.exists()
        assert not source.exists()

    def test_country_name_already_in_the_title_is_not_appended(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "Hello Germany - January2021.pdf", "de")
        _write_sidecar(source, "Hello Germany", country="DE")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)

        expected = library / "_Magazines" / "Hello Germany" / "2021" / "Hello Germany - January2021.pdf"
        doubled = library / "_Magazines" / "Hello Germany DE" / "2021" / "Hello Germany DE - January2021.pdf"
        assert result["files_reorganized"] == 1
        assert expected.read_text() == "de"
        assert not doubled.exists()

    def test_sidecar_dry_run_reports_the_destination_and_leaves_the_file(self, organizer, library, session):
        category = _magazines(library)
        source = _write(category / "Inbox" / "Wired.December.2024.pdf", "dry")
        sidecar = _write_sidecar(source, "Wired")

        result = organizer.reorganize_from_database(session, "Magazines", dry_run=True, auto_fix_tracking=False)

        assert result["dry_run"] is True
        assert result["files_found"] == 1
        assert result["files_reorganized"] == 1
        assert result["changes"][0]["source"] == "sidecar"
        assert result["changes"][0]["new_path"].endswith("/Wired/2024/Wired - December2024.pdf")
        assert source.read_text() == "dry"
        assert sidecar.exists()
        assert not (library / "_Magazines" / "Wired").exists()

    def test_sidecar_already_in_place_is_skipped(self, organizer, library, session):
        _magazines(library)
        expected = library / "_Magazines" / "Hello" / "2021" / "Hello - January2021.pdf"
        _write(expected, "placed")
        _write_sidecar(expected, "Hello")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)

        assert result["files_found"] == 1
        assert result["files_reorganized"] == 0
        assert result["files_skipped"] == 1
        assert result["changes"] == []
        assert expected.read_text() == "placed"
        assert _sidecar_path(expected).exists()

    def test_blank_tracking_title_and_undated_filename_are_skipped(self, organizer, library, session):
        category = _magazines(library)
        blank = _write(category / "Inbox" / "Hello - January2021.pdf", "blank")
        _write_sidecar(blank, "")
        undated = _write(category / "Inbox" / "Plain Notes.pdf", "notes")
        _write_sidecar(undated, "Plain Notes")

        result = organizer.reorganize_from_database(session, "Magazines", auto_fix_tracking=False)

        assert result["files_found"] == 2
        assert result["files_reorganized"] == 0
        assert result["files_skipped"] == 2
        assert result["changes"] == []
        assert blank.read_text() == "blank"
        assert undated.read_text() == "notes"
        assert (category / "Inbox").exists()


class TestCleanupDirectories:
    """Empty-directory cleanup and leftover non-periodical files."""

    def test_safe_cleanup_removes_leftovers_empty_dirs_and_keeps_periodical_dirs(self, organizer, tmp_path):
        base = tmp_path / "library"
        issue = base / "year" / "issue"
        _write(issue / "notes.nfo", "nfo")
        _write(issue / "extra.txt", "txt")
        _write(base / "other" / "keep.pdf", "keep")
        (base / "stray_empty").mkdir(parents=True)
        kept = base / "kept_pdf"
        _write(kept / "ISSUE.PDF", "pdf")
        _write(kept / "notes.nfo", "keep-nfo")
        outside = tmp_path / "outside" / "old"
        _write(outside / "orphan.nfo", "orphan")
        missing = base / "missing"

        removed = organizer._safe_cleanup_library_directories({issue, kept, outside, missing}, base)

        assert removed == 4
        assert not issue.exists()
        assert not (base / "year").exists()
        assert not (base / "stray_empty").exists()
        assert not outside.exists()
        assert outside.parent.exists()
        assert (base / "other" / "keep.pdf").read_text() == "keep"
        assert (kept / "ISSUE.PDF").read_text() == "pdf"
        assert (kept / "notes.nfo").read_text() == "keep-nfo"
        assert base.exists()

    def test_safe_cleanup_keeps_directory_that_still_has_a_subdirectory(self, organizer, tmp_path):
        base = tmp_path / "library"
        parent = base / "parent"
        _write(parent / "leftover.txt", "bye")
        child = _write(parent / "nested" / "child.pdf", "child")

        removed = organizer._safe_cleanup_library_directories({parent}, base)

        assert removed == 0
        assert parent.exists()
        assert not (parent / "leftover.txt").exists()
        assert child.read_text() == "child"

    def test_safe_cleanup_keeps_an_empty_base_directory(self, organizer, tmp_path):
        base = tmp_path / "empty-base"
        base.mkdir()

        assert organizer._safe_cleanup_library_directories(set(), base) == 0
        assert base.exists()

    def test_find_cleanup_removes_empty_children_and_returns_zero(self, organizer, tmp_path):
        base = tmp_path / "library"
        (base / "a" / "b").mkdir(parents=True)
        _write(base / "keep" / "file.txt", "stay")

        removed = organizer._cleanup_empty_directories(base)

        assert removed == 0
        assert base.exists()
        assert not (base / "a").exists()
        assert (base / "keep" / "file.txt").read_text() == "stay"

    def test_find_cleanup_deletes_the_base_directory_when_it_is_empty(self, organizer, tmp_path):
        base = tmp_path / "empty-category"
        base.mkdir()

        removed = organizer._cleanup_empty_directories(base)

        assert removed == 0
        assert not base.exists()

    def test_python_cleanup_counts_removed_directories_and_keeps_the_base(self, organizer, tmp_path):
        base = tmp_path / "library"
        (base / "a" / "b" / "c").mkdir(parents=True)
        _write(base / "keep" / "file.txt", "stay")

        removed = organizer._cleanup_empty_directories_python(base)

        assert removed == 3
        assert base.exists()
        assert not (base / "a").exists()
        assert (base / "keep" / "file.txt").read_text() == "stay"

    def test_find_failure_falls_back_to_the_python_count(self, organizer, tmp_path):
        base = tmp_path / "library"
        (base / "a" / "b").mkdir(parents=True)
        _write(base / "keep" / "file.txt", "stay")

        with patch("subprocess.run", return_value=CompletedProcess(args=["find"], returncode=1, stderr="fail")):
            removed = organizer._cleanup_empty_directories(base)

        assert removed == 2
        assert base.exists()
        assert not (base / "a").exists()
        assert (base / "keep" / "file.txt").read_text() == "stay"

    def test_missing_find_command_falls_back_to_python(self, organizer, tmp_path):
        base = tmp_path / "library"
        (base / "only-empty").mkdir(parents=True)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            removed = organizer._cleanup_empty_directories(base)

        assert removed == 1
        assert base.exists()
        assert not (base / "only-empty").exists()

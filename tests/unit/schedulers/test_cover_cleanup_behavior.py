"""Behavior tests for CoverCleanup orphan deletion and cover generation.

Two production behaviors are recorded here because the task is under test,
not changed:

* Thumbnails are written beside covers as ``<stem>_thumb.jpg``. The next run
  treats every ``*.jpg`` that is not a ``Periodical.cover_path`` as an orphan,
  so that thumbnail is deleted.
* If generating a cover raises after orphans have already been unlinked,
  ``run()`` still returns ``deleted_count`` 0. The files stay deleted.
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, Periodical
from schedulers.cover_cleanup import CoverCleanup


def _write_jpeg(path: Path, color=(20, 30, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (6, 8), color).save(path, format="JPEG")


@contextmanager
def sqlite_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'covers.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _add_periodical(session, **overrides) -> Periodical:
    values = {
        "user_id": 1,
        "title": "Issue",
        "issue_date": datetime(2024, 6, 1),
        "file_path": overrides.get("file_path", "/missing/issue.pdf"),
        "cover_path": None,
    }
    values.update(overrides)
    row = Periodical(**values)
    session.add(row)
    session.commit()
    return row


def _run(factory, library, importer=None):
    task = CoverCleanup(factory, str(library), importer or Mock())
    return asyncio.run(task.run())


def test_deletes_orphan_jpgs_and_keeps_referenced_covers(tmp_path):
    """Orphan top-level JPGs are removed. Referenced covers and other files stay."""
    library = tmp_path / "library"
    covers = library / ".covers"
    covers.mkdir(parents=True)
    nested = covers / "nested"
    nested.mkdir()

    kept = covers / "kept.jpg"
    shared = kept
    orphan = covers / "orphan.jpg"
    second_orphan = covers / "second-orphan.jpg"
    outside = tmp_path / "outside.jpg"
    note = covers / "note.png"
    nested_jpg = nested / "nested.jpg"
    for path, color in (
        (kept, (1, 2, 3)),
        (orphan, (4, 5, 6)),
        (second_orphan, (7, 8, 9)),
        (outside, (10, 11, 12)),
        (note, (13, 14, 15)),
        (nested_jpg, (16, 17, 18)),
    ):
        _write_jpeg(path, color)

    kept_file = tmp_path / "kept.pdf"
    shared_file = tmp_path / "shared.pdf"
    outside_file = tmp_path / "outside.pdf"
    for path in (kept_file, shared_file, outside_file):
        path.write_bytes(b"%PDF-1.4")

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(
            session,
            title="Kept",
            file_path=str(kept_file),
            cover_path=str(kept),
        )
        _add_periodical(
            session,
            title="Shared",
            file_path=str(shared_file),
            cover_path=str(shared),
        )
        _add_periodical(
            session,
            title="Outside",
            file_path=str(outside_file),
            cover_path=str(outside),
        )
        session.close()

        result = _run(factory, library)

        session = factory()
        stored = {row.title: row.cover_path for row in session.query(Periodical).all()}
        session.close()

    assert result == {"deleted_count": 2, "generated_count": 0, "thumbnail_count": 0}
    assert kept.exists()
    assert outside.exists()
    assert note.exists()
    assert nested_jpg.exists()
    assert not orphan.exists()
    assert not second_orphan.exists()
    assert stored == {
        "Kept": str(kept),
        "Shared": str(shared),
        "Outside": str(outside),
    }


def test_keeps_cover_when_stored_path_resolves_to_the_same_file(tmp_path):
    """db paths are resolved before they are compared with files on disk."""
    library = tmp_path / "library"
    covers = library / ".covers"
    kept = covers / "kept.jpg"
    orphan = covers / "orphan.jpg"
    _write_jpeg(kept, (30, 10, 10))
    _write_jpeg(orphan, (10, 10, 30))
    stored = covers / "." / "kept.jpg"
    assert stored.resolve() == kept.resolve()

    issue = tmp_path / "issue.pdf"
    issue.write_bytes(b"%PDF-1.4")

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(
            session,
            title="Normalized",
            file_path=str(issue),
            cover_path=str(stored),
        )
        session.close()
        result = _run(factory, library)

    assert result["deleted_count"] == 1
    assert result["generated_count"] == 0
    assert kept.exists()
    assert not orphan.exists()


def test_creates_covers_directory_when_library_has_no_covers(tmp_path):
    library = tmp_path / "library"
    with sqlite_factory(tmp_path) as factory:
        result = _run(factory, library)

    assert result == {"deleted_count": 0, "generated_count": 0, "thumbnail_count": 0}
    assert (library / ".covers").is_dir()


def test_generates_missing_covers_and_persists_paths(tmp_path):
    """Periodicals with a file and no existing cover get a cover and a thumbnail."""
    library = tmp_path / "library"
    covers = library / ".covers"
    june = tmp_path / "june.pdf"
    july = tmp_path / "july.pdf"
    june.write_bytes(b"%PDF-1.4 june")
    july.write_bytes(b"%PDF-1.4 july")
    calls = []

    def extract(file_path):
        calls.append(Path(file_path))
        dest = covers / f"{Path(file_path).stem}.jpg"
        _write_jpeg(dest, (40, 80, 120))
        return dest

    importer = Mock()
    importer._extract_cover.side_effect = extract

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(session, title="June", file_path=str(june), cover_path=None)
        _add_periodical(
            session,
            title="July",
            file_path=str(july),
            cover_path=str(covers / "missing-july.jpg"),
        )
        session.close()

        closed = {"count": 0}
        real_factory = factory

        def tracking_factory():
            db_session = real_factory()
            original_close = db_session.close

            def close():
                closed["count"] += 1
                return original_close()

            db_session.close = close
            return db_session

        result = _run(tracking_factory, library, importer)

        session = factory()
        stored = {row.title: row.cover_path for row in session.query(Periodical).all()}
        session.close()

    assert result == {"deleted_count": 0, "generated_count": 2, "thumbnail_count": 2}
    assert sorted(path.name for path in calls) == ["july.pdf", "june.pdf"]
    assert stored["June"] == str(covers / "june.jpg")
    assert stored["July"] == str(covers / "july.jpg")
    for stem in ("june", "july"):
        cover = covers / f"{stem}.jpg"
        thumb = covers / f"{stem}_thumb.jpg"
        assert cover.is_file()
        assert thumb.is_file()
        with Image.open(thumb) as image:
            assert image.format == "JPEG"
            assert image.size[0] > 0 and image.size[1] > 0
    assert closed["count"] == 1


def test_skips_missing_files_and_leaves_cover_empty_when_extract_returns_none(tmp_path):
    library = tmp_path / "library"
    present = tmp_path / "present.pdf"
    present.write_bytes(b"%PDF-1.4")
    calls = []

    def extract(file_path):
        calls.append(Path(file_path))
        return None

    importer = Mock()
    importer._extract_cover.side_effect = extract

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(
            session,
            title="Missing File",
            file_path=str(tmp_path / "absent.pdf"),
            cover_path=None,
        )
        _add_periodical(session, title="No Cover Found", file_path=str(present), cover_path=None)
        session.close()

        result = _run(factory, library, importer)

        session = factory()
        stored = {row.title: row.cover_path for row in session.query(Periodical).all()}
        session.close()

    assert calls == [present]
    assert result == {"deleted_count": 0, "generated_count": 0, "thumbnail_count": 0}
    assert stored == {"Missing File": None, "No Cover Found": None}


def test_thumbnail_failure_still_saves_the_generated_cover(tmp_path):
    library = tmp_path / "library"
    covers = library / ".covers"
    issue = tmp_path / "issue.pdf"
    issue.write_bytes(b"%PDF-1.4")
    generated = covers / "issue.jpg"

    def extract(file_path):
        _write_jpeg(generated, (90, 10, 10))
        return generated

    importer = Mock()
    importer._extract_cover.side_effect = extract

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(session, title="Issue", file_path=str(issue), cover_path=None)
        session.close()
        with patch("core.utils.thumbnail.generate_thumbnail", side_effect=RuntimeError("thumb failed")):
            result = _run(factory, library, importer)
        session = factory()
        row = session.query(Periodical).one()
        cover_path = row.cover_path
        session.close()

    assert "error" not in result
    assert result["generated_count"] == 1
    assert result["thumbnail_count"] == 0
    assert cover_path == str(generated)
    assert generated.is_file()
    assert not (covers / "issue_thumb.jpg").exists()


def test_unlink_error_on_one_orphan_still_deletes_the_others(tmp_path):
    library = tmp_path / "library"
    covers = library / ".covers"
    kept = covers / "kept.jpg"
    orphan = covers / "orphan.jpg"
    locked = covers / "locked.jpg"
    _write_jpeg(kept)
    _write_jpeg(orphan)
    locked.mkdir(parents=True)
    issue = tmp_path / "issue.pdf"
    issue.write_bytes(b"%PDF-1.4")

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(session, title="Kept", file_path=str(issue), cover_path=str(kept))
        session.close()
        result = _run(factory, library)

    assert result["deleted_count"] == 1
    assert result["generated_count"] == 0
    assert "error" not in result
    assert kept.is_file()
    assert not orphan.exists()
    assert locked.is_dir()


def test_generation_error_reports_zero_deletes_after_orphans_are_removed(tmp_path):
    """Orphans are unlinked before generation. A later exception reports zero deletes."""
    library = tmp_path / "library"
    covers = library / ".covers"
    orphan = covers / "orphan.jpg"
    kept = covers / "kept.jpg"
    _write_jpeg(orphan, (1, 1, 1))
    _write_jpeg(kept, (2, 2, 2))
    issue = tmp_path / "needs-cover.pdf"
    kept_issue = tmp_path / "kept.pdf"
    issue.write_bytes(b"%PDF-1.4")
    kept_issue.write_bytes(b"%PDF-1.4")

    importer = Mock()
    importer._extract_cover.side_effect = RuntimeError("extract failed")

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(session, title="Needs Cover", file_path=str(issue), cover_path=None)
        _add_periodical(session, title="Kept", file_path=str(kept_issue), cover_path=str(kept))
        session.close()

        closed = {"count": 0}
        real_factory = factory

        def tracking_factory():
            db_session = real_factory()
            original_close = db_session.close

            def close():
                closed["count"] += 1
                return original_close()

            db_session.close = close
            return db_session

        result = _run(tracking_factory, library, importer)
        session = factory()
        needs_cover = session.query(Periodical).filter_by(title="Needs Cover").one()
        assert needs_cover.cover_path is None
        session.close()

    assert result["deleted_count"] == 0
    assert result["generated_count"] == 0
    assert result["thumbnail_count"] == 0
    assert result["error"] == "extract failed"
    assert not orphan.exists()
    assert kept.exists()
    assert closed["count"] == 1


def test_following_run_deletes_thumbnail_that_is_not_a_cover_path(tmp_path):
    """The thumbnail written next to a new cover is an orphan on the next run.

    ``generate_thumbnail`` saves ``<stem>_thumb.jpg`` in the cover directory.
    ``CoverCleanup`` keeps a JPEG only when its resolved path is stored on
    ``Periodical.cover_path``. The thumbnail path is not stored, so the second
    run deletes it.
    """
    library = tmp_path / "library"
    covers = library / ".covers"
    issue = tmp_path / "issue.pdf"
    issue.write_bytes(b"%PDF-1.4")
    generated = covers / "issue.jpg"

    def extract(file_path):
        _write_jpeg(generated, (15, 25, 35))
        return generated

    importer = Mock()
    importer._extract_cover.side_effect = extract
    thumb = covers / "issue_thumb.jpg"

    with sqlite_factory(tmp_path) as factory:
        session = factory()
        _add_periodical(session, title="Issue", file_path=str(issue), cover_path=None)
        session.close()

        first = _run(factory, library, importer)
        assert first["generated_count"] == 1
        assert first["thumbnail_count"] == 1
        assert generated.is_file()
        assert thumb.is_file()

        second = _run(factory, library, importer)
        session = factory()
        row = session.query(Periodical).one()
        assert row.cover_path == str(generated)
        session.close()

    assert second == {"deleted_count": 1, "generated_count": 0, "thumbnail_count": 0}
    assert generated.is_file()
    assert not thumb.exists()


def test_session_factory_failure_returns_zero_counts_and_error(tmp_path):
    def factory():
        raise RuntimeError("db down")

    result = _run(factory, tmp_path / "library")

    assert result == {
        "deleted_count": 0,
        "generated_count": 0,
        "thumbnail_count": 0,
        "error": "db down",
    }
    assert not (tmp_path / "library" / ".covers").exists()

"""Behavior tests for the tracking preference handlers in web/routers/tracking/preferences.py."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, Periodical, PeriodicalTracking
from web.routers.auth import get_verify_token
from web.routers.tracking import router, set_dependencies


@pytest.fixture
def test_db():
    """File-backed SQLite so request threads share committed rows."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    try:
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def library_dir(tmp_path):
    path = tmp_path / "library"
    path.mkdir()
    return path


@pytest.fixture
def feed_sync():
    feed = MagicMock()
    feed.reset_skipped_entries.return_value = 2
    return feed


@pytest.fixture
def test_client(test_db, library_dir, feed_sync):
    """Mount the tracking router and bypass token verification."""
    _, session_factory = test_db
    set_dependencies(
        session_factory,
        search_providers=[],
        storage_config={"library_dir": str(library_dir)},
        import_config={"category_prefix": "_"},
        feed_sync_service=feed_sync,
    )
    app = FastAPI()
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    app.include_router(router)
    with TestClient(app) as client:
        yield client


def _session(test_db):
    _, session_factory = test_db
    return session_factory()


def _tracking(session, **overrides):
    values = {
        "user_id": 1,
        "olid": "wired",
        "title": "Wired",
        "language": "English",
        "category": "Magazines",
        "track_all_editions": False,
        "track_new_only": False,
        "selected_editions": {},
        "selected_years": [2020, 2021, 2024],
        "delete_from_client_on_completion": True,
    }
    values.update(overrides)
    row = PeriodicalTracking(**values)
    session.add(row)
    return row


def _reload(test_db, model, row_id):
    session = _session(test_db)
    try:
        row = session.get(model, row_id)
        if row is not None:
            session.expunge(row)
        return row
    finally:
        session.close()


class TestSaveTrackingPreferences:
    """POST /api/periodicals/tracking/save"""

    def test_save_persists_track_all_and_selected_years(self, test_client, test_db):
        response = test_client.post(
            "/api/periodicals/tracking/save",
            json={
                "olid": "OL12345W",
                "title": "National Geographic",
                "first_publish_year": 1888,
                "country": "US",
                "track_all_editions": True,
                "track_new_only": False,
                "selected_editions": {"OL1M": True, "OL2M": False},
                "selected_years": [2020, 2021, 2024],
                "metadata": {"source": "test"},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["track_all_editions"] is True
        assert body["selected_count"] == 1
        assert "National Geographic" in body["message"]
        saved = _reload(test_db, PeriodicalTracking, body["tracking_id"])
        assert saved.title == "National Geographic"
        assert saved.olid == "OL12345W"
        assert saved.user_id == 1
        assert saved.track_all_editions is True
        assert saved.track_new_only is False
        assert saved.selected_years == [2020, 2021, 2024]
        assert saved.selected_editions == {"OL1M": True, "OL2M": False}
        assert saved.first_publish_year == 1888
        assert saved.country == "US"
        assert saved.periodical_metadata == {"source": "test"}
        assert saved.last_metadata_update is not None

    def test_save_updates_existing_olid(self, test_client, test_db):
        created = test_client.post(
            "/api/periodicals/tracking/save",
            json={
                "olid": "OL12345W",
                "title": "National Geographic",
                "track_all_editions": False,
                "selected_years": [2019],
                "selected_editions": {},
            },
        )
        assert created.status_code == 200
        tracking_id = created.json()["tracking_id"]

        updated = test_client.post(
            "/api/periodicals/tracking/save",
            json={
                "olid": "OL12345W",
                "title": "National Geographic Magazine",
                "track_all_editions": True,
                "track_new_only": True,
                "selected_years": [2022, 2023],
                "selected_editions": {"OL9M": True},
            },
        )

        assert updated.status_code == 200
        assert updated.json()["tracking_id"] == tracking_id
        assert updated.json()["track_all_editions"] is True
        assert updated.json()["selected_count"] == 1
        session = _session(test_db)
        try:
            rows = session.query(PeriodicalTracking).all()
            assert len(rows) == 1
            assert rows[0].title == "National Geographic Magazine"
            assert rows[0].track_all_editions is True
            assert rows[0].track_new_only is True
            assert rows[0].selected_years == [2022, 2023]
        finally:
            session.close()

    def test_blank_olid_is_generated_from_title(self, test_client, test_db):
        response = test_client.post(
            "/api/periodicals/tracking/save",
            json={"olid": "", "title": "PC-Gamer", "track_all_editions": False, "selected_years": []},
        )

        assert response.status_code == 200
        saved = _reload(test_db, PeriodicalTracking, response.json()["tracking_id"])
        assert saved.olid == "pc_gamer"
        assert saved.title == "PC-Gamer"

    def test_save_rejects_missing_fields(self, test_client):
        response = test_client.post("/api/periodicals/tracking/save", json={})

        assert response.status_code == 422

    def test_resave_clears_category_and_resets_language(self, test_client, test_db):
        """POST save cannot keep category or language.

        TrackingPreferencesRequest has neither field. The handler assigns
        getattr defaults, so a later save writes category=None and language='English'
        even when the JSON body includes those keys and a previous PUT set them.
        """
        session = _session(test_db)
        tracking = _tracking(session, olid="OLWIRED", language="French", category="Comics")
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.post(
            "/api/periodicals/tracking/save",
            json={
                "olid": "OLWIRED",
                "title": "Wired",
                "category": "Comics",
                "language": "French",
                "track_all_editions": True,
                "selected_years": [2024],
            },
        )

        assert response.status_code == 200
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.track_all_editions is True
        assert saved.selected_years == [2024]
        assert saved.category is None
        assert saved.language == "English"


class TestUpdateTracking:
    """PUT /api/periodicals/tracking/{tracking_id}"""

    def test_missing_tracking_id_is_404(self, test_client):
        response = test_client.put(
            "/api/periodicals/tracking/99999",
            json={"track_all_editions": True},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Tracking record not found"

    def test_preference_flags_persist_and_years_are_kept(self, test_client, test_db):
        session = _session(test_db)
        tracking = _tracking(session)
        periodical = Periodical(
            user_id=1,
            title="Wired",
            language="English",
            issue_date=datetime(2024, 6, 1, tzinfo=UTC),
            file_path="/library/wired-2024-06.pdf",
            tracking_id=None,
        )
        session.add(periodical)
        session.flush()
        periodical.tracking_id = tracking.id
        session.commit()
        tracking_id, periodical_id = tracking.id, periodical.id
        session.close()

        response = test_client.put(
            f"/api/periodicals/tracking/{tracking_id}",
            json={
                "category": "Comics",
                "language": "French",
                "country": "France",
                "download_category": "Comics",
                "track_all_editions": True,
                "track_new_only": True,
                "delete_from_client_on_completion": False,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["language_updates"] == 1
        assert "Updated language" in body["message"]
        tracking_body = body["tracking"]
        assert tracking_body["id"] == tracking_id
        assert tracking_body["language"] == "French"
        assert tracking_body["track_all_editions"] is True
        assert tracking_body["track_new_only"] is True
        assert tracking_body["delete_from_client_on_completion"] is False
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.category == "Comics"
        assert saved.language == "French"
        assert saved.country == "France"
        assert saved.download_category == "Comics"
        assert saved.track_all_editions is True
        assert saved.track_new_only is True
        assert saved.delete_from_client_on_completion is False
        assert saved.selected_years == [2020, 2021, 2024]
        issue = _reload(test_db, Periodical, periodical_id)
        assert issue.language == "French"

    def test_put_does_not_apply_selected_years(self, test_client, test_db):
        """selected_years is stored by POST /save. PUT ignores that key."""
        session = _session(test_db)
        tracking = _tracking(session, selected_years=[2020])
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.put(
            f"/api/periodicals/tracking/{tracking_id}",
            json={"selected_years": [1999, 2000], "track_all_editions": True},
        )

        assert response.status_code == 200
        assert response.json()["tracking"]["track_all_editions"] is True
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.track_all_editions is True
        assert saved.selected_years == [2020]

    def test_organization_pattern_reports_affected_files(self, test_client, test_db):
        session = _session(test_db)
        tracking = _tracking(session, organization_pattern=None)
        session.flush()
        session.add(
            Periodical(
                user_id=1,
                title="Wired",
                issue_date=datetime(2024, 6, 1, tzinfo=UTC),
                file_path="/library/wired-pattern.pdf",
                tracking_id=tracking.id,
            )
        )
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.put(
            f"/api/periodicals/tracking/{tracking_id}",
            json={"organization_pattern": "{category}/{title}/"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["pattern_changed"] is True
        assert body["files_affected"] == 1
        assert body["tracking"]["organization_pattern"] == "{category}/{title}/"
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.organization_pattern == "{category}/{title}/"

    def test_alias_change_resets_skipped_feed_entries(self, test_client, test_db, feed_sync):
        session = _session(test_db)
        tracking = _tracking(session, search_aliases="old name")
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.put(
            f"/api/periodicals/tracking/{tracking_id}",
            json={"search_aliases": "new alias"},
        )

        assert response.status_code == 200
        assert response.json()["tracking"]["search_aliases"] == "new alias"
        feed_sync.reset_skipped_entries.assert_called_once_with()
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.search_aliases == "new alias"

    def test_feed_reset_failure_still_saves_aliases(self, test_client, test_db, feed_sync):
        feed_sync.reset_skipped_entries.side_effect = RuntimeError("feed down")
        session = _session(test_db)
        tracking = _tracking(session, search_aliases="old name")
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.put(
            f"/api/periodicals/tracking/{tracking_id}",
            json={"search_aliases": "kept alias"},
        )

        assert response.status_code == 200
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.search_aliases == "kept alias"

    def test_empty_update_leaves_record_unchanged(self, test_client, test_db):
        session = _session(test_db)
        tracking = _tracking(session, title="Wired", delete_from_client_on_completion=True)
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.put(f"/api/periodicals/tracking/{tracking_id}", json={})

        assert response.status_code == 200
        assert response.json()["tracking"]["title"] == "Wired"
        assert response.json()["tracking"]["delete_from_client_on_completion"] is True
        saved = _reload(test_db, PeriodicalTracking, tracking_id)
        assert saved.title == "Wired"
        assert saved.delete_from_client_on_completion is True
        assert saved.selected_years == [2020, 2021, 2024]


class TestReorganizeTrackingFiles:
    """POST /api/periodicals/tracking/{tracking_id}/reorganize"""

    def test_missing_tracking_id_is_404(self, test_client):
        response = test_client.post("/api/periodicals/tracking/99999/reorganize")

        assert response.status_code == 404
        assert response.json()["detail"] == "Tracking record not found"

    def test_reorganize_with_no_periodicals(self, test_client, test_db):
        session = _session(test_db)
        tracking = _tracking(session)
        session.commit()
        tracking_id = tracking.id
        session.close()

        response = test_client.post(f"/api/periodicals/tracking/{tracking_id}/reorganize")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["files_reorganized"] == 0
        assert body["files_failed"] == 0
        assert "0 file" in body["message"]

    def test_reorganize_moves_regular_files_and_counts_failures(self, test_client, test_db, library_dir):
        staging = library_dir / "staging" / "Wired"
        staging.mkdir(parents=True)
        source = staging / "issue.pdf"
        source.write_bytes(b"%PDF-1.4\n")
        special_source = library_dir / "staging" / "special.pdf"
        special_source.write_bytes(b"%PDF-1.4 special\n")

        session = _session(test_db)
        tracking = _tracking(session, title="Wired", organization_pattern=None)
        session.flush()
        regular = Periodical(
            user_id=1,
            title="Wired",
            issue_date=datetime(2024, 6, 1, tzinfo=UTC),
            file_path=str(source),
            tracking_id=tracking.id,
        )
        missing = Periodical(
            user_id=1,
            title="Wired",
            issue_date=datetime(2024, 7, 1, tzinfo=UTC),
            file_path=str(staging / "missing.pdf"),
            tracking_id=tracking.id,
        )
        special = Periodical(
            user_id=1,
            title="Wired Holiday",
            issue_date=datetime(2022, 12, 1, tzinfo=UTC),
            file_path=str(special_source),
            tracking_id=tracking.id,
            derived_metadata={"is_special_edition": True},
        )
        session.add_all([regular, missing, special])
        session.commit()
        tracking_id = tracking.id
        regular_id, missing_id, special_id = regular.id, missing.id, special.id
        missing_path = missing.file_path
        special_path = special.file_path
        session.close()

        response = test_client.post(f"/api/periodicals/tracking/{tracking_id}/reorganize")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["files_reorganized"] == 1
        assert body["files_failed"] == 1
        assert "1 failed" in body["message"]

        moved = _reload(test_db, Periodical, regular_id)
        failed = _reload(test_db, Periodical, missing_id)
        skipped = _reload(test_db, Periodical, special_id)
        assert moved.file_path != str(source)
        assert str(library_dir) in moved.file_path
        assert "_Magazines" in moved.file_path
        assert Path(moved.file_path).is_file()
        assert not source.exists()
        assert failed.file_path == missing_path
        assert skipped.file_path == special_path
        assert special_source.is_file()

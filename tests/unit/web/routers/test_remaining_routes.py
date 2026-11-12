"""HTTP coverage for config, covers, download operations, tracking, and task triggers.

Config reads and writes go through a temporary copy of tests/config.test.yaml.
The save route is used for updates so the process is not restarted.
"""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import ConfigLoader
from models.database import Base, DownloadSubmission, Periodical, PeriodicalTracking
from web.routers import config as config_router
from web.routers import tasks
from web.routers.auth import get_verify_token
from web.routers.downloads import _shared as downloads_shared
from web.routers.periodicals import _shared as periodicals_shared
from web.routers.tracking import _shared as tracking_shared

import web.routers.downloads.operations  # noqa: F401
import web.routers.downloads.queue  # noqa: F401
import web.routers.downloads.status  # noqa: F401
import web.routers.periodicals.covers  # noqa: F401
import web.routers.tracking.crud  # noqa: F401


SOURCE_CONFIG = Path(__file__).resolve().parents[3] / "config.test.yaml"


@pytest.fixture
def test_db():
    """File-backed SQLite so router worker threads can see committed rows."""
    import tempfile

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
def config_path(tmp_path, monkeypatch):
    """Copy the test config so reads and saves never touch a real config file."""
    destination = tmp_path / "curator-test-config.yaml"
    shutil.copy(SOURCE_CONFIG, destination)
    monkeypatch.setenv("CURATOR_CONFIG_PATH", str(destination))
    return destination


@pytest.fixture
def task_mocks():
    """Mock objects injected into the tasks router."""
    download_monitor = MagicMock()
    download_monitor.run = AsyncMock()
    folder_cleanup = MagicMock()
    folder_cleanup.run.return_value = {"total_deleted": 2, "total_size_freed": 1048576}
    scheduler = MagicMock()
    scheduler.run_task_now = AsyncMock()
    scheduler.get_status.return_value = {
        "tasks": {
            "auto_download": {"enabled": True, "interval": 1800},
            "cleanup_orphaned_covers": {"enabled": True, "interval": 86400},
            "folder_cleanup": {"enabled": False, "interval": 86400},
            "file_reorganizer": {"enabled": True, "interval": 300},
        }
    }
    task_config = MagicMock()
    task_config.get_all_config.return_value = {"tasks": {}}
    return {
        "download_monitor": download_monitor,
        "folder_cleanup": folder_cleanup,
        "scheduler": scheduler,
        "config_loader": task_config,
    }


@pytest.fixture
def download_manager():
    manager = MagicMock()
    manager.max_downloads = 5
    manager.retry_submission.return_value = {"success": True, "message": "Retry submitted"}
    return manager


@pytest.fixture
def test_client(test_db, config_path, task_mocks, download_manager, tmp_path):
    """Mount the routers under test with auth bypassed."""
    _, session_factory = test_db
    library_dir = tmp_path / "library"
    library_dir.mkdir()

    config_router.set_dependencies(ConfigLoader(str(config_path)))
    periodicals_shared.set_dependencies(session_factory=session_factory, library_base_dir=str(library_dir))
    downloads_shared.set_dependencies(session_factory, download_manager, MagicMock())
    tracking_shared.set_dependencies(session_factory=session_factory, search_providers=[])
    tasks.set_dependencies(
        session_factory=session_factory,
        download_monitor_task=task_mocks["download_monitor"],
        file_importer=MagicMock(),
        storage_config={"library_dir": str(library_dir)},
        ocr_processor_task=MagicMock(),
        task_scheduler=task_mocks["scheduler"],
        folder_cleanup_task=task_mocks["folder_cleanup"],
        config_loader=task_mocks["config_loader"],
    )

    app = FastAPI()
    app.include_router(config_router.router)
    # Tracking's /periodicals/tracking path must be registered before the
    # periodical id route, which would otherwise try to parse "tracking" as an int.
    app.include_router(tracking_shared.router)
    app.include_router(periodicals_shared.router)
    app.include_router(downloads_shared.router)
    app.include_router(tasks.router)
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    with TestClient(app) as client:
        yield client


def _session(test_db):
    _, session_factory = test_db
    return session_factory()


def _insert_tracking(test_db, **overrides):
    session = _session(test_db)
    values = {
        "user_id": 1,
        "olid": "OL1W",
        "title": "National Geographic",
        "language": "English",
        "category": "Magazines",
    }
    values.update(overrides)
    row = PeriodicalTracking(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    tracking_id = row.id
    session.close()
    return tracking_id


def _insert_periodical(test_db, **overrides):
    session = _session(test_db)
    values = {
        "user_id": 1,
        "title": "Wired",
        "language": "English",
        "category": "Magazines",
        "issue_date": datetime(2024, 6, 1, tzinfo=UTC),
        "file_path": "/library/wired-2024-06.pdf",
    }
    values.update(overrides)
    row = Periodical(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    periodical_id = row.id
    session.close()
    return periodical_id


def _insert_submission(test_db, tracking_id, **overrides):
    session = _session(test_db)
    values = {
        "user_id": 1,
        "tracking_id": tracking_id,
        "source_url": "http://example.test/issue.nzb",
        "result_title": "National Geographic 2024-06",
        "status": DownloadSubmission.StatusEnum.COMPLETED,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    row = DownloadSubmission(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    submission_id = row.id
    session.close()
    return submission_id


class TestConfigRoutes:
    """Read and save safe config fields against a temporary yaml copy."""

    def test_get_config_masks_secrets_and_returns_safe_fields(self, test_client):
        response = test_client.get("/api/config")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        config = body["config"]
        assert config["logging"]["level"] == "WARNING"
        assert config["server"]["host"] == "127.0.0.1"
        assert config["server"]["port"] == 8000
        assert config["matching"]["fuzzy_threshold"] == 80
        assert config["search_providers"][0]["api_key"] == "***"
        assert config["search_providers"][0]["name"] == "Test Newsnab"
        assert config["download_client"]["api_key"] == "***"

    def test_save_updates_safe_field_and_persists_it(self, test_client, config_path):
        response = test_client.post("/api/config/save", json={"matching": {"fuzzy_threshold": 91}})
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["status"] == "success"
        assert body["config"]["matching"]["fuzzy_threshold"] == 91
        assert body["config"]["search_providers"][0]["api_key"] == "***"
        assert body["config"]["server"]["port"] == 8000

        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert saved["matching"]["fuzzy_threshold"] == 91
        assert saved["server"]["port"] == 8000
        assert saved["search_providers"][0]["api_key"] == "test-api-key"
        assert saved["logging"]["level"] == "WARNING"

        reread = test_client.get("/api/config")
        assert reread.status_code == 200
        assert reread.json()["config"]["matching"]["fuzzy_threshold"] == 91

    def test_unknown_config_section_is_rejected(self, test_client, config_path):
        before = config_path.read_text(encoding="utf-8")
        response = test_client.get("/api/config/not-a-section")
        assert response.status_code == 404
        assert config_path.read_text(encoding="utf-8") == before


class TestCoverRoutes:
    """Cover lookups that fail before any PDF renderer starts, plus a mocked regenerate."""

    def test_cover_404_when_periodical_is_missing(self, test_client):
        response = test_client.get("/api/periodicals/99999/cover")
        assert response.status_code == 404
        assert response.json()["detail"] == "Magazine not found"

    def test_cover_404_when_cover_file_is_missing(self, test_client, test_db, tmp_path):
        missing_cover = tmp_path / "does-not-exist.jpg"
        periodical_id = _insert_periodical(test_db, cover_path=str(missing_cover), file_path=str(tmp_path / "a.pdf"))
        response = test_client.get(f"/api/periodicals/{periodical_id}/cover")
        assert response.status_code == 404
        assert response.json()["detail"] == "Cover file not found"

        unset = _insert_periodical(test_db, cover_path=None, file_path=str(tmp_path / "b.pdf"))
        missing_path = test_client.get(f"/api/periodicals/{unset}/cover")
        assert missing_path.status_code == 404
        assert missing_path.json()["detail"] == "Cover not found"

    def test_regenerate_cover_uses_mocked_generator(self, test_client, test_db, tmp_path):
        pdf_path = tmp_path / "wired-2024-06.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        periodical_id = _insert_periodical(test_db, file_path=str(pdf_path), cover_path=None)
        generated = tmp_path / "library" / ".covers" / "wired-2024-06.jpg"

        with (
            patch("web.routers.periodicals.covers.OCRService.is_available", return_value=False),
            patch(
                "web.routers.periodicals.covers.extract_cover_from_pdf",
                return_value=generated,
            ) as generator,
        ):
            response = test_client.post(
                f"/api/periodicals/{periodical_id}/regenerate-cover",
                json={"page_number": 2},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["cover_path"] == str(generated)
        assert "page 2" in body["message"]
        generator.assert_called_once()
        assert generator.call_args.kwargs["page_number"] == 2

        session = _session(test_db)
        row = session.query(Periodical).filter(Periodical.id == periodical_id).one()
        assert row.cover_path == str(generated)
        assert row.extra_metadata["cover_page"] == 2
        session.close()


class TestDownloadOperationRoutes:
    """List, fetch, and 404 download submissions created for user 1."""

    def test_list_and_get_submission(self, test_client, test_db):
        tracking_id = _insert_tracking(test_db)
        submission_id = _insert_submission(
            test_db,
            tracking_id,
            result_title="National Geographic 2024-06",
            status=DownloadSubmission.StatusEnum.COMPLETED,
        )

        listed = test_client.get("/api/downloads/queue")
        assert listed.status_code == 200
        body = listed.json()
        assert body["success"] is True
        assert body["count"] == 1
        item = body["queue"][0]
        assert item["submission_id"] == submission_id
        assert item["title"] == "National Geographic 2024-06"
        assert item["status"] == "completed"
        assert item["periodical"] == "National Geographic"
        assert item["tracking_id"] == tracking_id

        fetched = test_client.get(f"/api/downloads/status/{tracking_id}")
        assert fetched.status_code == 200
        fetched_body = fetched.json()
        assert fetched_body["count"] == 1
        assert fetched_body["periodical"] == "National Geographic"
        assert fetched_body["submissions"][0]["submission_id"] == submission_id
        assert fetched_body["submissions"][0]["title"] == "National Geographic 2024-06"
        assert fetched_body["submissions"][0]["status"] == "completed"

    def test_missing_submission_and_tracking_return_404(self, test_client):
        missing = test_client.delete("/api/downloads/queue/99999")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Submission not found"

        missing_tracking = test_client.get("/api/downloads/status/99999")
        assert missing_tracking.status_code == 404
        assert missing_tracking.json()["detail"] == "Tracking record not found"

    def test_delete_submission_removes_the_row(self, test_client, test_db):
        tracking_id = _insert_tracking(test_db, olid="OL2W", title="Wired")
        submission_id = _insert_submission(test_db, tracking_id, result_title="Wired July")

        response = test_client.delete(f"/api/downloads/queue/{submission_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert "Wired July" in response.json()["message"]

        session = _session(test_db)
        assert session.query(DownloadSubmission).count() == 0
        session.close()

    def test_retry_calls_manager_and_missing_id_is_404(self, test_client, test_db, download_manager):
        missing = test_client.post("/api/downloads/queue/retry/99999")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Submission not found"
        download_manager.retry_submission.assert_not_called()

        tracking_id = _insert_tracking(test_db, olid="OL3W", title="Time")
        submission_id = _insert_submission(
            test_db,
            tracking_id,
            result_title="Time 2024",
            status=DownloadSubmission.StatusEnum.FAILED,
        )
        response = test_client.post(f"/api/downloads/queue/retry/{submission_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["submission_id"] == submission_id
        assert body["message"] == "Retry submitted"
        download_manager.retry_submission.assert_called_once()
        assert download_manager.retry_submission.call_args.args[0] == submission_id

    def test_clear_failed_deletes_only_failed_rows(self, test_client, test_db):
        tracking_id = _insert_tracking(test_db, olid="OL4W", title="Economist")
        failed_id = _insert_submission(
            test_db,
            tracking_id,
            result_title="Economist failed",
            status=DownloadSubmission.StatusEnum.FAILED,
            source_url="http://example.test/failed.nzb",
        )
        kept_id = _insert_submission(
            test_db,
            tracking_id,
            result_title="Economist kept",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.test/kept.nzb",
        )

        response = test_client.delete("/api/downloads/queue/failed")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["deleted"] == 1

        session = _session(test_db)
        remaining = {row.id for row in session.query(DownloadSubmission).all()}
        session.close()
        assert failed_id not in remaining
        assert remaining == {kept_id}


class TestTrackingCrudRoutes:
    """List, fetch, and delete periodical tracking rows."""

    def test_list_get_delete_and_missing_id(self, test_client, test_db):
        empty = test_client.get("/api/periodicals/tracking")
        assert empty.status_code == 200
        assert empty.json()["success"] is True
        assert empty.json()["total"] == 0
        assert empty.json()["tracked_periodicals"] == []

        tracking_id = _insert_tracking(test_db)
        listed = test_client.get("/api/periodicals/tracking")
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] == 1
        item = body["tracked_periodicals"][0]
        assert item["id"] == tracking_id
        assert item["olid"] == "OL1W"
        assert item["title"] == "National Geographic"
        assert item["library_count"] == 0
        assert item["failed_count"] == 0

        fetched = test_client.get(f"/api/periodicals/tracking/{tracking_id}")
        assert fetched.status_code == 200
        tracking = fetched.json()["tracking"]
        assert tracking["id"] == tracking_id
        assert tracking["olid"] == "OL1W"
        assert tracking["title"] == "National Geographic"
        assert tracking["language"] == "English"

        missing = test_client.get("/api/periodicals/tracking/99999")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Tracking record not found"

        deleted = test_client.delete(f"/api/periodicals/tracking/{tracking_id}")
        assert deleted.status_code == 200
        assert deleted.json()["success"] is True
        assert deleted.json()["message"] == "Stopped tracking 'National Geographic'"

        session = _session(test_db)
        assert session.query(PeriodicalTracking).count() == 0
        session.close()

        missing_delete = test_client.delete("/api/periodicals/tracking/99999")
        assert missing_delete.status_code == 404
        assert missing_delete.json()["detail"] == "Tracking record not found"


class TestTaskTriggerRoutes:
    """Manual task triggers beyond the status route."""

    def test_run_download_monitor(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/run/download_monitor")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["task_name"] == "Auto-Import"
        task_mocks["download_monitor"].run.assert_awaited_once()

    def test_run_auto_download(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/run/auto_download")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["task_name"] == "Auto-Download"
        task_mocks["scheduler"].run_task_now.assert_awaited_once_with("auto_download")

    def test_run_folder_cleanup(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/run/folder_cleanup")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["task_name"] == "Auto-Cleanup"
        assert "Deleted: 2" in body["message"]
        task_mocks["folder_cleanup"].run.assert_called_once()

    def test_run_cleanup_orphaned_covers(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/run/cleanup_orphaned_covers")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["task_name"] == "Auto-Thumbnail"
        task_mocks["scheduler"].run_task_now.assert_awaited_once_with("cleanup_orphaned_covers")

    def test_run_file_reorganizer(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/run/file_reorganizer")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["task_name"] == "Auto-Reorganize"
        task_mocks["scheduler"].run_task_now.assert_awaited_once_with("file_reorganizer")

    def test_run_auto_metadata_uses_mocked_service(self, test_client):
        stats = {
            "total_periodicals": 4,
            "metadata_cleaned": 1,
            "derived_metadata_backfilled": 2,
            "issue_date_synced": 1,
            "ocr_queued": 0,
            "text_scan_queued": 3,
            "errors": 0,
        }
        loader = MagicMock()
        loader.get_storage.return_value = {"db_path": "local/data/test.db", "library_dir": "/tmp/library"}
        loader.get_import.return_value = {"category_prefix": "_"}
        db_manager = MagicMock()
        service = MagicMock()
        service.run_full_scan.return_value = stats

        with (
            patch("core.config.ConfigLoader", return_value=loader),
            patch("core.database.DatabaseManager", return_value=db_manager),
            patch("services.auto_metadata.AutoMetadataService", return_value=service),
        ):
            response = test_client.post("/api/tasks/run/auto_metadata")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["task_name"] == "Auto-Metadata"
        assert body["stats"]["total_periodicals"] == 4
        assert body["stats"]["text_scan_queued"] == 3
        service.run_full_scan.assert_called_once()

    def test_unknown_task_name_returns_error(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/run/not-a-real-task")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["message"] == "Unknown task: not-a-real-task"
        task_mocks["download_monitor"].run.assert_not_called()
        task_mocks["scheduler"].run_task_now.assert_not_called()

    def test_toggle_task_persists_enabled_flag(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/auto_download/toggle")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["task_id"] == "auto_download"
        assert body["enabled"] is False
        task_mocks["scheduler"].set_task_enabled.assert_called_once_with("auto_download", False)
        saved = task_mocks["config_loader"].save_config.call_args.args[0]
        assert saved["tasks"]["auto_download_enabled"] is False

    def test_toggle_unknown_task_returns_error(self, test_client, task_mocks):
        response = test_client.post("/api/tasks/not-a-real-task/toggle")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["message"] == "Unknown task: not-a-real-task"
        task_mocks["scheduler"].set_task_enabled.assert_not_called()

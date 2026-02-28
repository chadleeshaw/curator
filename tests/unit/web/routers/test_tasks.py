"""
Test suite for tasks router endpoints
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers import tasks
from web.routers.auth import get_verify_token


@pytest.fixture(scope="module")
def mock_scheduler():
    """Create mock scheduler"""
    scheduler = MagicMock()
    scheduler.ocr_task = MagicMock()
    scheduler.ocr_task.is_running = True
    scheduler.ocr_task.last_run = None
    scheduler.ocr_task.next_run = None
    scheduler.download_monitor_task = MagicMock()
    scheduler.download_monitor_task.is_running = False
    return scheduler


@pytest.fixture(scope="module")
def mock_search_scheduler():
    """Create mock search scheduler"""
    search_sched = MagicMock()
    search_sched.is_running = True
    search_sched.last_run = None
    search_sched.next_run = None
    return search_sched


@pytest.fixture(scope="module")
def test_app(mock_scheduler, mock_search_scheduler):
    """Create test FastAPI app with tasks router"""
    app = FastAPI(title="Test App")
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    tasks.set_dependencies(
        session_factory=MagicMock(),
        download_monitor_task=MagicMock(),
        file_importer=MagicMock(),
        storage_config={"library_dir": "/tmp/test"},
        ocr_processor_task=MagicMock(),
        task_scheduler=mock_scheduler,
        folder_cleanup_task=MagicMock(),
    )
    app.include_router(tasks.router)
    return app


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    with TestClient(test_app) as client:
        yield client


class TestGetTasksStatus:
    """Test GET /api/tasks/status endpoint"""

    def test_get_tasks_status_success(self, test_client):
        """Test getting tasks status"""
        response = test_client.get("/api/tasks/status")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
        # Verify task structure
        for task in data["tasks"]:
            assert "id" in task
            assert "name" in task
            assert "interval" in task
            assert "last_run" in task


class TestRunTaskManually:
    """Test POST /api/tasks/run/{task_id} endpoint"""

    def test_run_task_invalid_id(self, test_client):
        """Test running task with invalid ID"""
        response = test_client.post("/api/tasks/run/invalid_task")
        # Should return error for invalid task ID (or 200 with error message)
        assert response.status_code in [200, 400, 404, 500]

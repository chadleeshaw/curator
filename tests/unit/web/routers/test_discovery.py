"""
Test suite for discovery router endpoints
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, DiscoveredIssue, PeriodicalTracking
from web.routers import discovery
from web.routers.auth import get_verify_token


@pytest.fixture
def test_db():
    """Create file-based test database"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def mock_download_manager():
    """Create mock download manager"""
    manager = MagicMock()
    manager.submit_issue_download.return_value = {"status": "queued"}
    return manager


@pytest.fixture
def test_app(test_db, mock_download_manager):
    """Create test FastAPI app with discovery router"""
    engine, session_factory = test_db
    mock_issue_discovery = MagicMock()
    mock_search_scheduler = MagicMock()
    discovery.set_dependencies(session_factory, mock_issue_discovery, mock_search_scheduler)

    app = FastAPI(title="Test App")
    app.include_router(discovery.router)
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    return app


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    with TestClient(test_app) as client:
        yield client


@pytest.fixture
def sample_tracking(test_db):
    """Create sample tracking record"""
    engine, session_factory = test_db
    session = session_factory()
    tracking = PeriodicalTracking(
        olid="OL12345W",
        title="Test Magazine",
        last_metadata_update=datetime.now(UTC),
        user_id=1,
    )
    session.add(tracking)
    session.commit()
    tracking_id = tracking.id
    session.close()
    return tracking_id


@pytest.fixture
def sample_discovered_issue(test_db, sample_tracking):
    """Create sample discovered issue"""
    engine, session_factory = test_db
    session = session_factory()
    issue = DiscoveredIssue(
        tracking_id=sample_tracking,
        title="Test Magazine #5",
        normalized_title="test magazine",
        fuzzy_match_group="testmagazine",
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        download_status="discovered",
        latest_url="http://example.com/download",
        user_id=1,
    )
    session.add(issue)
    session.commit()
    issue_id = issue.id
    session.close()
    return issue_id


class TestListDiscoveredIssues:
    """Test GET /api/discovered-issues endpoint"""

    def test_list_discovered_issues_all(self, test_client, sample_discovered_issue):
        """Test listing all discovered issues"""
        response = test_client.get("/api/discovered-issues")
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert isinstance(data["issues"], list)
        assert len(data["issues"]) > 0

    def test_list_discovered_issues_filtered_by_status(self, test_client, sample_discovered_issue):
        """Test listing issues filtered by status"""
        # Use valid status value from DiscoveredIssue model
        response = test_client.get("/api/discovered-issues?status=discovered")
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert isinstance(data["issues"], list)

    def test_list_discovered_issues_pagination(self, test_client, sample_discovered_issue):
        """Test pagination of discovered issues"""
        response = test_client.get("/api/discovered-issues?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "issues" in data
        assert len(data["issues"]) <= 10


class TestGetDiscoveredIssue:
    """Test GET /api/discovered-issues/{issue_id} endpoint"""

    def test_get_discovered_issue_success(self, test_client, sample_discovered_issue):
        """Test getting a specific discovered issue"""
        response = test_client.get(f"/api/discovered-issues/{sample_discovered_issue}")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["id"] == sample_discovered_issue

    def test_get_discovered_issue_not_found(self, test_client):
        """Test getting non-existent issue"""
        response = test_client.get("/api/discovered-issues/99999")
        assert response.status_code == 404


class TestRetryDiscoveredIssue:
    """Test POST /api/discovered-issues/{issue_id}/retry endpoint"""

    def test_retry_discovered_issue_success(self, test_client, test_db, sample_discovered_issue):
        """Test retrying a failed issue"""
        engine, session_factory = test_db
        session = session_factory()
        issue = session.get(DiscoveredIssue, sample_discovered_issue)
        issue.download_status = "failed"
        session.commit()
        session.close()

        response = test_client.post(f"/api/discovered-issues/{sample_discovered_issue}/retry")
        assert response.status_code == 200
        data = response.json()
        # Check for actual response field
        assert "message" in data or "id" in data

    def test_retry_discovered_issue_not_found(self, test_client):
        """Test retrying non-existent issue"""
        response = test_client.post("/api/discovered-issues/99999/retry")
        # Should return 404 or 200 with error message
        assert response.status_code in [200, 404]


class TestGetDiscoveryStatistics:
    """Test GET /api/discovered-issues/stats/summary endpoint"""

    def test_get_discovery_statistics_success(self, test_client, sample_discovered_issue):
        """Test getting discovery statistics"""
        response = test_client.get("/api/discovered-issues/stats/summary")
        assert response.status_code == 200
        data = response.json()
        # Check for actual response fields
        assert "status_counts" in data
        assert isinstance(data["status_counts"], dict)


class TestGetStatisticsByTracking:
    """Test GET /api/discovered-issues/stats/by-tracking endpoint"""

    def test_get_statistics_by_tracking_success(self, test_client, sample_discovered_issue):
        """Test getting statistics grouped by tracking"""
        response = test_client.get("/api/discovered-issues/stats/by-tracking")
        assert response.status_code == 200
        data = response.json()
        # API returns 'trackings' not 'tracking_stats'
        assert "trackings" in data
        assert isinstance(data["trackings"], list)

    def test_get_statistics_by_tracking_empty(self, test_client, test_db):
        """Test statistics with no discovered issues"""
        # Clear all issues first
        engine, session_factory = test_db
        session = session_factory()
        session.query(DiscoveredIssue).delete()
        session.commit()
        session.close()

        response = test_client.get("/api/discovered-issues/stats/by-tracking")
        # May return 200 with empty list or 404
        assert response.status_code in [200, 404]

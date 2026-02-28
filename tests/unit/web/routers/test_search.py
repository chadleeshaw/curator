"""
Test suite for search router endpoints
"""

# pylint: disable=redefined-outer-name  # pytest fixture injection pattern

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base
from web.routers import search
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
def mock_providers():
    """Create mock search providers"""
    provider = MagicMock()
    provider.search.return_value = [
        {
            "title": "National Geographic",
            "guid": "test-guid-1",
            "pubDate": "2024-01-01",
            "link": "http://example.com/download1",
        }
    ]
    return [provider]


@pytest.fixture
def test_app(test_db, mock_providers):
    """Create test FastAPI app with search router"""
    _engine, session_factory = test_db
    mock_title_matcher = MagicMock()
    search.set_dependencies(
        search_providers=mock_providers,
        metadata_providers=[],
        title_matcher=mock_title_matcher,
        session_factory=session_factory,
    )

    app = FastAPI(title="Test App")
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    app.include_router(search.router)
    return app


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    with TestClient(test_app) as client:
        yield client


class TestSearch:
    """Test POST /api/search endpoint"""

    def test_search_basic_success(self, test_client):
        """Test basic search functionality"""
        request_data = {
            "query": "National Geographic",
            "use_cache": False,
        }
        response = test_client.post("/api/search", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_with_cache(self, test_client):
        """Test search using cache"""
        request_data = {
            "query": "National Geographic",
            "use_cache": True,
        }
        response = test_client.post("/api/search", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_search_empty_query(self, test_client):
        """Test search with empty query"""
        request_data = {"query": ""}
        response = test_client.post("/api/search", json=request_data)
        # Should handle gracefully, either return empty results or error
        assert response.status_code in [200, 400]


class TestSearchPeriodicalProviders:
    """Test POST /api/search/periodicals/search-providers endpoint"""

    def test_search_providers_success(self, test_client):
        """Test searching periodical providers"""
        response = test_client.post("/api/periodicals/search-providers?query=National+Geographic")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_providers_with_filters(self, test_client):
        """Test searching with language and country filters"""
        response = test_client.post(
            "/api/periodicals/search-providers?query=National+Geographic&language=en&country=US"
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_search_providers_no_results(self, test_client, mock_providers):
        """Test search with no results"""
        mock_providers[0].search.return_value = []
        response = test_client.post("/api/periodicals/search-providers?query=NonExistentMagazine")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 0


class TestGetPeriodicalEditions:
    """Test GET /api/periodicals/issues/{magazine_title} endpoint"""

    def test_get_periodical_issues_success(self, test_client):
        """Test getting periodical issues"""
        response = test_client.get("/api/periodicals/issues/National+Geographic")
        assert response.status_code == 200
        data = response.json()
        # API returns 'results' not 'editions'
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_get_periodical_issues_missing_title(self, test_client):
        """Test getting issues without title parameter"""
        # GET endpoint requires title in path, so 404 is expected
        response = test_client.get("/api/periodicals/issues/")
        assert response.status_code in [404, 422]

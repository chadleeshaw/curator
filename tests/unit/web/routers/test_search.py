"""
Test suite for search router endpoints
"""

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
def mock_cache_service():
    """Create mock cache service"""
    cache = MagicMock()
    cache.search_cached_releases.return_value = []
    cache.get_cache_status.return_value = {
        "total_releases": 1000,
        "providers": [{"name": "provider1", "releases": 1000}],
    }
    return cache


@pytest.fixture
def test_app(test_db, mock_providers, mock_cache_service):
    """Create test FastAPI app with search router"""
    engine, session_factory = test_db
    mock_title_matcher = MagicMock()
    search.set_dependencies(
        search_providers=mock_providers,
        metadata_providers=[],
        title_matcher=mock_title_matcher,
        session_factory=session_factory,
        provider_cache_service=mock_cache_service,
    )

    app = FastAPI(title="Test App")
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
    """Test GET /api/periodicals/editions/{magazine_title} endpoint"""

    def test_get_periodical_editions_success(self, test_client, mock_cache_service):
        """Test getting periodical editions"""
        mock_cache_service.get_editions_for_title.return_value = [
            {"title": "National Geographic US", "country": "US"},
            {"title": "National Geographic UK", "country": "UK"},
        ]
        response = test_client.get("/api/periodicals/editions/National+Geographic")
        assert response.status_code == 200
        data = response.json()
        # API returns 'results' not 'editions'
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_get_periodical_editions_missing_title(self, test_client):
        """Test getting editions without title parameter"""
        # GET endpoint requires title in path, so 404 is expected
        response = test_client.get("/api/periodicals/editions/")
        assert response.status_code in [404, 422]


class TestGetProviderCacheStatus:
    """Test GET /api/indexer-cache/status endpoint"""

    def test_get_cache_status_success(self, test_client):
        """Test getting provider cache status"""
        response = test_client.get("/api/indexer-cache/status")
        assert response.status_code == 200
        data = response.json()
        # Check for actual response fields
        assert "enabled" in data
        assert isinstance(data, dict)

    def test_get_cache_status_structure(self, test_client):
        """Test cache status response structure"""
        response = test_client.get("/api/indexer-cache/status")
        assert response.status_code == 200
        data = response.json()
        # Verify actual response structure
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)

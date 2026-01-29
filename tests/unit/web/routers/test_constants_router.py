"""
Test suite for constants router endpoints
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers import constants_router


@pytest.fixture(scope="module")
def test_app():
    """Create test FastAPI app with constants router"""
    app = FastAPI(title="Test App")
    app.include_router(constants_router.router)
    return app


@pytest.fixture(scope="module")
def test_client(test_app):
    """Create test client"""
    with TestClient(test_app) as client:
        yield client


class TestGetSupportedLanguages:
    """Test GET /api/constants/languages endpoint"""

    def test_get_supported_languages_success(self, test_client):
        """Test getting supported languages"""
        response = test_client.get("/api/constants/languages")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert isinstance(data["languages"], list)
        assert "English" in data["languages"]


class TestGetCategories:
    """Test GET /api/constants/categories endpoint"""

    def test_get_categories_success(self, test_client):
        """Test getting categories"""
        response = test_client.get("/api/constants/categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert isinstance(data["categories"], list)
        assert len(data["categories"]) > 0


class TestGetIsoCountries:
    """Test GET /api/constants/countries endpoint"""

    def test_get_iso_countries_success(self, test_client):
        """Test getting ISO countries"""
        response = test_client.get("/api/constants/countries")
        assert response.status_code == 200
        data = response.json()
        assert "countries" in data
        assert isinstance(data["countries"], dict)
        assert "US" in data["countries"]


class TestGetAllConstants:
    """Test GET /api/constants endpoint"""

    def test_get_all_constants_success(self, test_client):
        """Test getting all constants"""
        response = test_client.get("/api/constants")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert "categories" in data
        assert "countries" in data
        assert isinstance(data["languages"], list)
        assert isinstance(data["categories"], list)
        assert isinstance(data["countries"], dict)


class TestGetSupportedLanguagesLegacy:
    """Test GET /api/metadata/languages endpoint (legacy)"""

    def test_get_supported_languages_legacy_success(self, test_client):
        """Test getting supported languages via legacy endpoint"""
        response = test_client.get("/api/metadata/languages")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert isinstance(data["languages"], list)


class TestGetSupportedCountries:
    """Test GET /api/metadata/countries endpoint"""

    def test_get_supported_countries_success(self, test_client):
        """Test getting supported countries"""
        response = test_client.get("/api/metadata/countries")
        assert response.status_code == 200
        data = response.json()
        assert "countries" in data
        assert isinstance(data["countries"], list)
        # Verify structure of country objects
        if len(data["countries"]) > 0:
            assert "code" in data["countries"][0]
            assert "name" in data["countries"][0]

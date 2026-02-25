"""
API Endpoint Performance Tests

Tests the performance of key API endpoints using pytest-benchmark.
Run with: .venv/bin/python -m pytest tests/performance/test_api_benchmarks.py --benchmark-only -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from fastapi.testclient import TestClient

from web.app import app


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app"""
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers(client):
    """
    Get authentication headers for protected endpoints.

    Note: This assumes you have a test user configured.
    If authentication fails, these tests will need credentials setup.
    """
    try:
        # Try to login with test credentials
        response = client.post(
            "/api/login", json={"username": "admin", "password": "admin"}
        )  # Default credentials
        if response.status_code == 200:
            token = response.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
    except Exception:
        pass

    # Return empty headers if auth fails (some endpoints may not require auth)
    return {}


class TestAPIBenchmarks:
    """Benchmark tests for API endpoints"""

    def test_version_endpoint(self, benchmark, client):
        """Benchmark the version endpoint (public, lightweight)"""

        def get_version():
            return client.get("/api/version")

        result = benchmark(get_version)
        assert result.status_code == 200

    def test_tasks_status(self, benchmark, client, auth_headers):
        """Benchmark task status endpoint"""

        def get_task_status():
            return client.get("/api/tasks/status", headers=auth_headers)

        result = benchmark(get_task_status)
        # May return 401 if auth not configured
        assert result.status_code in [200, 401]


class TestStaticAssetBenchmarks:
    """Benchmark tests for static asset serving"""

    def test_index_page(self, benchmark, client):
        """Benchmark serving the index page"""

        def get_index():
            return client.get("/")

        result = benchmark(get_index)
        # May redirect to login if not authenticated
        assert result.status_code in [200, 307]

    def test_login_page(self, benchmark, client):
        """Benchmark serving the login page"""

        def get_login():
            return client.get("/login.html")

        result = benchmark(get_login)
        assert result.status_code == 200

    def test_epub_reader_page(self, benchmark, client):
        """Benchmark serving the EPUB reader page (requires params)"""

        def get_epub_reader():
            return client.get("/epub-reader")

        result = benchmark(get_epub_reader)
        # 422 if required query params missing
        assert result.status_code in [200, 307, 422]

    def test_comic_reader_page(self, benchmark, client):
        """Benchmark serving the comic reader page (requires params)"""

        def get_comic_reader():
            return client.get("/comic-reader")

        result = benchmark(get_comic_reader)
        # 422 if required query params missing
        assert result.status_code in [200, 307, 422]

    def test_pdf_reader_page(self, benchmark, client):
        """Benchmark serving the PDF reader page (requires params)"""

        def get_pdf_reader():
            return client.get("/pdf-reader")

        result = benchmark(get_pdf_reader)
        # 422 if required query params missing
        assert result.status_code in [200, 307, 422]

    def test_periodical_page(self, benchmark, client):
        """Benchmark serving the periodical detail page (requires params)"""

        def get_periodical():
            return client.get("/periodical")

        result = benchmark(get_periodical)
        # 422 if required query params missing
        assert result.status_code in [200, 307, 422]

    def test_css_base(self, benchmark, client):
        """Benchmark serving base CSS file"""

        def get_css():
            return client.get("/static/css/base.css")

        result = benchmark(get_css)
        assert result.status_code == 200

    def test_css_components(self, benchmark, client):
        """Benchmark serving components CSS file"""

        def get_css():
            return client.get("/static/css/components.css")

        result = benchmark(get_css)
        assert result.status_code == 200


class TestConstantsAPI:
    """Benchmark tests for constants/config endpoints (no database needed)"""

    def test_constants_all(self, benchmark, client):
        """Benchmark fetching all constants"""

        def get_constants():
            return client.get("/api/constants")

        result = benchmark(get_constants)
        assert result.status_code == 200

    def test_constants_languages(self, benchmark, client):
        """Benchmark fetching language constants"""

        def get_languages():
            return client.get("/api/constants/languages")

        result = benchmark(get_languages)
        assert result.status_code == 200

    def test_constants_categories(self, benchmark, client):
        """Benchmark fetching category constants"""

        def get_categories():
            return client.get("/api/constants/categories")

        result = benchmark(get_categories)
        assert result.status_code == 200

    def test_constants_countries(self, benchmark, client):
        """Benchmark fetching country constants"""

        def get_countries():
            return client.get("/api/constants/countries")

        result = benchmark(get_countries)
        assert result.status_code == 200


class TestImportsAPI:
    """Benchmark tests for imports endpoints"""

    def test_imports_status(self, benchmark, client, auth_headers):
        """Benchmark imports status check (endpoint may not exist)"""

        def get_status():
            return client.get("/api/imports/status", headers=auth_headers)

        result = benchmark(get_status)
        # May return 401 if auth not configured, 404 if endpoint doesn't exist
        assert result.status_code in [200, 401, 404]


class TestErrorHandling:
    """Benchmark tests for error handling performance"""

    def test_404_response(self, benchmark, client):
        """Benchmark 404 error handling"""

        def get_nonexistent():
            return client.get("/api/nonexistent-endpoint")

        result = benchmark(get_nonexistent)
        assert result.status_code == 404

    def test_404_nested_path(self, benchmark, client):
        """Benchmark 404 error handling for nested paths"""

        def get_nonexistent():
            return client.get("/api/periodicals/99999999/nonexistent")

        result = benchmark(get_nonexistent)
        assert result.status_code == 404


class TestAuthenticationPOST:
    """Benchmark tests for POST request processing"""

    def test_login_invalid_credentials(self, benchmark, client):
        """Benchmark login with invalid credentials (endpoint may not exist)"""

        def post_login():
            return client.post(
                "/api/login", json={"username": "invalid", "password": "invalid"}
            )

        result = benchmark(post_login)
        # Should return 401 for invalid credentials, 404 if endpoint doesn't exist,
        # or 403 if CSRF middleware blocks the request before routing
        assert result.status_code in [401, 403, 404, 422]

    def test_login_missing_fields(self, benchmark, client):
        """Benchmark login with missing fields (endpoint may not exist)"""

        def post_login():
            return client.post("/api/login", json={})

        result = benchmark(post_login)
        # Should return 422 for validation error, 404 if endpoint doesn't exist,
        # or 403 if CSRF middleware blocks the request before routing
        assert result.status_code in [403, 404, 422]


if __name__ == "__main__":
    # Allow running directly for quick tests
    print(
        "Run with: .venv/bin/python -m pytest tests/performance/test_api_benchmarks.py --benchmark-only -v"
    )

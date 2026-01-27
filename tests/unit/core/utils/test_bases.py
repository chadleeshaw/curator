#!/usr/bin/env python3
"""
Test suite for core.bases module (abstract base classes)
"""

import sys
from pathlib import Path
from datetime import datetime

# Path setup handled by conftest.py

from core.interfaces import SearchResult, SearchProvider, DownloadClient


def test_search_result_initialization():
    """Test SearchResult dataclass initialization"""
    result = SearchResult(
        title="Test Magazine Issue 5",
        url="https://example.com/nzb/test",
        provider="TestProvider",
    )

    assert result.title == "Test Magazine Issue 5"
    assert result.url == "https://example.com/nzb/test"
    assert result.provider == "TestProvider"
    assert result.publication_date is None
    assert result.raw_metadata == {}


def test_search_result_with_metadata():
    """Test SearchResult with full metadata"""
    pub_date = datetime(2026, 1, 14)
    metadata = {"size": "100MB", "category": "magazines"}

    result = SearchResult(
        title="Test Magazine",
        url="https://example.com/nzb/test",
        provider="TestProvider",
        publication_date=pub_date,
        raw_metadata=metadata,
    )

    assert result.publication_date == pub_date
    assert result.raw_metadata == metadata
    assert result.raw_metadata["size"] == "100MB"


def test_search_result_post_init():
    """Test SearchResult __post_init__ sets empty dict for raw_metadata"""
    result = SearchResult(title="Test", url="https://example.com/nzb", provider="Test", raw_metadata=None)

    assert result.raw_metadata == {}
    assert isinstance(result.raw_metadata, dict)


def test_search_provider_abstract():
    """Test that SearchProvider cannot be instantiated directly"""
    config = {"name": "test", "type": "search"}

    try:
        provider = SearchProvider(config)
        # Try to call abstract method
        provider.search("query")
        assert False, "Should not be able to call abstract method"
    except TypeError:
        # Expected - abstract class cannot be instantiated
        pass


def test_search_provider_concrete_implementation():
    """Test a concrete implementation of SearchProvider"""

    class TestProvider(SearchProvider):
        def search(self, query, category=None):
            return [
                SearchResult(
                    title=f"Result for {query}",
                    url="https://example.com/nzb",
                    provider=self.name,
                )
            ]

    config = {"name": "TestProvider", "type": "search", "enabled": True}
    provider = TestProvider(config)

    assert provider.name == "TestProvider"
    assert provider.type == "search"

    results = provider.search("test query")
    assert len(results) == 1
    assert results[0].title == "Result for test query"


def test_search_provider_get_provider_info():
    """Test SearchProvider get_provider_info method"""

    class TestProvider(SearchProvider):
        def search(self, query, category=None):
            return []

    config = {"name": "TestProv", "type": "newsnab", "enabled": True}
    provider = TestProvider(config)

    info = provider.get_provider_info()

    assert info["type"] == "newsnab"
    assert info["name"] == "TestProv"
    assert info["enabled"] is True


def test_download_client_abstract():
    """Test that DownloadClient cannot be instantiated directly"""
    config = {"name": "test", "type": "download_client"}

    try:
        client = DownloadClient(config)
        # Try to call abstract method
        client.submit("url")
        assert False, "Should not be able to call abstract method"
    except TypeError:
        # Expected - abstract class cannot be instantiated
        pass


def test_download_client_concrete_implementation():
    """Test a concrete implementation of DownloadClient"""

    class TestClient(DownloadClient):
        def submit(self, nzb_url, title=None, category=None):
            return "job_123"

        def get_status(self, job_id):
            return {"status": "completed", "progress": 100}

        def get_completed_downloads(self):
            return [{"job_id": "job_123", "file_path": "/downloads/test"}]

        def delete(self, job_id):
            return True

    config = {"name": "TestClient", "type": "download_client"}
    client = TestClient(config)

    assert client.name == "TestClient"
    assert client.type == "download_client"

    job_id = client.submit("https://example.com/nzb")
    assert job_id == "job_123"

    status = client.get_status("job_123")
    assert status["status"] == "completed"
    assert status["progress"] == 100

    downloads = client.get_completed_downloads()
    assert len(downloads) == 1
    assert downloads[0]["job_id"] == "job_123"

    deleted = client.delete("job_123")
    assert deleted is True


def test_download_client_default_values():
    """Test DownloadClient default name and type"""

    class MyClient(DownloadClient):
        def submit(self, nzb_url, title=None, category=None):
            return "id"

        def get_status(self, job_id):
            return {}

        def get_completed_downloads(self):
            return []

        def delete(self, job_id):
            return True

    config = {}  # No name or type provided
    client = MyClient(config)

    # Should use class name as default
    assert client.name == "MyClient"
    assert client.type == "unknown"


def test_search_provider_default_values():
    """Test SearchProvider default name and type"""

    class MyProvider(SearchProvider):
        def search(self, query, category=None):
            return []

    config = {}  # No name or type provided
    provider = MyProvider(config)

    assert provider.name == "MyProvider"
    assert provider.type == "unknown"

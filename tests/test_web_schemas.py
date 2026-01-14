#!/usr/bin/env python3
"""
Test suite for web.schemas module
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.schemas import (
    SearchRequest,
    DownloadSingleIssueRequest,
    APIResponse
)


def test_search_request_schema():
    """Test SearchRequest schema"""
    request = SearchRequest(query="test magazine", mode="automatic")

    assert request.query == "test magazine"
    assert request.mode == "automatic"


def test_search_request_minimal():
    """Test SearchRequest with minimal data"""
    request = SearchRequest(query="test")

    assert request.query == "test"
    # mode has a default value


def test_download_single_issue_request_schema():
    """Test DownloadSingleIssueRequest schema"""
    request = DownloadSingleIssueRequest(
        tracking_id=1,
        title="Test Magazine",
        url="https://example.com/nzb"
    )

    assert request.tracking_id == 1
    assert request.title == "Test Magazine"
    assert request.url == "https://example.com/nzb"


def test_download_request_url_validation():
    """Test DownloadSingleIssueRequest validates URL format"""
    # Should accept valid URLs
    request = DownloadSingleIssueRequest(tracking_id=1, title="Test", url="https://example.com/nzb")
    assert request.url.startswith("http")


def test_api_response_schema():
    """Test APIResponse schema"""
    response = APIResponse(
        success=True,
        message="Operation successful",
        data={"id": 123}
    )

    assert response.success is True
    assert response.message == "Operation successful"
    assert response.data == {"id": 123}


def test_api_response_minimal():
    """Test APIResponse with minimal data"""
    response = APIResponse(message="OK")

    assert response.success is True  # Default value
    assert response.message == "OK"

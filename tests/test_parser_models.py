#!/usr/bin/env python3
"""
Test suite for core.parsers.models module
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.models import (
    ParsedMetadata,
    ParsedFilename,
    ParsedFilepath,
    ParsedSearchResult,
    ParsedDownloadFile
)


def test_parsed_metadata_initialization():
    """Test ParsedMetadata dataclass initialization"""
    metadata = ParsedMetadata(
        title="Time Magazine",
        issue_number=123,
        year=2026,
        month=1
    )

    assert metadata.title == "Time Magazine"
    assert metadata.issue_number == 123
    assert metadata.year == 2026
    assert metadata.month == 1


def test_parsed_metadata_optional_fields():
    """Test ParsedMetadata with optional fields"""
    metadata = ParsedMetadata(
        title="National Geographic",
        volume=5,
        language="English",
        country="US"
    )

    assert metadata.title == "National Geographic"
    assert metadata.volume == 5
    assert metadata.language == "English"
    assert metadata.country == "US"


def test_parsed_metadata_minimal():
    """Test ParsedMetadata with minimal data"""
    metadata = ParsedMetadata(title="Test")

    assert metadata.title == "Test"
    assert metadata.language == "English"  # Default value
    assert metadata.issue_number is None


def test_parsed_filename_initialization():
    """Test ParsedFilename dataclass"""
    parsed = ParsedFilename(
        title="Magazine",
        issue_number=1,
        year=2026
    )

    assert parsed.title == "Magazine"
    assert parsed.issue_number == 1
    assert parsed.year == 2026


def test_parsed_filepath_initialization():
    """Test ParsedFilepath dataclass"""
    parsed = ParsedFilepath(
        title_from_path="Time Magazine",
        language_from_path="English",
        year_from_path=2026
    )

    assert parsed.title_from_path == "Time Magazine"
    assert parsed.language_from_path == "English"
    assert parsed.year_from_path == 2026


def test_parsed_search_result_initialization():
    """Test ParsedSearchResult dataclass"""
    result = ParsedSearchResult(
        title="Wired Issue 5",
        original_title="Wired Issue 5",
        cleaned_title="wired issue 5",
        base_title="wired",
        language="English",
        country=None,
        is_special_edition=False,
        special_edition_name=None,
        publication_date=datetime(2026, 1, 14),
        provider="TestProvider",
        url="https://example.com/nzb/123"
    )

    assert result.title == "Wired Issue 5"
    assert result.url == "https://example.com/nzb/123"
    assert result.provider == "TestProvider"
    assert result.publication_date.year == 2026


def test_parsed_search_result_minimal():
    """Test ParsedSearchResult with minimal data"""
    result = ParsedSearchResult(
        title="Magazine",
        original_title="Magazine",
        cleaned_title="magazine",
        base_title="magazine",
        language="English",
        country=None,
        is_special_edition=False,
        special_edition_name=None,
        publication_date=None,
        provider="Provider",
        url="https://example.com/nzb"
    )

    assert result.title == "Magazine"
    assert result.url == "https://example.com/nzb"
    assert result.provider == "Provider"


def test_parsed_download_file_initialization():
    """Test ParsedDownloadFile dataclass"""
    download = ParsedDownloadFile(
        file_path=Path("/downloads/magazine.pdf"),
        title="Magazine Issue 5",
        cleaned_title="magazine issue 5",
        language="English",
        country=None,
        issue_date=datetime(2026, 1, 14)
    )

    assert download.file_path == Path("/downloads/magazine.pdf")
    assert download.title == "Magazine Issue 5"
    assert download.cleaned_title == "magazine issue 5"
    assert download.language == "English"


def test_parsed_models_are_dataclasses():
    """Test that parser models are proper dataclasses"""
    from dataclasses import is_dataclass

    assert is_dataclass(ParsedMetadata)
    assert is_dataclass(ParsedFilename)
    assert is_dataclass(ParsedFilepath)
    assert is_dataclass(ParsedSearchResult)
    assert is_dataclass(ParsedDownloadFile)


def test_parsed_metadata_with_date():
    """Test ParsedMetadata with date field"""
    date = datetime(2026, 1, 14)
    metadata = ParsedMetadata(
        title="Test Magazine",
        publication_date=date
    )

    assert metadata.publication_date == date
    assert metadata.publication_date.year == 2026
    assert metadata.publication_date.month == 1


def test_parsed_filename_without_extension():
    """Test ParsedFilename without issue number"""
    parsed = ParsedFilename(
        title="Magazine"
    )

    assert parsed.title == "Magazine"
    assert parsed.issue_number is None


def test_parsed_search_result_with_special_edition():
    """Test ParsedSearchResult with special edition"""
    result = ParsedSearchResult(
        title="Comic Book Special",
        original_title="Comic Book Special",
        cleaned_title="comic book special",
        base_title="comic book",
        language="English",
        country=None,
        is_special_edition=True,
        special_edition_name="Anniversary Edition",
        publication_date=None,
        provider="Provider",
        url="https://example.com/nzb"
    )

    assert result.is_special_edition is True
    assert result.special_edition_name == "Anniversary Edition"


def test_parsed_download_file_attributes():
    """Test ParsedDownloadFile has expected attributes"""
    download = ParsedDownloadFile(
        file_path=Path("/test/magazine.pdf"),
        title="Test Magazine",
        cleaned_title="test magazine",
        language="English",
        country=None,
        issue_date=None
    )

    assert download.title == "Test Magazine"
    assert download.cleaned_title == "test magazine"
    assert download.language == "English"
    assert download.source == "download_client"  # Default value

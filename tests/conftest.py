"""
Shared pytest fixtures for all tests.

This file contains common fixtures used across unit, integration, and e2e tests.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

# Ensure project root is in path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Common Fixtures
# =============================================================================


@pytest.fixture
def tmpdir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def mock_session_factory():
    """Create a mock SQLAlchemy session factory."""
    mock_factory = Mock()
    mock_session = Mock()
    mock_factory.return_value = mock_session
    return mock_factory


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy session."""
    return Mock()


@pytest.fixture
def fixtures_dir():
    """Get the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_pdf_path(fixtures_dir):
    """Get path to sample PDF file for testing."""
    return str(fixtures_dir / "pdf" / "NationalGeographic 2000-01.pdf")


@pytest.fixture
def sample_epub_path(fixtures_dir):
    """Get path to sample EPUB file for testing."""
    return str(fixtures_dir / "epub" / "sample-book.epub")


@pytest.fixture
def sample_png_magazine(fixtures_dir):
    """Get path to sample magazine PNG for testing."""
    return str(fixtures_dir / "png" / "magazine.png")


@pytest.fixture
def sample_png_comic(fixtures_dir):
    """Get path to sample comic PNG for testing."""
    return str(fixtures_dir / "png" / "comic.png")


# =============================================================================
# Pytest Hooks
# =============================================================================


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (multiple components)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (full workflows)")
    config.addinivalue_line("markers", "slow: Tests that take a long time to run")

"""
Tests for version management
"""

import json
from pathlib import Path
from unittest.mock import patch
import subprocess

from core.version import get_version, get_version_info


def test_get_version_from_git():
    """Test getting version from git tags"""
    # Mock successful git command
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v3.14.2\n"

        version = get_version()
        assert version == "v3.14.2"


def test_get_version_from_git_dev():
    """Test getting development version from git (commits after tag)"""
    # Clear cache first
    get_version.cache_clear()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v3.14.2-5-g1a2b3c4\n"

        version = get_version()
        assert version == "v3.14.2-5-g1a2b3c4"

        # Clear cache for next test
        get_version.cache_clear()

        info = get_version_info()
        assert info["is_dev"] is True


def test_get_version_from_package_json():
    """Test fallback to package.json when git is not available"""
    with patch("subprocess.run") as mock_run:
        # Simulate git not available
        mock_run.side_effect = FileNotFoundError()

        # Clear cache
        get_version.cache_clear()

        version = get_version()
        # Should get version from package.json
        assert version.startswith("v")


def test_get_version_info():
    """Test getting detailed version information"""
    info = get_version_info()

    assert "version" in info
    assert "is_dev" in info
    assert isinstance(info["version"], str)
    assert isinstance(info["is_dev"], bool)


def test_version_cache():
    """Test that version is cached"""
    # Clear cache first
    get_version.cache_clear()

    # First call
    version1 = get_version()

    # Second call should be cached
    with patch("subprocess.run") as mock_run:
        version2 = get_version()
        # subprocess.run should not be called because result is cached
        mock_run.assert_not_called()

    assert version1 == version2

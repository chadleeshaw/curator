"""
Tests for version management
"""

from unittest.mock import patch

from core.version import get_build_hash, get_version, get_version_info


def test_get_version_from_git():
    """Test getting version from git tags"""
    # Clear cache first
    get_version.cache_clear()

    # Mock successful git command
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v3.14.2\n"

        version = get_version()
        assert version == "v3.14.2"


def test_get_version_from_git_returns_tag_only():
    """Test that get_version returns just the tag name, not the full describe string"""
    # Clear cache first
    get_version.cache_clear()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "v3.14.2\n"

        version = get_version()
        # --abbrev=0 returns just the tag, not v3.14.2-5-g1a2b3c4
        assert version == "v3.14.2"


def test_get_version_info_is_dev():
    """Test that is_dev is True when HEAD is ahead of the tag"""
    from unittest.mock import MagicMock

    get_version.cache_clear()
    get_build_hash.cache_clear()

    # Mock subprocess.run to return different results for different commands
    def mock_run_side_effect(cmd, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        if "--abbrev=0" in cmd:
            # get_version: just the tag
            mock_result.stdout = "v3.14.2\n"
        elif "rev-parse" in cmd:
            # get_build_hash: commit hash
            mock_result.stdout = "1a2b3c4\n"
        elif "--always" in cmd:
            # get_version_info is_dev check: full describe (ahead of tag)
            mock_result.stdout = "v3.14.2-5-g1a2b3c4\n"
        return mock_result

    with patch("subprocess.run", side_effect=mock_run_side_effect):
        info = get_version_info()
        assert info["version"] == "v3.14.2"
        assert info["build_hash"] == "1a2b3c4"
        assert info["is_dev"] is True


def test_get_version_info_not_dev_on_tag():
    """Test that is_dev is False when HEAD is exactly on the tag"""
    from unittest.mock import MagicMock

    get_version.cache_clear()
    get_build_hash.cache_clear()

    def mock_run_side_effect(cmd, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        if "--abbrev=0" in cmd:
            mock_result.stdout = "v3.14.2\n"
        elif "rev-parse" in cmd:
            mock_result.stdout = "abc1234\n"
        elif "--always" in cmd:
            # HEAD is exactly on the tag
            mock_result.stdout = "v3.14.2\n"
        return mock_result

    with patch("subprocess.run", side_effect=mock_run_side_effect):
        info = get_version_info()
        assert info["version"] == "v3.14.2"
        assert info["is_dev"] is False


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
    assert "build_hash" in info
    assert isinstance(info["version"], str)
    assert isinstance(info["is_dev"], bool)
    assert isinstance(info["build_hash"], str)


def test_get_build_hash():
    """Test getting git commit hash"""
    # Clear cache first
    get_build_hash.cache_clear()

    # Mock successful git command
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "a9f1a15\n"

        build_hash = get_build_hash()
        assert build_hash == "a9f1a15"


def test_get_build_hash_fallback():
    """Test build hash fallback when git is not available"""
    # Clear cache first
    get_build_hash.cache_clear()

    with patch("subprocess.run") as mock_run:
        # Simulate git not available
        mock_run.side_effect = FileNotFoundError()

        build_hash = get_build_hash()
        assert build_hash == "unknown"


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

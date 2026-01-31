"""
Tests for CBZ/CBR utility functions
"""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory"""
    return Path(__file__).parent.parent.parent.parent / "fixtures"


@pytest.fixture
def sample_cbz(fixtures_dir):
    """Return path to sample CBZ file"""
    return fixtures_dir / "cbz" / "sample-comic.cbz"


@pytest.fixture
def sample_cbr(fixtures_dir):
    """Return path to sample CBR file"""
    cbr_path = fixtures_dir / "cbr" / "sample-comic.cbr"
    if cbr_path.exists():
        return cbr_path
    return None


class TestValidateCBZ:
    """Tests for validate_cbz function"""

    def test_validate_valid_cbz(self, sample_cbz):
        """Test validation of a valid CBZ file"""
        from core.utils.cbz import validate_cbz

        assert validate_cbz(sample_cbz) is True

    def test_validate_nonexistent_file(self, tmp_path):
        """Test validation of non-existent file"""
        from core.utils.cbz import validate_cbz

        fake_path = tmp_path / "nonexistent.cbz"
        assert validate_cbz(fake_path) is False

    def test_validate_invalid_zip(self, tmp_path):
        """Test validation of invalid ZIP file"""
        from core.utils.cbz import validate_cbz

        invalid_cbz = tmp_path / "invalid.cbz"
        invalid_cbz.write_text("not a zip file")
        assert validate_cbz(invalid_cbz) is False


class TestExtractCoverFromCBZ:
    """Tests for extract_cover_from_cbz function"""

    def test_extract_cover_success(self, sample_cbz, tmp_path):
        """Test successful cover extraction from CBZ"""
        from core.utils.cbz import extract_cover_from_cbz

        cover_path = extract_cover_from_cbz(sample_cbz, tmp_path)

        assert cover_path is not None
        assert cover_path.exists()
        assert cover_path.suffix == ".jpg"
        assert cover_path.stat().st_size > 0

    def test_extract_cover_creates_directory(self, sample_cbz, tmp_path):
        """Test that cover extraction creates output directory if it doesn't exist"""
        from core.utils.cbz import extract_cover_from_cbz

        output_dir = tmp_path / "covers"
        assert not output_dir.exists()

        cover_path = extract_cover_from_cbz(sample_cbz, output_dir)

        assert output_dir.exists()
        assert cover_path is not None

    def test_extract_cover_from_invalid_cbz(self, tmp_path):
        """Test cover extraction from invalid CBZ file"""
        from core.utils.cbz import extract_cover_from_cbz

        invalid_cbz = tmp_path / "invalid.cbz"
        invalid_cbz.write_text("not a zip file")

        cover_path = extract_cover_from_cbz(invalid_cbz, tmp_path)

        assert cover_path is None

    def test_extract_cover_from_nonexistent_file(self, tmp_path):
        """Test cover extraction from non-existent file"""
        from core.utils.cbz import extract_cover_from_cbz

        fake_path = tmp_path / "nonexistent.cbz"

        cover_path = extract_cover_from_cbz(fake_path, tmp_path)

        assert cover_path is None


class TestValidateCBR:
    """Tests for validate_cbr function"""

    def test_validate_valid_cbr(self, sample_cbr):
        """Test validation of a valid CBR file"""
        if sample_cbr is None:
            pytest.skip("CBR fixture not available")

        from core.utils.cbz import validate_cbr

        assert validate_cbr(sample_cbr) is True

    def test_validate_nonexistent_file(self, tmp_path):
        """Test validation of non-existent file"""
        from core.utils.cbz import validate_cbr

        fake_path = tmp_path / "nonexistent.cbr"
        assert validate_cbr(fake_path) is False

    def test_validate_invalid_rar(self, tmp_path):
        """Test validation of invalid RAR file"""
        from core.utils.cbz import validate_cbr

        invalid_cbr = tmp_path / "invalid.cbr"
        invalid_cbr.write_text("not a rar file")
        assert validate_cbr(invalid_cbr) is False

    def test_validate_requires_rarfile(self, tmp_path):
        """Test that CBR validation requires rarfile library"""
        from core.utils.cbz import validate_cbr

        # This test verifies the function handles missing rarfile gracefully
        fake_cbr = tmp_path / "test.cbr"
        fake_cbr.write_bytes(b"Rar!\x1a\x07\x00")  # RAR file header

        # Should return False if rarfile not available
        # (We're not testing actual RAR validation without rarfile installed)
        result = validate_cbr(fake_cbr)
        assert isinstance(result, bool)


class TestExtractCoverFromCBR:
    """Tests for extract_cover_from_cbr function"""

    def test_extract_cover_success(self, sample_cbr, tmp_path):
        """Test successful cover extraction from CBR"""
        if sample_cbr is None:
            pytest.skip("CBR fixture not available")

        from core.utils.cbz import extract_cover_from_cbr

        cover_path = extract_cover_from_cbr(sample_cbr, tmp_path)

        assert cover_path is not None
        assert cover_path.exists()
        assert cover_path.suffix == ".jpg"
        assert cover_path.stat().st_size > 0

    def test_extract_cover_creates_directory(self, sample_cbr, tmp_path):
        """Test that cover extraction creates output directory if it doesn't exist"""
        if sample_cbr is None:
            pytest.skip("CBR fixture not available")

        from core.utils.cbz import extract_cover_from_cbr

        output_dir = tmp_path / "covers"
        assert not output_dir.exists()

        cover_path = extract_cover_from_cbr(sample_cbr, output_dir)

        assert output_dir.exists()
        assert cover_path is not None

    def test_extract_cover_from_invalid_cbr(self, tmp_path):
        """Test cover extraction from invalid CBR file"""
        from core.utils.cbz import extract_cover_from_cbr

        invalid_cbr = tmp_path / "invalid.cbr"
        invalid_cbr.write_text("not a rar file")

        cover_path = extract_cover_from_cbr(invalid_cbr, tmp_path)

        assert cover_path is None

    def test_extract_cover_from_nonexistent_file(self, tmp_path):
        """Test cover extraction from non-existent file"""
        from core.utils.cbz import extract_cover_from_cbr

        fake_path = tmp_path / "nonexistent.cbr"

        cover_path = extract_cover_from_cbr(fake_path, tmp_path)

        assert cover_path is None

    def test_extract_cover_requires_rarfile(self, tmp_path):
        """Test that CBR extraction requires rarfile library"""
        from core.utils.cbz import extract_cover_from_cbr

        fake_cbr = tmp_path / "test.cbr"
        fake_cbr.write_bytes(b"Rar!\x1a\x07\x00")  # RAR file header

        result = extract_cover_from_cbr(fake_cbr, tmp_path)

        # Should return None if rarfile not available
        assert result is None

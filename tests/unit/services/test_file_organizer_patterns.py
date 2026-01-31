"""
Tests for FileOrganizer pattern registry and volume/issue-based organization.

Tests flexible folder patterns and fallback behavior when dates are missing.
"""

import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from services.file_organizer import FileOrganizer


class TestOrganizationPatterns:
    """Test organization pattern registry and selection."""

    def test_pattern_registry_exists(self):
        """Test that organization pattern registry is defined"""
        assert hasattr(FileOrganizer, "ORGANIZATION_PATTERNS")
        patterns = FileOrganizer.ORGANIZATION_PATTERNS

        # Check expected patterns exist
        assert "default" in patterns
        assert "volume" in patterns
        assert "flat" in patterns
        assert "volume_year" in patterns
        assert "issue" in patterns

    def test_pattern_structure(self):
        """Test that patterns have required structure"""
        patterns = FileOrganizer.ORGANIZATION_PATTERNS

        for pattern_name, pattern_config in patterns.items():
            assert "description" in pattern_config, f"Pattern '{pattern_name}' missing description"
            assert "template" in pattern_config, f"Pattern '{pattern_name}' missing template"
            assert "requires_date" in pattern_config, f"Pattern '{pattern_name}' missing requires_date"


class TestVolumeBasedOrganization:
    """Test organization for files with volume numbers but no dates."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing"""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def organizer(self, temp_dir):
        """Create FileOrganizer instance"""
        return FileOrganizer(str(temp_dir))

    def test_organize_with_volume_no_date(self, organizer, temp_dir):
        """Test organizing file with volume number but no date information"""
        # Create test file
        test_file = temp_dir / "Science Vol385.pdf"
        test_file.write_text("test content")

        metadata = {
            "title": "Science",
            "volume": 385,
            "issue_date": None,  # No date
            "year": None,
            "month_name": None,
        }

        result = organizer.organize(test_file, metadata, "Magazines")

        assert result is not None
        result_path = Path(result)
        assert result_path.exists()

        # Should be organized in volume-based structure
        # Expected: _Magazines/Science/Vol385/Science - Vol385.pdf
        assert "_Magazines" in str(result_path)
        assert "Science" in str(result_path)
        assert "Vol385" in str(result_path)
        assert result_path.name == "Science - Vol385.pdf"

    def test_organize_with_issue_no_date(self, organizer, temp_dir):
        """Test organizing file with issue number but no date information"""
        # Create test file
        test_file = temp_dir / "Comic Issue123.pdf"
        test_file.write_text("test content")

        metadata = {
            "title": "Amazing Comic",
            "issue_number": 123,
            "volume": None,
            "issue_date": None,
            "year": None,
            "month_name": None,
        }

        result = organizer.organize(test_file, metadata, "Comics")

        assert result is not None
        result_path = Path(result)
        assert result_path.exists()

        # Should be organized in flat structure
        # Expected: _Comics/Amazing Comic/Amazing Comic - No123.pdf
        assert "_Comics" in str(result_path)
        assert "Amazing Comic" in str(result_path)
        assert result_path.name == "Amazing Comic - No123.pdf"

    def test_organize_with_volume_and_issue_no_date(self, organizer, temp_dir):
        """Test organizing file with volume AND issue but no date"""
        # Create test file
        test_file = temp_dir / "Journal Vol12 No3.pdf"
        test_file.write_text("test content")

        metadata = {
            "title": "Academic Journal",
            "volume": 12,
            "issue_number": 3,
            "issue_date": None,
            "year": None,
            "month_name": None,
        }

        result = organizer.organize(test_file, metadata, "Articles")

        assert result is not None
        result_path = Path(result)
        assert result_path.exists()

        # Should prefer volume-based organization
        # Expected: _Articles/Academic Journal/Vol12/Academic Journal - Vol12 - No3.pdf
        assert "_Articles" in str(result_path)
        assert "Academic Journal" in str(result_path)
        assert "Vol12" in str(result_path)
        assert result_path.name == "Academic Journal - Vol12 - No3.pdf"

    def test_organize_with_no_metadata(self, organizer, temp_dir):
        """Test organizing file with no date, volume, or issue information"""
        # Create test file
        test_file = temp_dir / "Unknown File.pdf"
        test_file.write_text("test content")

        metadata = {
            "title": "Unknown Periodical",
            "volume": None,
            "issue_number": None,
            "issue_date": None,
            "year": None,
            "month_name": None,
        }

        result = organizer.organize(test_file, metadata, "Magazines")

        assert result is not None
        result_path = Path(result)
        assert result_path.exists()

        # Should use flat structure with "Unknown" fallback
        # Expected: _Magazines/Unknown Periodical/Unknown Periodical - Unknown.pdf
        assert "_Magazines" in str(result_path)
        assert "Unknown Periodical" in str(result_path)
        assert result_path.name == "Unknown Periodical - Unknown.pdf"


class TestFilenameBuilding:
    """Test filename building with optional date components."""

    @pytest.fixture
    def organizer(self):
        """Create FileOrganizer instance"""
        return FileOrganizer("/tmp/test")

    def test_build_filename_with_all_components(self, organizer):
        """Test filename with volume, issue, and date"""
        filename = organizer._build_filename("Wired", 5, 12, "December", "2024", ".pdf")
        assert filename == "Wired - Vol5 - No12 - December2024.pdf"

    def test_build_filename_volume_only(self, organizer):
        """Test filename with only volume (no issue or date)"""
        filename = organizer._build_filename("Science", 385, None, None, None, ".pdf")
        assert filename == "Science - Vol385.pdf"

    def test_build_filename_issue_only(self, organizer):
        """Test filename with only issue number (no volume or date)"""
        filename = organizer._build_filename("Comic", None, 123, None, None, ".pdf")
        assert filename == "Comic - No123.pdf"

    def test_build_filename_date_only(self, organizer):
        """Test filename with only date (no volume or issue)"""
        filename = organizer._build_filename("Magazine", None, None, "January", "2024", ".pdf")
        assert filename == "Magazine - January2024.pdf"

    def test_build_filename_volume_and_date(self, organizer):
        """Test filename with volume and date but no issue"""
        filename = organizer._build_filename("Journal", 42, None, "March", "2023", ".epub")
        assert filename == "Journal - Vol42 - March2023.epub"

    def test_build_filename_no_metadata(self, organizer):
        """Test filename with no metadata uses 'Unknown' fallback"""
        filename = organizer._build_filename("Unknown", None, None, None, None, ".pdf")
        assert filename == "Unknown - Unknown.pdf"


class TestHybridPatterns:
    """Test combining dates with volume/issue when both are available."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing"""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def organizer(self, temp_dir):
        """Create FileOrganizer instance"""
        return FileOrganizer(str(temp_dir))

    def test_organize_with_volume_and_date(self, organizer, temp_dir):
        """Test that having both volume and date uses default year-based organization"""
        # Create test file
        test_file = temp_dir / "Journal Vol42 2023.pdf"
        test_file.write_text("test content")

        metadata = {
            "title": "Scientific Journal",
            "volume": 42,
            "issue_number": None,
            "issue_date": datetime(2023, 3, 1),
            "year": 2023,
            "month_name": "March",
        }

        result = organizer.organize(test_file, metadata, "Articles")

        assert result is not None
        result_path = Path(result)
        assert result_path.exists()

        # Should use default year-based pattern when date is available
        # Expected: _Articles/Scientific Journal/Vol42/2023/Scientific Journal - Vol42 - March2023.pdf
        assert "_Articles" in str(result_path)
        assert "Scientific Journal" in str(result_path)
        assert "Vol42" in str(result_path)
        assert "2023" in str(result_path)
        assert result_path.name == "Scientific Journal - Vol42 - March2023.pdf"

    def test_custom_volume_year_pattern(self, organizer, temp_dir):
        """Test using explicit volume_year pattern"""
        # Create test file
        test_file = temp_dir / "Journal.pdf"
        test_file.write_text("test content")

        metadata = {
            "title": "Academic Review",
            "volume": 15,
            "issue_number": 3,
            "issue_date": datetime(2024, 6, 1),
            "year": 2024,
            "month_name": "June",
        }

        # Use explicit pattern
        result = organizer.organize(
            test_file,
            metadata,
            "Articles",
            pattern="{category}/{title}/Vol{volume}/{year}/",
        )

        assert result is not None
        result_path = Path(result)
        assert result_path.exists()

        # Should follow explicit pattern
        assert "_Articles/Academic Review/Vol15/2024" in str(result_path)
        assert result_path.name == "Academic Review - Vol15 - No3 - June2024.pdf"

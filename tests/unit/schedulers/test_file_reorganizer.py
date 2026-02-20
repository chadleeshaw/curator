"""
Tests for the file reorganizer scheduler.

Tests the background task that processes periodicals flagged with
needs_reorganization in extra_metadata.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from schedulers.file_reorganizer import FileReorganizer


@pytest.fixture
def mock_session_factory():
    """Mock session factory that returns a mock session."""
    session = MagicMock()
    factory = Mock(return_value=session)
    return factory


@pytest.fixture
def reorganizer(mock_session_factory, tmp_path):
    """Create a FileReorganizer with temp directory."""
    return FileReorganizer(
        session_factory=mock_session_factory,
        library_base_dir=str(tmp_path),
        category_prefix="_",
        batch_size=10,
    )


class TestFileReorganizerInitialization:
    """Test FileReorganizer initialization."""

    def test_initialization(self, mock_session_factory, tmp_path):
        """Test basic initialization."""
        reorg = FileReorganizer(
            session_factory=mock_session_factory,
            library_base_dir=str(tmp_path),
        )
        assert reorg.session_factory == mock_session_factory
        assert reorg.library_base_dir == str(tmp_path)
        assert reorg.category_prefix == "_"
        assert reorg.batch_size == 20  # default

    def test_custom_batch_size(self, mock_session_factory, tmp_path):
        """Test initialization with custom batch size."""
        reorg = FileReorganizer(
            session_factory=mock_session_factory,
            library_base_dir=str(tmp_path),
            batch_size=5,
        )
        assert reorg.batch_size == 5

    def test_initial_stats(self, reorganizer):
        """Test initial stats are zeroed."""
        assert reorganizer.stats["total_runs"] == 0
        assert reorganizer.stats["total_reorganized"] == 0
        assert reorganizer.stats["total_errors"] == 0
        assert reorganizer.stats["last_run_time"] is None


class TestRunNoFlagged:
    """Test run() when no periodicals are flagged."""

    def test_no_flagged_returns_zero_counts(self, reorganizer, mock_session_factory):
        """When no periodicals are flagged, return zeros."""
        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        result = reorganizer.run()

        assert result["processed"] == 0
        assert result["reorganized"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == 0

    def test_no_flagged_increments_total_runs(self, reorganizer, mock_session_factory):
        """Even with nothing to do, total_runs should not increment (no work done)."""
        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        reorganizer.run()

        # No work done, stats not updated
        assert reorganizer.stats["total_runs"] == 0


class TestClearFlag:
    """Test _clear_flag properly clears the reorganization flag."""

    def test_clears_needs_reorganization(self, reorganizer):
        """Flag should be removed from extra_metadata."""
        magazine = MagicMock()
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "metadata_discovered_by_ocr_queue",
            "category": "Magazines",
        }

        db = MagicMock()
        reorganizer._clear_flag(magazine, db, {"status": "reorganized"})

        assert "needs_reorganization" not in magazine.extra_metadata
        assert "reorganization_reason" not in magazine.extra_metadata
        assert "last_reorganization" in magazine.extra_metadata
        assert magazine.extra_metadata["last_reorganization"]["status"] == "reorganized"
        assert magazine.extra_metadata["last_reorganization"]["reason"] == "metadata_discovered_by_ocr_queue"
        db.commit.assert_called_once()

    def test_records_error_status(self, reorganizer):
        """Error results should be recorded in last_reorganization."""
        magazine = MagicMock()
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "metadata_discovered_by_text_scan",
        }

        db = MagicMock()
        reorganizer._clear_flag(magazine, db, {"status": "error", "error": "file not found"})

        last_reorg = magazine.extra_metadata["last_reorganization"]
        assert last_reorg["status"] == "error"
        assert last_reorg["reason"] == "metadata_discovered_by_text_scan"

    def test_handles_empty_extra_metadata(self, reorganizer):
        """Should handle None extra_metadata gracefully."""
        magazine = MagicMock()
        magazine.extra_metadata = None

        db = MagicMock()
        reorganizer._clear_flag(magazine, db, {"status": "skipped"})

        assert magazine.extra_metadata is not None
        assert "last_reorganization" in magazine.extra_metadata

    def test_preserves_other_metadata(self, reorganizer):
        """Other extra_metadata fields should not be affected."""
        magazine = MagicMock()
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "metadata_discovered_by_ocr",
            "category": "Comics",
            "imported_from": "some_file.pdf",
        }

        db = MagicMock()
        reorganizer._clear_flag(magazine, db, {"status": "reorganized"})

        assert magazine.extra_metadata["category"] == "Comics"
        assert magazine.extra_metadata["imported_from"] == "some_file.pdf"
        assert "needs_reorganization" not in magazine.extra_metadata


class TestRunWithFlagged:
    """Test run() with flagged periodicals."""

    def test_reorganized_count(self, reorganizer, mock_session_factory):
        """Successfully reorganized periodicals should be counted."""
        magazine = MagicMock()
        magazine.id = 1
        magazine.title = "Test Magazine"
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "metadata_discovered_by_ocr",
            "category": "Magazines",
        }

        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = [magazine]

        with patch.object(reorganizer, "_reorganize_single", return_value={"status": "reorganized"}):
            result = reorganizer.run()

        assert result["processed"] == 1
        assert result["reorganized"] == 1
        assert result["skipped"] == 0
        assert reorganizer.stats["total_reorganized"] == 1

    def test_skipped_count(self, reorganizer, mock_session_factory):
        """Skipped periodicals should be counted."""
        magazine = MagicMock()
        magazine.id = 1
        magazine.title = "Test Magazine"
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "metadata_discovered_by_ocr",
        }

        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = [magazine]

        with patch.object(
            reorganizer,
            "_reorganize_single",
            return_value={"status": "skipped", "reason": "already_correct"},
        ):
            result = reorganizer.run()

        assert result["skipped"] == 1
        assert result["reorganized"] == 0

    def test_error_count(self, reorganizer, mock_session_factory):
        """Errors during reorganization should be counted and flag still cleared."""
        magazine = MagicMock()
        magazine.id = 1
        magazine.title = "Test Magazine"
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "metadata_discovered_by_ocr",
        }

        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = [magazine]

        with patch.object(reorganizer, "_reorganize_single", side_effect=RuntimeError("disk full")):
            result = reorganizer.run()

        assert result["errors"] == 1
        assert result["reorganized"] == 0
        assert reorganizer.stats["total_errors"] == 1

    def test_multiple_periodicals(self, reorganizer, mock_session_factory):
        """Test processing multiple flagged periodicals."""
        magazines = []
        for i in range(3):
            mag = MagicMock()
            mag.id = i + 1
            mag.title = f"Magazine {i + 1}"
            mag.extra_metadata = {
                "needs_reorganization": True,
                "reorganization_reason": "metadata_discovered_by_ocr",
            }
            magazines.append(mag)

        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = magazines

        results = [
            {"status": "reorganized"},
            {"status": "skipped", "reason": "already_correct"},
            {"status": "reorganized"},
        ]

        with patch.object(reorganizer, "_reorganize_single", side_effect=results):
            result = reorganizer.run()

        assert result["processed"] == 3
        assert result["reorganized"] == 2
        assert result["skipped"] == 1

    def test_session_always_closed(self, reorganizer, mock_session_factory):
        """Database session should always be closed, even on error."""
        session = mock_session_factory()
        session.query.side_effect = RuntimeError("database error")

        with pytest.raises(RuntimeError):
            reorganizer.run()

        session.close.assert_called_once()

    def test_stats_accumulate(self, reorganizer, mock_session_factory):
        """Stats should accumulate across multiple runs."""
        magazine = MagicMock()
        magazine.id = 1
        magazine.title = "Test"
        magazine.extra_metadata = {
            "needs_reorganization": True,
            "reorganization_reason": "test",
        }

        session = mock_session_factory()
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = [magazine]

        with patch.object(reorganizer, "_reorganize_single", return_value={"status": "reorganized"}):
            reorganizer.run()
            reorganizer.run()

        assert reorganizer.stats["total_runs"] == 2
        assert reorganizer.stats["total_reorganized"] == 2
        assert reorganizer.stats["last_run_time"] is not None


class TestReorganizeSingle:
    """Test _reorganize_single delegates to FileOrganizer correctly."""

    def test_delegates_to_file_organizer(self, reorganizer):
        """Should use FileOrganizer's reorganization logic."""
        magazine = MagicMock()
        magazine.extra_metadata = {"category": "Magazines"}

        db = MagicMock()

        with patch("services.file_organizer.FileOrganizer") as MockOrganizer:
            mock_instance = MockOrganizer.return_value
            mock_instance._process_periodical_with_error_handling.return_value = {"status": "reorganized"}
            mock_instance._safe_cleanup_library_directories = MagicMock()

            result = reorganizer._reorganize_single(magazine, db)

        assert result["status"] == "reorganized"
        MockOrganizer.assert_called_once_with(reorganizer.library_base_dir, category_prefix="_")

    def test_uses_default_category(self, reorganizer):
        """Should use DEFAULT_CATEGORY when category not in extra_metadata."""
        magazine = MagicMock()
        magazine.extra_metadata = {}

        db = MagicMock()

        with patch("services.file_organizer.FileOrganizer") as MockOrganizer:
            mock_instance = MockOrganizer.return_value
            mock_instance._process_periodical_with_error_handling.return_value = {"status": "skipped"}
            mock_instance._safe_cleanup_library_directories = MagicMock()

            reorganizer._reorganize_single(magazine, db)

            # Verify category_with_prefix uses default
            call_kwargs = mock_instance._process_periodical_with_error_handling.call_args
            assert "_Magazines" in str(call_kwargs)


class TestResolveOrganizationPattern:
    """Test _resolve_organization_pattern uses tracking pattern when available."""

    def test_uses_tracking_pattern(self, reorganizer):
        """Should use per-periodical pattern from tracking record."""
        magazine = MagicMock()
        magazine.id = 1
        magazine.title = "Test"
        magazine.tracking_id = 42

        tracking = MagicMock()
        tracking.organization_pattern = "{category}/{title}/Vol{volume}/{year}/"

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = tracking

        result = reorganizer._resolve_organization_pattern(magazine, db)

        assert result == "{category}/{title}/Vol{volume}/{year}/"

    def test_falls_back_to_global_pattern(self, reorganizer):
        """Should fall back to global pattern when tracking has no pattern."""
        reorganizer.organization_pattern = "{category}/{title}/{year}/"

        magazine = MagicMock()
        magazine.id = 1
        magazine.title = "Test"
        magazine.tracking_id = 42

        tracking = MagicMock()
        tracking.organization_pattern = None

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = tracking

        result = reorganizer._resolve_organization_pattern(magazine, db)

        assert result == "{category}/{title}/{year}/"

    def test_falls_back_when_no_tracking_id(self, reorganizer):
        """Should use global pattern when periodical has no tracking_id."""
        reorganizer.organization_pattern = "{category}/{title}/{year}/"

        magazine = MagicMock()
        magazine.id = 1
        magazine.tracking_id = None

        db = MagicMock()

        result = reorganizer._resolve_organization_pattern(magazine, db)

        assert result == "{category}/{title}/{year}/"

    def test_falls_back_when_tracking_not_found(self, reorganizer):
        """Should use global pattern when tracking record doesn't exist."""
        reorganizer.organization_pattern = "{category}/{title}/{year}/"

        magazine = MagicMock()
        magazine.id = 1
        magazine.tracking_id = 999

        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = None

        result = reorganizer._resolve_organization_pattern(magazine, db)

        assert result == "{category}/{title}/{year}/"

    def test_returns_none_when_no_patterns(self, reorganizer):
        """Should return None when neither tracking nor global pattern exists."""
        reorganizer.organization_pattern = None

        magazine = MagicMock()
        magazine.id = 1
        magazine.tracking_id = None

        db = MagicMock()

        result = reorganizer._resolve_organization_pattern(magazine, db)

        assert result is None

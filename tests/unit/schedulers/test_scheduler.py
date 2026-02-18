"""
Unit tests for TaskScheduler class.

Fast unit tests using mocks - no real async execution or sleep calls.
For integration tests with real execution, see tests/integration/schedulers/
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


from core.parsers import utc_now
from schedulers import TaskScheduler


# ==============================================================================
# Tests for TaskScheduler.__init__
# ==============================================================================


class TestTaskSchedulerInit:
    """Test TaskScheduler initialization."""

    def test_initializes_with_empty_tasks(self):
        """Test scheduler starts with no tasks."""
        scheduler = TaskScheduler()

        assert scheduler.tasks == {}
        assert scheduler.running is False


# ==============================================================================
# Tests for TaskScheduler.schedule_periodic
# ==============================================================================


class TestSchedulePeriodic:
    """Test schedule_periodic method."""

    def test_adds_task_to_registry(self):
        """Test task is added to internal registry."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60)

        assert "test_task" in scheduler.tasks
        assert scheduler.tasks["test_task"]["func"] == task_func
        assert scheduler.tasks["test_task"]["interval"] == 60

    def test_task_enabled_by_default(self):
        """Test tasks are enabled by default."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60)

        assert scheduler.tasks["test_task"]["enabled"] is True

    def test_task_can_be_disabled_on_creation(self):
        """Test tasks can be created in disabled state."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60, enabled=False)

        assert scheduler.tasks["test_task"]["enabled"] is False

    def test_last_run_is_none_initially(self):
        """Test last_run timestamp is None for new tasks."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60)

        assert scheduler.tasks["test_task"]["last_run"] is None

    def test_run_immediately_sets_next_run_to_now(self):
        """Test run_immediately flag sets next_run to current time."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        before = utc_now()
        scheduler.schedule_periodic("test_task", task_func, 60, run_immediately=True)
        after = utc_now()

        # next_run should be set to now (not future)
        next_run = scheduler.tasks["test_task"]["next_run"]
        assert before <= next_run <= after

    def test_run_not_immediately_sets_next_run_to_future(self):
        """Test run_immediately=False sets next_run to future time."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        before = utc_now()
        scheduler.schedule_periodic("test_task", task_func, 60, run_immediately=False)

        # next_run should be in the future (about 60 seconds from now)
        next_run = scheduler.tasks["test_task"]["next_run"]
        time_diff = (next_run - before).total_seconds()
        assert 59 <= time_diff <= 61  # Allow 1s tolerance

    def test_failure_count_initialized_to_zero(self):
        """Test failure_count starts at 0."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60)

        assert scheduler.tasks["test_task"]["failure_count"] == 0

    def test_backoff_seconds_initialized_to_zero(self):
        """Test backoff_seconds starts at 0."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60)

        assert scheduler.tasks["test_task"]["backoff_seconds"] == 0


# ==============================================================================
# Tests for TaskScheduler.get_status
# ==============================================================================


class TestGetStatus:
    """Test get_status method."""

    def test_returns_running_state(self):
        """Test status includes running state."""
        scheduler = TaskScheduler()

        status = scheduler.get_status()

        assert "running" in status
        assert status["running"] is False

    def test_includes_all_scheduled_tasks(self):
        """Test status includes all scheduled tasks."""
        scheduler = TaskScheduler()
        task1 = AsyncMock()
        task2 = AsyncMock()

        scheduler.schedule_periodic("task1", task1, 30)
        scheduler.schedule_periodic("task2", task2, 60)

        status = scheduler.get_status()

        assert "tasks" in status
        assert "task1" in status["tasks"]
        assert "task2" in status["tasks"]

    def test_includes_task_intervals(self):
        """Test status includes task intervals."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 120)

        status = scheduler.get_status()

        assert status["tasks"]["test_task"]["interval"] == 120

    def test_includes_task_enabled_state(self):
        """Test status includes enabled flag."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("enabled_task", task_func, 60, enabled=True)
        scheduler.schedule_periodic("disabled_task", task_func, 60, enabled=False)

        status = scheduler.get_status()

        assert status["tasks"]["enabled_task"]["enabled"] is True
        assert status["tasks"]["disabled_task"]["enabled"] is False


# ==============================================================================
# Tests for TaskScheduler.set_task_enabled
# ==============================================================================


class TestSetTaskEnabled:
    """Test set_task_enabled method."""

    def test_enables_disabled_task(self):
        """Test enabling a disabled task."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60, enabled=False)
        result = scheduler.set_task_enabled("test_task", True)

        assert result is True
        assert scheduler.tasks["test_task"]["enabled"] is True

    def test_disables_enabled_task(self):
        """Test disabling an enabled task."""
        scheduler = TaskScheduler()
        task_func = AsyncMock()

        scheduler.schedule_periodic("test_task", task_func, 60, enabled=True)
        result = scheduler.set_task_enabled("test_task", False)

        assert result is True
        assert scheduler.tasks["test_task"]["enabled"] is False

    def test_returns_false_for_nonexistent_task(self):
        """Test returns False when task doesn't exist."""
        scheduler = TaskScheduler()

        result = scheduler.set_task_enabled("nonexistent_task", True)

        assert result is False


# ==============================================================================
# Tests for TaskScheduler.stop
# ==============================================================================


class TestStop:
    """Test stop method."""

    def test_sets_running_to_false(self):
        """Test stop() sets running flag to False."""
        scheduler = TaskScheduler()
        scheduler.running = True

        scheduler.stop()

        assert scheduler.running is False

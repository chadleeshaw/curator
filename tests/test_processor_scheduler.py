#!/usr/bin/env python3
"""
Test suite for TaskScheduler
"""

import asyncio
import sys
import time
from pathlib import Path  # noqa: E402
from datetime import datetime  # noqa: E402

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from processor.task_scheduler import TaskScheduler  # noqa: E402


def test_schedule_periodic():
    """Test scheduling periodic tasks"""
    scheduler = TaskScheduler()

    async def dummy_task():
        pass

    scheduler.schedule_periodic("test_task", dummy_task, 60)

    assert "test_task" in scheduler.tasks
    assert scheduler.tasks["test_task"]["interval"] == 60
    assert scheduler.tasks["test_task"]["func"] == dummy_task
    assert scheduler.tasks["test_task"]["last_run"] is None

    print("Testing TaskScheduler.schedule_periodic()... ✓ PASS")
    return True


def test_get_status():
    """Test getting scheduler status"""
    scheduler = TaskScheduler()

    async def dummy_task():
        pass

    scheduler.schedule_periodic("task1", dummy_task, 30)
    scheduler.schedule_periodic("task2", dummy_task, 60)

    status = scheduler.get_status()

    assert status["running"] is False
    assert "tasks" in status
    assert "task1" in status["tasks"]
    assert "task2" in status["tasks"]
    assert status["tasks"]["task1"]["interval"] == 30
    assert status["tasks"]["task2"]["interval"] == 60
    assert status["tasks"]["task1"]["last_run"] is None
    assert status["tasks"]["task2"]["last_run"] is None

    print("Testing TaskScheduler.get_status()... ✓ PASS")
    return True


def test_start_and_stop():
    """Test starting and stopping the scheduler"""
    scheduler = TaskScheduler()

    call_count = {"count": 0}

    async def counting_task():
        call_count["count"] += 1

    scheduler.schedule_periodic("counter", counting_task, 1)

    async def run_scheduler():
        scheduler_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(2.5)  # Let it run for 2.5 seconds
        scheduler.stop()
        await asyncio.sleep(0.5)

        # Force cancel the scheduler task if still running
        if not scheduler_task.done():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass

    asyncio.run(run_scheduler())

    # Task should have been called approximately 2-3 times (every 1 second for ~2.5 seconds)
    assert call_count["count"] >= 2, f"Expected at least 2 calls, got {call_count['count']}"

    # Verify scheduler stopped
    assert scheduler.running is False

    print("Testing TaskScheduler.start()/stop()... ✓ PASS")
    return True


def test_scheduler_error_handling():
    """Test that scheduler handles task errors gracefully"""
    scheduler = TaskScheduler()

    error_log = {"count": 0}

    async def failing_task():
        error_log["count"] += 1
        raise ValueError("Task failed intentionally")

    scheduler.schedule_periodic("failing_task", failing_task, 1)

    async def run_scheduler_with_errors():
        scheduler_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(2.5)
        scheduler.stop()
        await asyncio.sleep(0.5)

        if not scheduler_task.done():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass

    asyncio.run(run_scheduler_with_errors())

    # Task should still be rescheduled even after errors
    assert error_log["count"] >= 2, f"Expected at least 2 calls despite errors, got {error_log['count']}"
    assert scheduler.running is False

    print("Testing TaskScheduler error handling... ✓ PASS")
    return True


def test_multiple_tasks():
    """Test scheduling and running multiple tasks"""
    scheduler = TaskScheduler()

    execution_log = {"task1": 0, "task2": 0, "task3": 0}

    async def task1():
        execution_log["task1"] += 1

    async def task2():
        execution_log["task2"] += 1

    async def task3():
        execution_log["task3"] += 1

    scheduler.schedule_periodic("task1", task1, 1)
    scheduler.schedule_periodic("task2", task2, 1)
    scheduler.schedule_periodic("task3", task3, 1)

    async def run_multiple_tasks():
        scheduler_task = asyncio.create_task(scheduler.start())
        await asyncio.sleep(2.5)
        scheduler.stop()
        await asyncio.sleep(0.5)

        if not scheduler_task.done():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass

    asyncio.run(run_multiple_tasks())

    # All tasks should have been executed
    assert execution_log["task1"] >= 2
    assert execution_log["task2"] >= 2
    assert execution_log["task3"] >= 2

    status = scheduler.get_status()
    assert len(status["tasks"]) == 3

    print("Testing TaskScheduler with multiple tasks... ✓ PASS")
    return True


def test_task_intervals():
    """Test that tasks are scheduled with correct intervals"""
    scheduler = TaskScheduler()

    async def dummy_task():
        pass

    scheduler.schedule_periodic("fast_task", dummy_task, 5)
    scheduler.schedule_periodic("slow_task", dummy_task, 300)

    status = scheduler.get_status()
    assert status["tasks"]["fast_task"]["interval"] == 5
    assert status["tasks"]["slow_task"]["interval"] == 300

    print("Testing TaskScheduler task intervals... ✓ PASS")
    return True


if __name__ == "__main__":
    print("\n🧪 Task Scheduler Tests\n")
    print("=" * 50)

    results = {}

    try:
        results["schedule_periodic"] = test_schedule_periodic()
    except Exception as e:
        print(f"Testing TaskScheduler.schedule_periodic()... ❌ FAIL: {e}")
        results["schedule_periodic"] = False

    try:
        results["get_status"] = test_get_status()
    except Exception as e:
        print(f"Testing TaskScheduler.get_status()... ❌ FAIL: {e}")
        results["get_status"] = False

    try:
        results["start_stop"] = test_start_and_stop()
    except Exception as e:
        print(f"Testing TaskScheduler.start()/stop()... ❌ FAIL: {e}")
        results["start_stop"] = False

    try:
        results["error_handling"] = test_scheduler_error_handling()
    except Exception as e:
        print(f"Testing TaskScheduler error handling... ❌ FAIL: {e}")
        results["error_handling"] = False

    try:
        results["multiple_tasks"] = test_multiple_tasks()
    except Exception as e:
        print(f"Testing TaskScheduler with multiple tasks... ❌ FAIL: {e}")
        results["multiple_tasks"] = False

    try:
        results["task_intervals"] = test_task_intervals()
    except Exception as e:
        print(f"Testing TaskScheduler task intervals... ❌ FAIL: {e}")
        results["task_intervals"] = False

    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))

    sys.exit(0 if all_passed else 1)

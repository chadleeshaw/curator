"""
Background task scheduler for automated file imports and maintenance.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, TypedDict, cast

from core.parsers import utc_now

logger = logging.getLogger(__name__)


class TaskInfo(TypedDict):
    func: Callable
    interval: int
    last_run: Optional[datetime]
    next_run: datetime
    failure_count: int
    backoff_seconds: int
    enabled: bool


class TaskScheduler:
    """Simple task scheduler for background jobs with dynamic sleep and error backoff"""

    # Backoff settings for failed tasks
    MAX_BACKOFF_SECONDS = 300  # 5 minutes max backoff
    MIN_BACKOFF_SECONDS = 10  # 10 seconds min backoff
    BACKOFF_MULTIPLIER = 2.0  # Double the backoff each failure

    def __init__(self):
        self.tasks: Dict[str, TaskInfo] = {}
        self.running = False
        self.active_tasks = set()  # Track currently executing tasks
        self._async_tasks = set()  # Track running asyncio.Task objects

    def schedule_periodic(
        self,
        name: str,
        task_func: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
        enabled: bool = True,
    ):
        """
        Schedule a task to run periodically.

        Args:
            name: Task name (for logging)
            task_func: Async function to execute
            interval_seconds: How often to run the task
            run_immediately: If True, run task immediately on first scheduler cycle (default: False)
            enabled: If False, task is registered but will not run on schedule (default: True)
        """
        next_run = utc_now() if run_immediately else utc_now() + timedelta(seconds=interval_seconds)

        self.tasks[name] = TaskInfo(
            func=task_func,
            interval=interval_seconds,
            last_run=None,
            next_run=next_run,
            failure_count=0,
            backoff_seconds=0,
            enabled=enabled,
        )

        status = "enabled" if enabled else "disabled"
        timing = "immediately, then" if run_immediately else "in"
        logger.info(f"Scheduled task: {name} ({timing} every {interval_seconds}s) [{status}]")

    async def _run_task(self, task_name: str, task_info: TaskInfo) -> None:
        """Execute a scheduled task with error handling and backoff calculation"""
        now = utc_now()
        try:
            logger.debug(f"[TaskScheduler] About to run task: {task_name}")
            logger.debug(f"Running task: {task_name}")

            await task_info["func"]()

            # Task succeeded - reset failure count and backoff
            task_info["last_run"] = now
            task_info["failure_count"] = 0
            task_info["backoff_seconds"] = 0
            task_info["next_run"] = now + timedelta(seconds=task_info["interval"])

            logger.debug(f"[TaskScheduler] Task completed: {task_name}, next_run: {task_info['next_run']}")
            logger.debug(f"Task completed: {task_name}")

        except Exception as e:
            # Task failed - increment failure count and apply backoff
            task_info["failure_count"] += 1

            # Calculate exponential backoff
            if task_info["failure_count"] == 1:
                task_info["backoff_seconds"] = self.MIN_BACKOFF_SECONDS
            else:
                task_info["backoff_seconds"] = int(
                    min(
                        task_info["backoff_seconds"] * self.BACKOFF_MULTIPLIER,
                        self.MAX_BACKOFF_SECONDS,
                    )
                )

            # Schedule next run with backoff
            backoff_interval = task_info["interval"] + task_info["backoff_seconds"]
            task_info["next_run"] = now + timedelta(seconds=backoff_interval)

            logger.error(
                f"Error in task {task_name} (failure #{task_info['failure_count']}): {e}. "
                f"Next retry in {backoff_interval}s",
                exc_info=True,
            )
        finally:
            # Remove from active tasks
            self.active_tasks.discard(task_name)

    async def start(self):
        """Start the scheduler with dynamic sleep and error backoff"""
        if self.running:
            return

        self.running = True
        logger.debug("Task scheduler started")

        try:
            while self.running:
                now = utc_now()
                next_wakeup: Optional[datetime] = None

                for task_name, task_info in self.tasks.items():
                    # Skip disabled tasks
                    if not task_info.get("enabled", True):
                        continue

                    # Prevent scheduling if already running concurrently
                    if task_name in self.active_tasks:
                        continue

                    if now >= task_info["next_run"]:
                        # Mark task as active
                        self.active_tasks.add(task_name)

                        # Execute task concurrently
                        task = asyncio.create_task(self._run_task(task_name, task_info))
                        self._async_tasks.add(task)
                        task.add_done_callback(self._async_tasks.discard)

                    # Track earliest next run time for dynamic sleep (only enabled tasks)
                    if task_info.get("enabled", True):
                        if next_wakeup is None:
                            next_wakeup = task_info["next_run"]
                        elif next_wakeup is not None and task_info["next_run"] < cast(datetime, next_wakeup):
                            next_wakeup = task_info["next_run"]

                # Dynamic sleep: sleep until next task is due (with max 60s)
                if next_wakeup:
                    sleep_seconds = max(0.0, (next_wakeup - utc_now()).total_seconds())
                    sleep_seconds = min(sleep_seconds, 60.0)  # Cap at 60 seconds
                else:
                    sleep_seconds = 1  # Default fallback

                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)

        except asyncio.CancelledError:
            logger.info("Task scheduler cancelled - waiting for active tasks to complete")

            # Wait for active tasks with timeout
            if self.active_tasks:
                logger.info(f"Waiting for {len(self.active_tasks)} active tasks: {self.active_tasks}")
                timeout = 30  # 30 second timeout
                start_time = utc_now()

                while self.active_tasks and (utc_now() - start_time).total_seconds() < timeout:
                    await asyncio.sleep(0.5)

                if self.active_tasks:
                    logger.warning(
                        f"Forced shutdown - {len(self.active_tasks)} tasks still active: {self.active_tasks}"
                    )
                else:
                    logger.info("All active tasks completed successfully")

            self.running = False
            raise  # Re-raise to allow proper cancellation

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Task scheduler stopped")

    async def run_task_now(self, task_name: str) -> bool:
        """Manually trigger a task to run immediately

        Args:
            task_name: Name of the task to run

        Returns:
            True if task was found and executed, False otherwise
        """
        if task_name not in self.tasks:
            logger.warning(f"Task not found: {task_name}")
            return False

        task_info = self.tasks[task_name]
        logger.info(f"Manually triggering task: {task_name}")

        try:
            await task_info["func"]()
            logger.info(f"Manual task execution completed: {task_name}")
            return True
        except Exception as e:
            logger.error(f"Error in manual task execution {task_name}: {e}", exc_info=True)
            raise

    def get_status(self) -> dict:
        """Get scheduler status with failure and backoff info"""
        status_tasks = {}
        for name, info in self.tasks.items():
            last_run = info["last_run"]
            next_run = info["next_run"]
            status_tasks[name] = {
                "interval": info["interval"],
                "last_run": last_run.isoformat() if last_run else None,
                "next_run": next_run.isoformat() if next_run else None,
                "failure_count": info.get("failure_count", 0),
                "backoff_seconds": info.get("backoff_seconds", 0),
                "is_active": name in self.active_tasks,
                "enabled": info.get("enabled", True),
            }
        return {
            "running": self.running,
            "active_tasks": list(self.active_tasks),
            "tasks": status_tasks,
        }

    def set_task_enabled(self, task_name: str, enabled: bool) -> bool:
        """
        Enable or disable a task.

        Args:
            task_name: Name of the task to enable/disable
            enabled: True to enable, False to disable

        Returns:
            True if task was found and updated, False otherwise
        """
        if task_name not in self.tasks:
            logger.warning(f"Task not found: {task_name}")
            return False

        self.tasks[task_name]["enabled"] = enabled
        state = "enabled" if enabled else "disabled"
        logger.info(f"Task {task_name} {state}")

        # If re-enabling, schedule next run from now
        if enabled:
            interval = int(self.tasks[task_name]["interval"])
            self.tasks[task_name]["next_run"] = utc_now() + timedelta(seconds=interval)

        return True

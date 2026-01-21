"""
Background task scheduler for automated file imports and maintenance.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Simple task scheduler for background jobs with dynamic sleep and error backoff"""

    # Backoff settings for failed tasks
    MAX_BACKOFF_SECONDS = 300  # 5 minutes max backoff
    MIN_BACKOFF_SECONDS = 10  # 10 seconds min backoff
    BACKOFF_MULTIPLIER = 2.0  # Double the backoff each failure

    def __init__(self):
        self.tasks = {}
        self.running = False
        self.active_tasks = set()  # Track currently executing tasks

    def schedule_periodic(
        self,
        name: str,
        task_func: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
    ):
        """
        Schedule a task to run periodically.

        Args:
            name: Task name (for logging)
            task_func: Async function to execute
            interval_seconds: How often to run the task
            run_immediately: If True, run task immediately on first scheduler cycle (default: False)
        """
        next_run = (
            datetime.now()
            if run_immediately
            else datetime.now() + timedelta(seconds=interval_seconds)
        )

        self.tasks[name] = {
            "func": task_func,
            "interval": interval_seconds,
            "last_run": None,
            "next_run": next_run,
            "failure_count": 0,
            "backoff_seconds": 0,
        }

        timing = "immediately, then" if run_immediately else "in"
        logger.info(f"Scheduled task: {name} ({timing} every {interval_seconds}s)")

    async def start(self):
        """Start the scheduler with dynamic sleep and error backoff"""
        if self.running:
            return

        self.running = True
        logger.debug("Task scheduler started")

        try:
            while self.running:
                now = datetime.now()
                next_wakeup: Optional[datetime] = None

                for task_name, task_info in self.tasks.items():
                    if now >= task_info["next_run"]:
                        # Mark task as active
                        self.active_tasks.add(task_name)

                        try:
                            logger.debug(
                                f"[TaskScheduler] About to run task: {task_name}"
                            )
                            logger.debug(f"Running task: {task_name}")

                            await task_info["func"]()

                            # Task succeeded - reset failure count and backoff
                            task_info["last_run"] = now
                            task_info["failure_count"] = 0
                            task_info["backoff_seconds"] = 0
                            task_info["next_run"] = now + timedelta(
                                seconds=task_info["interval"]
                            )

                            logger.debug(
                                f"[TaskScheduler] Task completed: {task_name}, next_run: {task_info['next_run']}"
                            )
                            logger.debug(f"Task completed: {task_name}")

                        except Exception as e:
                            # Task failed - increment failure count and apply backoff
                            task_info["failure_count"] += 1

                            # Calculate exponential backoff
                            if task_info["failure_count"] == 1:
                                task_info["backoff_seconds"] = self.MIN_BACKOFF_SECONDS
                            else:
                                task_info["backoff_seconds"] = min(
                                    task_info["backoff_seconds"]
                                    * self.BACKOFF_MULTIPLIER,
                                    self.MAX_BACKOFF_SECONDS,
                                )

                            # Schedule next run with backoff
                            backoff_interval = (
                                task_info["interval"] + task_info["backoff_seconds"]
                            )
                            task_info["next_run"] = now + timedelta(
                                seconds=backoff_interval
                            )

                            logger.error(
                                f"Error in task {task_name} (failure #{task_info['failure_count']}): {e}. "
                                f"Next retry in {backoff_interval}s",
                                exc_info=True,
                            )
                        finally:
                            # Remove from active tasks
                            self.active_tasks.discard(task_name)

                    # Track earliest next run time for dynamic sleep
                    if next_wakeup is None or task_info["next_run"] < next_wakeup:
                        next_wakeup = task_info["next_run"]

                # Dynamic sleep: sleep until next task is due (with max 60s)
                if next_wakeup:
                    sleep_seconds = max(
                        0, (next_wakeup - datetime.now()).total_seconds()
                    )
                    sleep_seconds = min(sleep_seconds, 60)  # Cap at 60 seconds
                else:
                    sleep_seconds = 1  # Default fallback

                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)

        except asyncio.CancelledError:
            logger.info(
                "Task scheduler cancelled - waiting for active tasks to complete"
            )

            # Wait for active tasks with timeout
            if self.active_tasks:
                logger.info(
                    f"Waiting for {len(self.active_tasks)} active tasks: {self.active_tasks}"
                )
                timeout = 30  # 30 second timeout
                start_time = datetime.now()

                while (
                    self.active_tasks
                    and (datetime.now() - start_time).total_seconds() < timeout
                ):
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

    def get_status(self) -> dict:
        """Get scheduler status with failure and backoff info"""
        return {
            "running": self.running,
            "active_tasks": list(self.active_tasks),
            "tasks": {
                name: {
                    "interval": info["interval"],
                    "last_run": (
                        info["last_run"].isoformat() if info["last_run"] else None
                    ),
                    "next_run": info["next_run"].isoformat(),
                    "failure_count": info.get("failure_count", 0),
                    "backoff_seconds": info.get("backoff_seconds", 0),
                    "is_active": name in self.active_tasks,
                }
                for name, info in self.tasks.items()
            },
        }

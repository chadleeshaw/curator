"""
Background task scheduler for automated file imports and maintenance.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Simple task scheduler for background jobs"""

    def __init__(self):
        self.tasks = {}
        self.running = False

    def schedule_periodic(self, name: str, task_func: Callable, interval_seconds: int):
        """
        Schedule a task to run periodically.

        Args:
            name: Task name (for logging)
            task_func: Async function to execute
            interval_seconds: How often to run the task
        """
        self.tasks[name] = {
            "func": task_func,
            "interval": interval_seconds,
            "last_run": None,
            "next_run": datetime.now(),
        }
        logger.info(f"Scheduled task: {name} (every {interval_seconds}s)")

    async def start(self):
        """Start the scheduler"""
        if self.running:
            return

        self.running = True
        logger.info("Task scheduler started")

        try:
            while self.running:
                now = datetime.now()

                for task_name, task_info in self.tasks.items():
                    if now >= task_info["next_run"]:
                        try:
                            logger.debug(
                                f"[TaskScheduler] About to run task: {task_name}"
                            )
                            logger.debug(f"Running task: {task_name}")

                            await task_info["func"]()

                            task_info["last_run"] = now
                            task_info["next_run"] = now + timedelta(
                                seconds=task_info["interval"]
                            )
                            logger.debug(
                                f"[TaskScheduler] Task completed: {task_name}, next_run: {task_info['next_run']}"
                            )
                            logger.debug(f"Task completed: {task_name}")
                        except Exception as e:
                            logger.debug(
                                f"[TaskScheduler] Error in task {task_name}: {e}"
                            )
                            logger.error(
                                f"Error in task {task_name}: {e}", exc_info=True
                            )
                            # Reschedule even on failure
                            task_info["next_run"] = now + timedelta(
                                seconds=task_info["interval"]
                            )

                # Sleep for a short interval
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Task scheduler cancelled")
            self.running = False
        except Exception as e:
            logger.error(f"Task scheduler error: {e}", exc_info=True)
            self.running = False

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Task scheduler stopped")

    def get_status(self) -> dict:
        """Get scheduler status"""
        return {
            "running": self.running,
            "tasks": {
                name: {
                    "interval": info["interval"],
                    "last_run": (
                        info["last_run"].isoformat() if info["last_run"] else None
                    ),
                    "next_run": info["next_run"].isoformat(),
                }
                for name, info in self.tasks.items()
            },
        }

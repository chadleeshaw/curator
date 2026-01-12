"""
Task scheduling and monitoring for background jobs.
"""

from scheduler.task_scheduler import TaskScheduler
from scheduler.download_monitor import DownloadMonitorTask
from scheduler.cover_cleanup import CoverCleanupTask
from scheduler.ocr_processor import OCRProcessorTask
from scheduler.ocr_cover_generator import OCRCoverGeneratorTask

__all__ = [
    "TaskScheduler",
    "DownloadMonitorTask",
    "CoverCleanupTask",
    "OCRProcessorTask",
    "OCRCoverGeneratorTask",
]

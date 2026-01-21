"""
Task management routes
"""

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException

from models.database import Periodical
from core.utils import run_in_thread

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_download_monitor_task = None
_ocr_processor_task = None
_folder_cleanup_task = None
_file_importer = None
_storage_config = None
_task_scheduler = None


def set_dependencies(
    session_factory: Callable,
    download_monitor_task: Any,
    file_importer: Any,
    storage_config: Dict[str, Any],
    ocr_processor_task: Optional[Any] = None,
    task_scheduler: Optional[Any] = None,
    folder_cleanup_task: Optional[Any] = None,
) -> None:  # pylint: disable=too-many-positional-arguments
    """Set dependencies from main app"""
    global _session_factory, _download_monitor_task, _file_importer, _storage_config, _ocr_processor_task, _task_scheduler, _folder_cleanup_task
    _session_factory = session_factory
    _download_monitor_task = download_monitor_task
    _file_importer = file_importer
    _storage_config = storage_config
    _ocr_processor_task = ocr_processor_task
    _task_scheduler = task_scheduler
    _folder_cleanup_task = folder_cleanup_task


@router.get("/status")
async def get_tasks_status():
    """Get status of all scheduled tasks"""
    try:
        tasks = []

        # Download monitor task
        if _download_monitor_task:
            dm_last_run = getattr(_download_monitor_task, "last_run_time", None)
            dm_status = getattr(_download_monitor_task, "last_status", None)
            dm_stats = getattr(_download_monitor_task, "stats", {})
            logger.debug(f"Tasks Status - Download Monitor: last_run={dm_last_run}, status={dm_status}")

            # Get interval from scheduler
            dm_interval = 30
            if _task_scheduler:
                scheduler_status = _task_scheduler.get_status()
                if "download_monitor" in scheduler_status.get("tasks", {}):
                    dm_interval = scheduler_status["tasks"]["download_monitor"]["interval"]

            tasks.append(
                {
                    "id": "download_monitor",
                    "name": "Auto-Import",
                    "description": "Automatically imports completed downloads and organizes files into the library",
                    "interval": dm_interval,
                    "last_run": dm_last_run,
                    "next_run": getattr(_download_monitor_task, "next_run_time", None),
                    "last_status": dm_status,
                    "stats": {
                        "total_runs": dm_stats.get("total_runs", 0),
                        "client_downloads_processed": dm_stats.get("client_downloads_processed", 0),
                        "client_downloads_failed": dm_stats.get("client_downloads_failed", 0),
                        "folder_files_imported": dm_stats.get("folder_files_imported", 0),
                        "last_client_check": dm_stats.get("last_client_check"),
                        "last_folder_scan": dm_stats.get("last_folder_scan"),
                    },
                }
            )
        else:
            logger.debug("Tasks Status - Download Monitor task not available")

        # OCR processor task
        if _ocr_processor_task:
            ocr_last_run = getattr(_ocr_processor_task, "last_run_time", None)
            ocr_status = getattr(_ocr_processor_task, "last_status", None)
            ocr_stats = getattr(_ocr_processor_task, "stats", {})
            logger.debug(f"Tasks Status - OCR Processor: last_run={ocr_last_run}, status={ocr_status}")

            # Get interval from scheduler
            ocr_interval = 3600
            if _task_scheduler:
                scheduler_status = _task_scheduler.get_status()
                if "ocr_processor" in scheduler_status.get("tasks", {}):
                    ocr_interval = scheduler_status["tasks"]["ocr_processor"]["interval"]

            tasks.append(
                {
                    "id": "ocr_processor",
                    "name": "Auto-OCR",
                    "description": "Automatically extracts text from periodical covers using OCR for better search and metadata",
                    "interval": ocr_interval,
                    "last_run": ocr_last_run,
                    "next_run": getattr(_ocr_processor_task, "next_run_time", None),
                    "last_status": ocr_status,
                    "stats": {
                        "total_runs": ocr_stats.get("total_runs", 0),
                        "jobs_processed": ocr_stats.get("jobs_processed", 0),
                        "jobs_failed": ocr_stats.get("jobs_failed", 0),
                    },
                }
            )
        else:
            logger.debug("Tasks Status - OCR Processor task not available")

        # Get scheduler status if available
        scheduler_status = None
        if _task_scheduler:
            scheduler_status = _task_scheduler.get_status()

        # Auto-download task (from task scheduler if available)
        auto_download_info = {
            "id": "auto_download",
            "name": "Auto-Download",
            "description": "Automatically searches for and downloads new issues of tracked periodicals",
            "interval": 1800,
            "last_run": None,
            "next_run": None,
            "last_status": None,
        }
        if scheduler_status and "auto_download" in scheduler_status.get("tasks", {}):
            task_data = scheduler_status["tasks"]["auto_download"]
            last_run = task_data.get("last_run")
            failure_count = task_data.get("failure_count", 0)
            # Only set status if task has run at least once
            status = None
            if last_run:
                status = "failed" if failure_count > 0 else "success"
            auto_download_info.update(
                {
                    "interval": task_data.get("interval", 1800),
                    "last_run": last_run,
                    "next_run": task_data.get("next_run"),
                    "last_status": status,
                }
            )
        tasks.append(auto_download_info)

        # Cleanup covers task
        cleanup_covers_info = {
            "id": "cleanup_orphaned_covers",
            "name": "Auto-Thumbnail",
            "description": "Automatically generates and manages thumbnail images for periodicals",
            "interval": 86400,
            "last_run": None,
            "next_run": None,
            "last_status": None,
        }
        if scheduler_status and "cleanup_orphaned_covers" in scheduler_status.get("tasks", {}):
            task_data = scheduler_status["tasks"]["cleanup_orphaned_covers"]
            last_run = task_data.get("last_run")
            failure_count = task_data.get("failure_count", 0)
            # Only set status if task has run at least once
            status = None
            if last_run:
                status = "failed" if failure_count > 0 else "success"
            cleanup_covers_info.update(
                {
                    "interval": task_data.get("interval", 86400),
                    "last_run": last_run,
                    "next_run": task_data.get("next_run"),
                    "last_status": status,
                }
            )
        tasks.append(cleanup_covers_info)

        # Folder cleanup task
        folder_cleanup_info = {
            "id": "folder_cleanup",
            "name": "Auto-Cleanup",
            "description": "Automatically removes empty folders and folders containing only non-importable files from downloads and library",
            "interval": 86400,
            "last_run": None,
            "next_run": None,
            "last_status": None,
        }
        if scheduler_status and "folder_cleanup" in scheduler_status.get("tasks", {}):
            task_data = scheduler_status["tasks"]["folder_cleanup"]
            last_run = task_data.get("last_run")
            failure_count = task_data.get("failure_count", 0)
            # Only set status if task has run at least once
            status = None
            if last_run:
                status = "failed" if failure_count > 0 else "success"
            folder_cleanup_info.update(
                {
                    "interval": task_data.get("interval", 86400),
                    "last_run": last_run,
                    "next_run": task_data.get("next_run"),
                    "last_status": status,
                }
            )
        tasks.append(folder_cleanup_info)

        logger.debug(f"Tasks Status - Returning {len(tasks)} tasks to client")

        return {
            "success": True,
            "tasks": tasks,
            "timezone": os.environ.get("TZ", "UTC"),
        }

    except Exception as e:
        logger.error(f"Error getting task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting task status: {str(e)}")


@router.post("/run/{task_id}")
async def run_task_manually(task_id: str):
    """Manually trigger a scheduled task"""
    try:
        if task_id == "download_monitor":
            if _download_monitor_task:
                await _download_monitor_task.run()
                return {
                    "success": True,
                    "task_name": "Auto-Import",
                    "message": "Auto-import task executed",
                }
            else:
                return {"success": False, "message": "Download monitor not available"}

        elif task_id == "ocr_processor":
            if _ocr_processor_task:
                stats = await _ocr_processor_task.run()
                message = (
                    f"OCR processor executed. Processed: {stats.get('processed', 0)}, Failed: {stats.get('failed', 0)}"
                )
                return {
                    "success": True,
                    "task_name": "Auto-OCR",
                    "message": message,
                }
            else:
                return {"success": False, "message": "OCR processor not available"}

        elif task_id == "auto_download":
            # Note: This manual trigger should be handled by the task scheduler
            # For now, just return success to indicate the task exists
            return {
                "success": True,
                "task_name": "Auto-Download",
                "message": "Auto-download task will run on its scheduled interval (30 minutes)",
            }

        elif task_id == "folder_cleanup":
            if _folder_cleanup_task:
                stats = await _folder_cleanup_task.run()
                message = (
                    f"Folder cleanup executed. Deleted: {stats.get('total_deleted', 0)} folders, "
                    f"Freed: {stats.get('total_size_freed', 0)} MB"
                )
                return {
                    "success": True,
                    "task_name": "Auto-Cleanup",
                    "message": message,
                }
            else:
                return {"success": False, "message": "Folder cleanup not available"}

        elif task_id == "cleanup_orphaned_covers":
            # Manually trigger cover cleanup and generation (run in thread to avoid blocking)
            def _cleanup_covers():
                db_session = _session_factory()
                try:
                    # Get all periodicals
                    all_periodicals = db_session.query(Periodical).all()
                    periodicals_with_covers = [
                        m for m in all_periodicals if m.cover_path and Path(m.cover_path).exists()
                    ]
                    periodicals_without_covers = [
                        m
                        for m in all_periodicals
                        if m.file_path and (not m.cover_path or not Path(m.cover_path).exists())
                    ]

                    db_cover_paths = {str(Path(m.cover_path).resolve()) for m in periodicals_with_covers}

                    # Find all cover files on disk
                    covers_dir = Path(_storage_config.get("library_base_dir", "./local/data")) / ".covers"
                    covers_dir.mkdir(parents=True, exist_ok=True)

                    # Part 1: Delete orphaned covers
                    deleted_count = 0
                    if covers_dir.exists():
                        # Get absolute paths of all cover files on disk
                        cover_files = set(str(f.resolve()) for f in covers_dir.glob("*.jpg"))
                        orphaned_covers = cover_files - db_cover_paths

                        for orphan_path in orphaned_covers:
                            try:
                                Path(orphan_path).unlink()
                                deleted_count += 1
                            except Exception as e:
                                logger.error(f"Error deleting orphaned cover {orphan_path}: {e}")

                    # Part 2: Generate missing covers
                    generated_count = 0
                    for magazine in periodicals_without_covers:
                        pdf_path = Path(magazine.file_path)
                        if not pdf_path.exists():
                            continue

                        # Extract cover from PDF
                        cover_path = _file_importer._extract_cover(pdf_path)
                        if cover_path:
                            magazine.cover_path = str(cover_path)
                            generated_count += 1

                    if generated_count > 0:
                        db_session.commit()

                    # Build result message
                    messages = []
                    if deleted_count > 0:
                        messages.append(
                            f"Deleted {deleted_count} orphaned cover file{'s' if deleted_count != 1 else ''}"
                        )
                    if generated_count > 0:
                        messages.append(
                            f"Generated {generated_count} missing cover{'s' if generated_count != 1 else ''}"
                        )

                    if messages:
                        message = "Cleanup executed. " + ", ".join(messages) + "."
                    else:
                        message = "No orphaned covers found and all periodicals have covers."

                    return {
                        "deleted": deleted_count,
                        "generated": generated_count,
                        "message": message,
                    }
                finally:
                    db_session.close()

            result = await run_in_thread(_cleanup_covers)
            return {
                "success": True,
                "task_name": "Auto-Thumbnail",
                "message": result["message"],
            }

        else:
            return {"success": False, "message": f"Unknown task: {task_id}"}

    except Exception as e:
        logger.error(f"Error running task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error running task: {str(e)}")

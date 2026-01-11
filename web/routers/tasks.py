"""
Task management routes
"""

import asyncio
import logging
import os
from pathlib import Path
from functools import partial

from fastapi import APIRouter, HTTPException

from models.database import Magazine

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_download_monitor_task = None
_file_importer = None
_storage_config = None


def set_dependencies(
    session_factory, download_monitor_task, file_importer, storage_config
):
    """Set dependencies from main app"""
    global _session_factory, _download_monitor_task, _file_importer, _storage_config
    _session_factory = session_factory
    _download_monitor_task = download_monitor_task
    _file_importer = file_importer
    _storage_config = storage_config


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
            logger.debug(
                f"Tasks Status - Download Monitor: last_run={dm_last_run}, status={dm_status}"
            )

            tasks.append(
                {
                    "id": "download_monitor",
                    "name": "Download Monitor",
                    "description": "Monitors download client status and scans download folder recursively for PDF/EPUB files to organize",
                    "interval": 30,
                    "last_run": dm_last_run,
                    "next_run": getattr(_download_monitor_task, "next_run_time", None),
                    "last_status": dm_status,
                    "stats": {
                        "total_runs": dm_stats.get("total_runs", 0),
                        "client_downloads_processed": dm_stats.get(
                            "client_downloads_processed", 0
                        ),
                        "client_downloads_failed": dm_stats.get(
                            "client_downloads_failed", 0
                        ),
                        "folder_files_imported": dm_stats.get(
                            "folder_files_imported", 0
                        ),
                        "bad_files_detected": dm_stats.get("bad_files_detected", 0),
                        "last_client_check": dm_stats.get("last_client_check"),
                        "last_folder_scan": dm_stats.get("last_folder_scan"),
                    },
                }
            )
        else:
            logger.debug("Tasks Status - Download Monitor task not available")

        # Auto-download task (from task scheduler if available)
        tasks.append(
            {
                "id": "auto_download",
                "name": "Auto Download",
                "description": "Searches for and downloads new issues of tracked periodicals (supports tracking entire series or individual issues)",
                "interval": 1800,
                "last_run": None,
                "next_run": None,
                "last_status": None,
            }
        )

        # Cleanup covers task
        tasks.append(
            {
                "id": "cleanup_orphaned_covers",
                "name": "Cleanup Orphaned Covers",
                "description": "Removes orphaned cover files and generates missing covers for periodicals",
                "interval": 86400,
                "last_run": None,
                "next_run": None,
                "last_status": None,
            }
        )

        logger.debug(f"Tasks Status - Returning {len(tasks)} tasks to client")

        return {
            "success": True,
            "tasks": tasks,
            "timezone": os.environ.get("TZ", "UTC"),
        }

    except Exception as e:
        logger.error(f"Error getting task status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error getting task status: {str(e)}"
        )


@router.post("/run/{task_id}")
async def run_task_manually(task_id: str):
    """Manually trigger a scheduled task"""
    try:
        if task_id == "download_monitor":
            if _download_monitor_task:
                await _download_monitor_task.run()
                return {
                    "success": True,
                    "task_name": "Download Monitor",
                    "message": "Download monitor task executed",
                }
            else:
                return {"success": False, "message": "Download monitor not available"}

        elif task_id == "auto_download":
            # Note: This manual trigger should be handled by the task scheduler
            # For now, just return success to indicate the task exists
            return {
                "success": True,
                "task_name": "Auto Download",
                "message": "Auto-download task will run on its scheduled interval (30 minutes)",
            }

        elif task_id == "cleanup_orphaned_covers":
            # Manually trigger cover cleanup and generation
            db_session = _session_factory()
            try:
                # Get all periodicals
                all_periodicals = db_session.query(Magazine).all()
                periodicals_with_covers = [
                    m
                    for m in all_periodicals
                    if m.cover_path and Path(m.cover_path).exists()
                ]
                periodicals_without_covers = [
                    m
                    for m in all_periodicals
                    if m.file_path
                    and (not m.cover_path or not Path(m.cover_path).exists())
                ]

                db_cover_paths = {
                    str(Path(m.cover_path).resolve())
                    for m in periodicals_with_covers
                }

                # Find all cover files on disk
                covers_dir = (
                    Path(_storage_config.get("organize_base_dir", "./local/data"))
                    / ".covers"
                )
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
                            logger.error(
                                f"Error deleting orphaned cover {orphan_path}: {e}"
                            )

                # Part 2: Generate missing covers
                generated_count = 0
                for magazine in periodicals_without_covers:
                    pdf_path = Path(magazine.file_path)
                    if not pdf_path.exists():
                        continue

                    # Extract cover from PDF (run in thread pool to avoid blocking)
                    loop = asyncio.get_event_loop()
                    cover_path = await loop.run_in_executor(
                        None,
                        _file_importer._extract_cover,
                        pdf_path
                    )
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
                    message = (
                        "No orphaned covers found and all periodicals have covers."
                    )

                return {
                    "success": True,
                    "task_name": "Cleanup Orphaned Covers",
                    "message": message,
                }
            finally:
                db_session.close()

        else:
            return {"success": False, "message": f"Unknown task: {task_id}"}

    except Exception as e:
        logger.error(f"Error running task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error running task: {str(e)}")

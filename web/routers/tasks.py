"""
Task management routes
"""

import logging
from pathlib import Path

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
            logger.debug(
                f"Tasks Status - Download Monitor: last_run={dm_last_run}, status={dm_status}"
            )

            tasks.append(
                {
                    "id": "download_monitor",
                    "name": "Download Monitor",
                    "description": "Monitors download status and processes completed downloads",
                    "interval": 30,
                    "last_run": dm_last_run,
                    "next_run": getattr(_download_monitor_task, "next_run_time", None),
                    "last_status": dm_status,
                }
            )
        else:
            logger.debug("Tasks Status - Download Monitor task not available")

        # Auto-download task (from task scheduler if available)
        tasks.append(
            {
                "id": "auto_download",
                "name": "Auto Download",
                "description": "Checks tracked periodicals for new issues and imports PDFs from downloads folder",
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
                "description": "Removes cover files that aren't tied to any periodical",
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
            # Manually trigger cover cleanup
            db_session = _session_factory()
            try:
                # Get all covers in the database
                periodicals = (
                    db_session.query(Magazine)
                    .filter(Magazine.cover_path is not None)
                    .all()
                )
                db_cover_paths = {m.cover_path for m in periodicals if m.cover_path}

                # Find all cover files on disk
                covers_dir = (
                    Path(_storage_config.get("organize_base_dir", "./local/data"))
                    / ".covers"
                )
                if covers_dir.exists():
                    cover_files = set(str(f) for f in covers_dir.glob("*.jpg"))

                    # Find orphaned covers (files that exist on disk but not in DB)
                    orphaned_covers = cover_files - db_cover_paths

                    # Delete orphaned covers
                    deleted_count = 0
                    for orphan_path in orphaned_covers:
                        try:
                            Path(orphan_path).unlink()
                            deleted_count += 1
                        except Exception as e:
                            logger.error(
                                f"Error deleting orphaned cover {orphan_path}: {e}"
                            )

                    return {
                        "success": True,
                        "task_name": "Cleanup Orphaned Covers",
                        "message": f"Cleanup executed. Deleted {deleted_count} orphaned cover files.",
                    }
                else:
                    return {
                        "success": True,
                        "task_name": "Cleanup Orphaned Covers",
                        "message": "Covers directory does not exist yet.",
                    }
            finally:
                db_session.close()

        else:
            return {"success": False, "message": f"Unknown task: {task_id}"}

    except Exception as e:
        logger.error(f"Error running task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error running task: {str(e)}")

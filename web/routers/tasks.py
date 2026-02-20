"""
Task management routes
"""

import logging
import os
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter

from core.constants.files import BYTES_PER_MB
from core.utils.error_handling import handle_api_errors
from core.utils import run_in_thread
from web.utils.responses import success_response, error_response

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
_config_loader = None

# Map task IDs to their config enabled keys
TASK_ENABLED_CONFIG_KEYS = {
    "auto_download": "auto_download_enabled",
    "download_monitor": "download_monitor_enabled",
    "cleanup_orphaned_covers": "cleanup_covers_enabled",
    "ocr_processor": "ocr_processor_enabled",
    "folder_cleanup": "folder_cleanup_enabled",
    "auto_metadata": "auto_metadata_enabled",
    "file_reorganizer": "file_reorganizer_enabled",
}


def set_dependencies(
    session_factory: Callable,
    download_monitor_task: Any,
    file_importer: Any,
    storage_config: Dict[str, Any],
    ocr_processor_task: Optional[Any] = None,
    task_scheduler: Optional[Any] = None,
    folder_cleanup_task: Optional[Any] = None,
    config_loader: Optional[Any] = None,
) -> None:  # pylint: disable=too-many-positional-arguments
    """Set dependencies from main app"""
    global _session_factory, _download_monitor_task, _file_importer, _storage_config, _ocr_processor_task, _task_scheduler, _folder_cleanup_task, _config_loader
    _session_factory = session_factory
    _download_monitor_task = download_monitor_task
    _file_importer = file_importer
    _storage_config = storage_config
    _ocr_processor_task = ocr_processor_task
    _task_scheduler = task_scheduler
    _folder_cleanup_task = folder_cleanup_task
    _config_loader = config_loader


@router.get("/status")
@handle_api_errors("Get tasks status", logger)
async def get_tasks_status():
    """Get status of all scheduled tasks"""
    tasks = []

    # Download monitor task
    if _download_monitor_task:
        dm_last_run = getattr(_download_monitor_task, "last_run_time", None)
        dm_status = getattr(_download_monitor_task, "last_status", None)
        dm_stats = getattr(_download_monitor_task, "stats", {})
        logger.debug(f"Tasks Status - Download Monitor: last_run={dm_last_run}, status={dm_status}")

        # Get interval and enabled from scheduler
        dm_interval = 30
        dm_enabled = True
        if _task_scheduler:
            scheduler_status = _task_scheduler.get_status()
            if "download_monitor" in scheduler_status.get("tasks", {}):
                dm_interval = scheduler_status["tasks"]["download_monitor"]["interval"]
                dm_enabled = scheduler_status["tasks"]["download_monitor"].get("enabled", True)

        tasks.append(
            {
                "id": "download_monitor",
                "name": "Auto-Import",
                "description": "Automatically imports completed downloads and organizes files into the library",
                "interval": dm_interval,
                "last_run": dm_last_run,
                "next_run": getattr(_download_monitor_task, "next_run_time", None),
                "last_status": dm_status,
                "enabled": dm_enabled,
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
        "enabled": True,
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
                "enabled": task_data.get("enabled", True),
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
        "enabled": True,
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
                "enabled": task_data.get("enabled", True),
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
        "enabled": True,
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
                "enabled": task_data.get("enabled", True),
            }
        )
    tasks.append(folder_cleanup_info)

    # Auto-metadata task (scheduled weekly, not manual-only anymore)
    auto_metadata_info = {
        "id": "auto_metadata",
        "name": "Auto-Metadata",
        "description": "Backfills derived_metadata, syncs issue_date, and queues missing OCR/text scans for all periodicals",
        "interval": 604800,  # 7 days
        "last_run": None,
        "next_run": None,
        "last_status": None,
        "enabled": True,
    }
    if scheduler_status and "auto_metadata" in scheduler_status.get("tasks", {}):
        task_data = scheduler_status["tasks"]["auto_metadata"]
        last_run = task_data.get("last_run")
        failure_count = task_data.get("failure_count", 0)
        # Only set status if task has run at least once
        status = None
        if last_run:
            status = "failed" if failure_count > 0 else "success"
        auto_metadata_info.update(
            {
                "interval": task_data.get("interval", 604800),
                "last_run": last_run,
                "next_run": task_data.get("next_run"),
                "last_status": status,
                "enabled": task_data.get("enabled", True),
            }
        )
    tasks.append(auto_metadata_info)

    # File reorganizer task
    file_reorganizer_info = {
        "id": "file_reorganizer",
        "name": "Auto-Reorganize",
        "description": "Moves periodical files to their correct library location when new metadata is discovered by OCR or text scans",
        "interval": 300,
        "last_run": None,
        "next_run": None,
        "last_status": None,
        "enabled": True,
    }
    if scheduler_status and "file_reorganizer" in scheduler_status.get("tasks", {}):
        task_data = scheduler_status["tasks"]["file_reorganizer"]
        last_run = task_data.get("last_run")
        failure_count = task_data.get("failure_count", 0)
        # Only set status if task has run at least once
        status = None
        if last_run:
            status = "failed" if failure_count > 0 else "success"
        file_reorganizer_info.update(
            {
                "interval": task_data.get("interval", 300),
                "last_run": last_run,
                "next_run": task_data.get("next_run"),
                "last_status": status,
                "enabled": task_data.get("enabled", True),
            }
        )
    tasks.append(file_reorganizer_info)

    logger.debug(f"Tasks Status - Returning {len(tasks)} tasks to client")

    return success_response(
        None,
        tasks=tasks,
        timezone=os.environ.get("TZ", "UTC"),
    )


@router.post("/run/{task_id}")
@handle_api_errors("Run task manually", logger)
async def run_task_manually(task_id: str):
    """Manually trigger a scheduled task"""
    if task_id == "download_monitor":
        if _download_monitor_task:
            logger.info("Starting auto-import task (manual trigger)")
            await _download_monitor_task.run()
            return success_response(
                "Auto-import task executed",
                task_name="Auto-Import",
            )
        else:
            return error_response("Download monitor not available")

    elif task_id == "auto_download":
        # Manually trigger auto-download task via scheduler
        if not _task_scheduler:
            logger.warning("Auto-download task triggered but task scheduler not available")
            return error_response("Task scheduler not available")

        try:
            logger.info("Manually triggering auto-download task via scheduler")
            await _task_scheduler.run_task_now("auto_download")
            logger.info("Auto-download task completed successfully")
            return success_response(
                "Auto-download task executed successfully",
                task_name="Auto-Download",
            )
        except Exception as e:
            logger.error(f"Error running auto-download task: {e}", exc_info=True)
            return error_response(f"Failed to run auto-download task: {str(e)}")

    elif task_id == "folder_cleanup":
        if _folder_cleanup_task:
            logger.info("Starting folder cleanup task (manual trigger)")
            stats = await run_in_thread(_folder_cleanup_task.run)
            message = (
                f"Folder cleanup executed. Deleted: {stats.get('total_deleted', 0)} folders, "
                f"Freed: {stats.get('total_size_freed', 0) / BYTES_PER_MB:.2f} MB"
            )
            return success_response(
                message,
                task_name="Auto-Cleanup",
            )
        else:
            return error_response("Folder cleanup not available")

    elif task_id == "auto_metadata":
        # Run auto-metadata task to backfill and sync metadata
        logger.info("Starting auto-metadata task (manual trigger)")

        def _run_auto_metadata():
            from services.auto_metadata import AutoMetadataService
            from core.database import DatabaseManager
            from core.config import ConfigLoader

            config_loader = ConfigLoader()
            storage = config_loader.get_storage()
            import_config = config_loader.get_import()
            db_path = storage.get("db_path", "local/data/curator.db")
            db_manager = DatabaseManager(f"sqlite:///{db_path}")

            service = AutoMetadataService(
                db_manager,
                library_base_dir=storage.get("library_dir"),
                category_prefix=import_config.get("category_prefix", "_"),
            )
            session = db_manager.session_factory()
            try:
                return service.run_full_scan(session)
            finally:
                session.close()

        stats = await run_in_thread(_run_auto_metadata)
        message = (
            f"Auto-metadata executed. "
            f"Processed: {stats.get('total_periodicals', 0)}, "
            f"Metadata cleaned: {stats.get('metadata_cleaned', 0)}, "
            f"Derived metadata backfilled: {stats.get('derived_metadata_backfilled', 0)}, "
            f"Issue dates synced: {stats.get('issue_date_synced', 0)}, "
            f"OCR queued: {stats.get('ocr_queued', 0)}, "
            f"Text scans queued: {stats.get('text_scan_queued', 0)}, "
            f"Errors: {stats.get('errors', 0)}"
        )
        return success_response(
            message,
            task_name="Auto-Metadata",
            stats=stats,
        )

    elif task_id == "cleanup_orphaned_covers":
        # Manually trigger cover cleanup via scheduler
        if _task_scheduler:
            try:
                await _task_scheduler.run_task_now("cleanup_orphaned_covers")
                return success_response(
                    "Cover cleanup executed successfully",
                    task_name="Auto-Thumbnail",
                )
            except Exception as e:
                logger.error(f"Error running cover cleanup: {e}", exc_info=True)
                return error_response(f"Failed to run cover cleanup: {str(e)}")
        else:
            return error_response("Task scheduler not available")

    elif task_id == "file_reorganizer":
        # Manually trigger file reorganizer via scheduler
        if _task_scheduler:
            try:
                await _task_scheduler.run_task_now("file_reorganizer")
                return success_response(
                    "File reorganizer executed successfully",
                    task_name="Auto-Reorganize",
                )
            except Exception as e:
                logger.error(f"Error running file reorganizer: {e}", exc_info=True)
                return error_response(f"Failed to run file reorganizer: {str(e)}")
        else:
            return error_response("Task scheduler not available")

    else:
        return error_response(f"Unknown task: {task_id}")


@router.post("/{task_id}/toggle")
@handle_api_errors("Toggle task enabled state", logger)
async def toggle_task(task_id: str):
    """Toggle a task's enabled/disabled state.

    Updates both the in-memory scheduler state and persists to config file.
    Disabled tasks will not run on schedule but can still be triggered manually.
    """
    if not _task_scheduler:
        return error_response("Task scheduler not available")

    # Check task exists in scheduler
    scheduler_status = _task_scheduler.get_status()
    if task_id not in scheduler_status.get("tasks", {}):
        return error_response(f"Unknown task: {task_id}")

    # Toggle the current state
    current_enabled = scheduler_status["tasks"][task_id].get("enabled", True)
    new_enabled = not current_enabled

    # Update scheduler in-memory state
    _task_scheduler.set_task_enabled(task_id, new_enabled)

    # Persist to config file
    if _config_loader:
        try:
            config_key = TASK_ENABLED_CONFIG_KEYS.get(task_id)
            if config_key:
                all_config = _config_loader.get_all_config()
                if "tasks" not in all_config:
                    all_config["tasks"] = {}
                all_config["tasks"][config_key] = new_enabled
                _config_loader.save_config(all_config)
                logger.info(f"Persisted task toggle: {task_id} -> {new_enabled}")
        except Exception:
            logger.warning(f"Failed to persist task toggle for {task_id} to config file")

    state = "enabled" if new_enabled else "disabled"
    return success_response(
        f"Task {task_id} {state}",
        task_id=task_id,
        enabled=new_enabled,
    )

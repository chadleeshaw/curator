"""
File import routes
"""

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from core.constants.category import DEFAULT_CATEGORY
from core.constants.errors import ErrorMessages
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.general import find_pdf_epub_files
from web.schemas import ImportOptionsRequest
from web.utils.responses import status_response, success_response

router = APIRouter(prefix="/api/import", tags=["imports"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_file_importer = None
_storage_config = None


def set_dependencies(session_factory: Callable, file_importer: Any, storage_config: Dict[str, Any]) -> None:
    """Set dependencies from main app"""
    global _session_factory, _file_importer, _storage_config
    _session_factory = session_factory
    _file_importer = file_importer
    _storage_config = storage_config


@router.post("/process")
@handle_api_errors("Import from downloads", logger)
async def import_from_downloads(
    background_tasks: BackgroundTasks, options: Optional[ImportOptionsRequest] = None
) -> Dict[str, Any]:
    """
    Process PDFs from downloads folder and import them into the library.
    Runs asynchronously in background.

    Args:
        options: Optional import configuration

    Returns:
        Status of import operation
    """
    if not _file_importer:
        raise HTTPException(status_code=503, detail=ErrorMessages.FILE_IMPORTER_UNAVAILABLE)

    async def process_imports():
        """Background task to process imports"""
        try:

            def operation(db):
                # Pass organization_pattern to file importer
                org_pattern = options.organization_pattern if options else None
                results = _file_importer.process_downloads(db, org_pattern)
                logger.debug(f"Import completed: {results}")
                return results

            await with_db_session(_session_factory, operation)
        except Exception as e:
            logger.error(f"Error processing imports: {e}", exc_info=True)

    background_tasks.add_task(process_imports)

    return status_response("processing", "Started importing PDFs from downloads folder")


@router.get("/status")
@handle_api_errors("Get import status", logger)
async def get_import_status() -> Dict[str, Any]:
    """Get information about available files in downloads folder (searches recursively)"""
    downloads_dir = Path(_storage_config.get("download_dir", "./downloads"))

    if not downloads_dir.exists():
        return {
            "ready": False,
            "files": 0,
            "message": "Downloads directory not found",
        }

    # Search recursively for PDF and EPUB files (matches process_downloads behavior)
    all_files = find_pdf_epub_files(downloads_dir, recursive=True)
    pdf_files = [f for f in all_files if f.suffix == ".pdf"]
    epub_files = [f for f in all_files if f.suffix == ".epub"]

    return {
        "ready": len(all_files) > 0,
        "files": len(all_files),
        "file_list": [str(f.relative_to(downloads_dir)) for f in all_files],
        "message": f"Found {len(all_files)} files ready to import ({len(pdf_files)} PDFs, {len(epub_files)} EPUBs)",
    }


@router.post("/from-library-dir")
@handle_api_errors("Import from library dir", logger)
async def import_from_library_dir(
    background_tasks: BackgroundTasks,
    options: ImportOptionsRequest,
) -> Dict[str, Any]:
    """
    Import PDF and EPUB files from the organized data directory back into the library.
    Useful for syncing files that exist in the library directory but aren't in the database.

    Args:
        options: Import options including auto_track, tracking_mode, and organization_pattern

    Returns:
        Status of import operation
    """
    if not _file_importer:
        raise HTTPException(status_code=503, detail=ErrorMessages.FILE_IMPORTER_UNAVAILABLE)

    library_dir = Path(_storage_config.get("library_dir", "./local/data"))

    if not library_dir.exists():
        raise HTTPException(status_code=400, detail=f"Library directory not found: {library_dir}")

    # Count files available for import (PDFs and EPUBs)
    all_files = find_pdf_epub_files(library_dir, recursive=True)

    if not all_files:
        return success_response(
            f"No PDF or EPUB files found in library directory: {library_dir}",
            imported=0,
        )

    async def process_library_dir_imports():
        """Background task to process imports from library directory"""
        original_pattern = None
        try:
            logger.info(f"Import settings: auto_track={options.auto_track}, tracking_mode={options.tracking_mode}")

            # Temporarily override organization pattern if provided
            original_pattern = _file_importer.organization_pattern
            if options.organization_pattern:
                _file_importer.organization_pattern = options.organization_pattern

            def operation(db):
                results = _file_importer.process_organized_files(
                    db,
                    auto_track=options.auto_track,
                    tracking_mode=options.tracking_mode,
                )

                # Extract counts from nested data structure
                data = results.get("data", {})
                imported = data.get("imported", 0)
                failed = data.get("failed", 0)

                logger.info(f"Library directory import results: {imported} imported, {failed} failed")
                return results

            await with_db_session(_session_factory, operation)

        except Exception as e:
            logger.error(f"Error processing library directory imports: {e}", exc_info=True)
        finally:
            # Restore original pattern
            if original_pattern is not None:
                try:
                    _file_importer.organization_pattern = original_pattern
                except Exception as e:
                    logger.error(f"Error restoring organization pattern: {e}")

    background_tasks.add_task(process_library_dir_imports)

    return success_response(
        f"Started importing {len(all_files)} files from library directory",
        imported=len(all_files),
    )


@router.post("/reorganize")
@handle_api_errors("Reorganize library", logger)
async def reorganize_library(
    category: str = DEFAULT_CATEGORY,
    pattern: Optional[str] = None,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Reorganize files in the library to match the current organization pattern.

    Scans the organized directory for files in the wrong location and moves them
    to the correct location based on their metadata in the database.

    Args:
        category: Category to reorganize (default: DEFAULT_CATEGORY from constants)
        pattern: Organization pattern with tags like {category}/{title}/{year}/ (uses config default if not provided)
        dry_run: If True, only report what would be done without making changes.
                 If None (default), checks CURATOR_DRY_RUN env var (defaults to False if not set)

    Returns:
        Reorganization results
    """
    # Determine dry_run value: parameter > env var > default False
    if dry_run is None:
        dry_run_env = os.environ.get("CURATOR_DRY_RUN", "false").lower()
        dry_run = dry_run_env in ("true", "1", "yes")

    if not _file_importer:
        raise HTTPException(status_code=503, detail=ErrorMessages.FILE_IMPORTER_UNAVAILABLE)

    def operation(db):
        # Use the file organizer from the file importer
        organizer = _file_importer.organizer

        results = organizer.reorganize_from_database(db_session=db, category=category, pattern=pattern, dry_run=dry_run)

        return results

    return await with_db_session(_session_factory, operation)

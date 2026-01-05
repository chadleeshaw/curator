"""
File import routes
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from web.schemas import ImportOptionsRequest

router = APIRouter(prefix="/api/import", tags=["imports"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_file_importer = None
_storage_config = None


def set_dependencies(session_factory, file_importer, storage_config):
    """Set dependencies from main app"""
    global _session_factory, _file_importer, _storage_config
    _session_factory = session_factory
    _file_importer = file_importer
    _storage_config = storage_config


@router.post("/process")
async def import_from_downloads(background_tasks: BackgroundTasks, options: Optional[ImportOptionsRequest] = None) -> Dict[str, Any]:
    """
    Process PDFs from downloads folder and import them into the library.
    Runs asynchronously in background.

    Args:
        options: Optional import configuration

    Returns:
        Status of import operation
    """
    try:
        if not _file_importer:
            raise HTTPException(status_code=503, detail="File importer not available")

        def process_imports():
            """Background task to process imports"""
            try:
                db_session = _session_factory()
                try:
                    # Pass organization_pattern to file importer
                    org_pattern = options.organization_pattern if options else None
                    results = _file_importer.process_downloads(db_session, org_pattern)
                    logger.debug(f"Import completed: {results}")
                finally:
                    db_session.close()
            except Exception as e:
                logger.error(f"Error processing imports: {e}", exc_info=True)

        background_tasks.add_task(process_imports)

        return {
            "status": "processing",
            "message": "Started importing PDFs from downloads folder",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_import_status() -> Dict[str, Any]:
    """Get information about available files in downloads folder"""
    try:
        downloads_dir = Path(_storage_config.get("download_dir", "./downloads"))

        if not downloads_dir.exists():
            return {"ready": False, "files": 0, "message": "Downloads directory not found"}

        pdf_files = list(downloads_dir.glob("*.pdf"))

        return {
            "ready": len(pdf_files) > 0,
            "files": len(pdf_files),
            "file_list": [f.name for f in pdf_files],
            "message": f"Found {len(pdf_files)} PDF files ready to import",
        }

    except Exception as e:
        logger.error(f"Get import status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-organize-dir")
async def import_from_organize_dir(
    background_tasks: BackgroundTasks,
    auto_track: bool = True,
    organization_pattern: str = None
) -> Dict[str, Any]:
    """
    Import PDFs from the organized data directory back into the library.
    Useful for syncing files that exist in the organize directory but aren't in the database.

    Args:
        auto_track: Whether to auto-track newly imported periodicals
        organization_pattern: Optional organization pattern override for this import

    Returns:
        Status of import operation
    """
    try:
        if not _file_importer:
            raise HTTPException(status_code=503, detail="File importer not available")

        organize_dir = Path(_storage_config.get("organize_dir", "./local/data"))

        if not organize_dir.exists():
            raise HTTPException(status_code=400, detail=f"Organize directory not found: {organize_dir}")

        # Count PDFs available
        pdf_files = list(organize_dir.rglob("*.pdf"))

        if not pdf_files:
            return {
                "success": True,
                "imported": 0,
                "message": f"No PDFs found in organize directory: {organize_dir}",
            }

        def process_organize_dir_imports():
            """Background task to process imports from organize directory"""
            try:
                db_session = _session_factory()
                try:
                    # Temporarily override organization pattern if provided
                    original_pattern = _file_importer.organization_pattern
                    if organization_pattern:
                        _file_importer.organization_pattern = organization_pattern

                    results = _file_importer.process_organized_files(db_session, auto_track=auto_track)
                    logger.info(f"Organize directory import results: {results['imported']} imported, {results['failed']} failed")

                    # Restore original pattern
                    _file_importer.organization_pattern = original_pattern
                finally:
                    db_session.close()
            except Exception as e:
                logger.error(f"Error processing organize directory imports: {e}", exc_info=True)

        background_tasks.add_task(process_organize_dir_imports)

        return {
            "success": True,
            "imported": len(pdf_files),
            "message": f"Started importing {len(pdf_files)} PDFs from organize directory",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import from organize dir error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

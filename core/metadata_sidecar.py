"""
Metadata sidecar file utilities for preserving download tracking context.

Sidecar files (.curator_meta.json) are created alongside downloaded files to maintain
the association between files and their tracking records, even when filenames don't
contain enough information to determine the source.
"""

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

SIDECAR_SUFFIX = ".curator_meta.json"


def create_sidecar_file(
    file_path: Path,
    tracking_id: int,
    tracking_title: str,
    *,
    submission_id: Optional[int] = None,
    category: Optional[str] = None,
    language: Optional[str] = None,
    country: Optional[str] = None,
) -> bool:
    """
    Create a sidecar metadata file next to a downloaded file.

    Args:
        file_path: Path to the downloaded file (PDF/EPUB)
        tracking_id: ID of the tracking record that requested this download
        tracking_title: Title of the tracked periodical
        submission_id: Optional download submission ID
        category: Optional category (Magazines, Comics, etc.)
        language: Optional language code
        country: Optional country code

    Returns:
        True if sidecar file was created successfully, False otherwise
    """
    try:
        sidecar_path = file_path.with_suffix(file_path.suffix + SIDECAR_SUFFIX)

        metadata = {
            "tracking_id": tracking_id,
            "tracking_title": tracking_title,
            "downloaded_at": datetime.now(UTC).isoformat(),
            "original_filename": file_path.name,
        }

        if submission_id:
            metadata["submission_id"] = submission_id
        if category:
            metadata["category"] = category
        if language:
            metadata["language"] = language
        if country:
            metadata["country"] = country

        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.debug(f"Created sidecar file: {sidecar_path.name} for {file_path.name}")
        return True

    except Exception as e:
        logger.warning(f"Failed to create sidecar file for {file_path}: {e}")
        return False


def read_sidecar_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Read metadata from a sidecar file if it exists.

    Args:
        file_path: Path to the file (PDF/EPUB) - not the sidecar itself

    Returns:
        Dict with metadata if sidecar exists and is valid, None otherwise
    """
    try:
        sidecar_path = file_path.with_suffix(file_path.suffix + SIDECAR_SUFFIX)

        if not sidecar_path.exists():
            return None

        with open(sidecar_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Validate required fields
        if "tracking_id" not in metadata or "tracking_title" not in metadata:
            logger.warning(f"Invalid sidecar file (missing required fields): {sidecar_path.name}")
            return None

        logger.debug(f"Read sidecar file: {sidecar_path.name} -> tracking_id={metadata['tracking_id']}")
        return metadata

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in sidecar file {sidecar_path}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to read sidecar file for {file_path}: {e}")
        return None


def delete_sidecar_file(file_path: Path) -> bool:
    """
    Delete a sidecar metadata file.

    Args:
        file_path: Path to the file (PDF/EPUB) - not the sidecar itself

    Returns:
        True if sidecar was deleted or didn't exist, False if deletion failed
    """
    try:
        sidecar_path = file_path.with_suffix(file_path.suffix + SIDECAR_SUFFIX)

        if sidecar_path.exists():
            sidecar_path.unlink()
            logger.debug(f"Deleted sidecar file: {sidecar_path.name}")

        return True

    except Exception as e:
        logger.warning(f"Failed to delete sidecar file for {file_path}: {e}")
        return False


def has_sidecar_file(file_path: Path) -> bool:
    """
    Check if a sidecar file exists for the given file.

    Args:
        file_path: Path to the file (PDF/EPUB)

    Returns:
        True if sidecar file exists, False otherwise
    """
    sidecar_path = file_path.with_suffix(file_path.suffix + SIDECAR_SUFFIX)
    return sidecar_path.exists()

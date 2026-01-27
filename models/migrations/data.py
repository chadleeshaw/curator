"""
Data migrations - transformations of existing data after schema changes.

This module contains data transformation logic that runs automatically after schema migrations.
Called by DatabaseManager.run_migrations() after schema changes are applied.

Current migrations:
- migrate_metadata_structure: Transform periodical metadata from single to three-column structure
"""

import logging

from sqlalchemy.orm import Session

from core.utils.metadata_builder import build_derived_metadata
from models.database import Periodical

logger = logging.getLogger(__name__)


def _migrate_single_periodical(periodical: Periodical) -> bool:
    """
    Migrate a single periodical from old to new metadata structure.

    Args:
        periodical: Periodical record to migrate

    Returns:
        True if migration was performed, False if already migrated
    """
    # Skip if already migrated (has parsed_metadata)
    if periodical.parsed_metadata is not None:
        return False

    old_metadata = periodical.extra_metadata or {}

    # Step 1: Build file_scan from metadata that came from filename parsing
    file_scan = {}
    if old_metadata.get("parse_source"):
        file_scan["parse_source"] = old_metadata["parse_source"]
    if old_metadata.get("confidence") is not None:
        file_scan["confidence"] = old_metadata["confidence"]
    if old_metadata.get("year"):
        file_scan["year"] = old_metadata["year"]
    if old_metadata.get("month"):
        file_scan["month_name"] = old_metadata["month"]
    if old_metadata.get("issue_number"):
        file_scan["issue_number"] = old_metadata["issue_number"]
    if old_metadata.get("volume"):
        file_scan["volume"] = old_metadata["volume"]
    if old_metadata.get("country"):
        file_scan["country"] = old_metadata["country"]
    if old_metadata.get("full_title"):
        file_scan["full_title"] = old_metadata["full_title"]

    # Step 2: Build parsed_metadata with all scan results
    parsed_metadata = {}
    if file_scan:
        parsed_metadata["file_scan"] = file_scan

    # Extract text_scan (could be under different keys)
    if "text_scan" in old_metadata:
        parsed_metadata["text_scan"] = old_metadata["text_scan"]
    elif "text_metadata" in old_metadata:
        # Handle text_metadata from OCR queue's direct text extraction
        parsed_metadata["text_scan"] = old_metadata["text_metadata"]

    # Extract ocr_scan
    if "ocr_metadata" in old_metadata:
        parsed_metadata["ocr_scan"] = old_metadata["ocr_metadata"]

    # Step 3: Build derived_metadata using metadata_builder
    # This intelligently merges all scan sources with priority and confidence
    derived_metadata = build_derived_metadata(
        file_scan=parsed_metadata.get("file_scan"),
        text_scan=parsed_metadata.get("text_scan"),
        ocr_scan=parsed_metadata.get("ocr_scan"),
    )

    # Step 4: Build new extra_metadata with only import/provenance info
    new_extra_metadata = {}
    provenance_keys = ["imported_from", "import_date", "category", "import_method"]
    for key in provenance_keys:
        if key in old_metadata:
            new_extra_metadata[key] = old_metadata[key]

    # Step 5: Update periodical with new structure
    periodical.parsed_metadata = parsed_metadata
    periodical.derived_metadata = derived_metadata
    periodical.extra_metadata = new_extra_metadata

    # Step 6: Sync issue_date from derived_metadata (keeps it in sync with best available data)
    from core.utils.metadata_builder import sync_issue_date_from_derived

    new_issue_date = sync_issue_date_from_derived(derived_metadata)
    if new_issue_date:
        periodical.issue_date = new_issue_date

    return True


def migrate_metadata_structure(session: Session) -> int:
    """
    Migrate all periodicals from old to new metadata structure.

    This migration transforms the metadata structure from a single extra_metadata column
    to three separate columns: parsed_metadata, derived_metadata, and extra_metadata.

    Args:
        session: SQLAlchemy database session

    Returns:
        Number of records migrated

    Note:
        This migration is idempotent - safe to run multiple times.
        Records with parsed_metadata already set are skipped.
    """
    # Check if any periodicals need migration
    unmigrated_count = session.query(Periodical).filter(Periodical.parsed_metadata.is_(None)).count()

    if unmigrated_count == 0:
        logger.debug("No periodicals need metadata structure migration")
        return 0

    logger.info(f"Migrating metadata structure for {unmigrated_count} periodical(s)...")

    migrated_count = 0
    batch_size = 100

    # Process in batches
    for offset in range(0, unmigrated_count, batch_size):
        periodicals = (
            session.query(Periodical)
            .filter(Periodical.parsed_metadata.is_(None))
            .offset(offset)
            .limit(batch_size)
            .all()
        )

        for periodical in periodicals:
            if _migrate_single_periodical(periodical):
                migrated_count += 1

        # Commit batch
        session.commit()
        logger.debug(f"Migrated {offset + len(periodicals)}/{unmigrated_count} periodicals...")

    logger.info(f"✓ Migrated metadata structure for {migrated_count} periodical(s)")
    return migrated_count


def run_data_migrations(session: Session) -> dict:
    """
    Run all data migrations.

    This is called automatically by DatabaseManager.run_migrations() after
    schema changes are applied.

    Args:
        session: SQLAlchemy database session

    Returns:
        Dictionary with migration names and counts
    """
    results = {}

    # Run metadata structure migration
    results["metadata_structure"] = migrate_metadata_structure(session)

    return results

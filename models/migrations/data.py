"""
Data migrations - transformations of existing data after schema changes.

This module contains data transformation logic that runs automatically after schema migrations.
Called by DatabaseManager.run_migrations() after schema changes are applied.

Current migrations:
- migrate_metadata_structure: Transform periodical metadata from single to three-column structure
- migrate_discovered_issues_provider: Fix provider names from display names to routing types
"""

import logging

from sqlalchemy import String, cast, or_
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
    # Skip if already migrated. JSON null loads as None, and a literal
    # "null" string is the same unset value written by older drivers.
    if not _parsed_metadata_is_unset(periodical.parsed_metadata):
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


def _parsed_metadata_is_unset(value) -> bool:
    """True for SQL NULL, JSON null, and the literal null string."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() == "null":
        return True
    return False


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
    # SQL NULL and JSON null both mean the new columns were never written.
    # The ORM stores Python None as the text 'null', which IS NULL does not match.
    needs_migration = or_(Periodical.parsed_metadata.is_(None), cast(Periodical.parsed_metadata, String) == "null")
    unmigrated_count = session.query(Periodical).filter(needs_migration).count()

    if unmigrated_count == 0:
        logger.debug("No periodicals need metadata structure migration")
        return 0

    logger.info(f"Migrating metadata structure for {unmigrated_count} periodical(s)...")

    migrated_count = 0
    batch_size = 100

    # Re-query each batch. Offsetting a shrinking filter would skip rows.
    # Stop if a batch still matches the filter but none of its rows change,
    # which would otherwise spin forever.
    while True:
        periodicals = session.query(Periodical).filter(needs_migration).limit(batch_size).all()
        if not periodicals:
            break
        progressed = 0
        for periodical in periodicals:
            if _migrate_single_periodical(periodical):
                progressed += 1
        session.commit()
        migrated_count += progressed
        if progressed == 0:
            logger.warning("Stopping metadata migration; a batch made no progress")
            break

    logger.info(f"✓ Migrated metadata structure for {migrated_count} periodical(s)")
    return migrated_count


def migrate_discovered_issues_provider(session: Session) -> int:
    """
    Fix discovered_issues.latest_provider from display names to routing types.

    Old provider.name values like "IA" need to be converted to provider.type
    values like "internet_archive" for correct download client routing.

    Args:
        session: SQLAlchemy database session

    Returns:
        Number of records migrated

    Note:
        This migration is idempotent - safe to run multiple times.
    """
    from models.database import DiscoveredIssue

    provider_mapping = {
        "IA": "internet_archive",
        # Add more mappings as needed for other providers
    }

    migrated_count = 0

    for old_name, new_type in provider_mapping.items():
        # Find all discovered_issues with old provider name
        issues_to_update = session.query(DiscoveredIssue).filter(DiscoveredIssue.latest_provider == old_name).all()

        if issues_to_update:
            logger.info(
                f"Migrating {len(issues_to_update)} discovered_issues " f"from provider '{old_name}' to '{new_type}'"
            )

            for issue in issues_to_update:
                issue.latest_provider = new_type
                migrated_count += 1

            session.commit()

    if migrated_count > 0:
        logger.info(f"✓ Migrated provider names for {migrated_count} discovered_issue(s)")
    else:
        logger.debug("No discovered_issues need provider name migration")

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

    # Run discovered_issues provider migration
    results["discovered_issues_provider"] = migrate_discovered_issues_provider(session)

    return results

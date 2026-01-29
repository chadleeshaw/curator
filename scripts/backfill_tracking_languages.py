#!/usr/bin/env python
"""
Backfill missing language field in PeriodicalTracking table.

This script updates all tracking records that have NULL language by extracting
the language from their linked periodicals' metadata.
"""

import sys
from pathlib import Path

# Add parent directory to path to import from project
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import ConfigLoader
from core.database import DatabaseManager
from core.constants.language import DEFAULT_LANGUAGE
from models.database import PeriodicalTracking, Periodical


def backfill_tracking_languages(dry_run=True):
    """
    Backfill missing language field for all tracking records.

    Uses the language from linked periodicals to infer the tracking language.

    Args:
        dry_run: If True, only report what would be updated without making changes
    """
    config_loader = ConfigLoader()
    config = config_loader.config

    # Initialize database manager
    db_url = f"sqlite:///{config['database']['path']}"
    db_manager = DatabaseManager(db_url)

    session = db_manager.session_factory()
    try:
        # Find all tracking records with NULL or empty language
        tracking_records = (
            session.query(PeriodicalTracking)
            .filter((PeriodicalTracking.language == None) | (PeriodicalTracking.language == ""))  # noqa: E711
            .all()
        )

        print(f"Found {len(tracking_records)} tracking records with missing language field")

        updated_count = 0
        for tracking in tracking_records:
            language = None

            # Get language from any linked periodical
            periodical = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).first()

            if periodical:
                # Try periodical.language first
                if periodical.language:
                    language = periodical.language
                # Try derived_metadata
                elif periodical.derived_metadata and isinstance(periodical.derived_metadata, dict):
                    lang_data = periodical.derived_metadata.get("language")
                    if lang_data:
                        if isinstance(lang_data, dict):
                            language = lang_data.get("value")
                        else:
                            language = lang_data
                # Try parsed_metadata
                elif periodical.parsed_metadata:
                    if isinstance(periodical.parsed_metadata, dict):
                        file_scan = periodical.parsed_metadata.get("file_scan", {})
                        if isinstance(file_scan, dict):
                            language = file_scan.get("language")

            # Default to English if still no language found
            if not language:
                language = DEFAULT_LANGUAGE

            if dry_run:
                print(f"  Would update tracking #{tracking.id} '{tracking.title}' → language='{language}'")
            else:
                tracking.language = language
                updated_count += 1

        if not dry_run:
            session.commit()
            print(f"\n✅ Updated {updated_count} tracking records with language field")
        else:
            print(f"\n🔍 Dry run complete. Run with --apply to update {len(tracking_records)} tracking records")

    finally:
        session.close()


if __name__ == "__main__":
    # Check for --apply flag
    apply = "--apply" in sys.argv

    if apply:
        print("🚀 Applying tracking language backfill...")
        backfill_tracking_languages(dry_run=False)
    else:
        print("🔍 Running in dry-run mode (use --apply to make changes)...")
        backfill_tracking_languages(dry_run=True)

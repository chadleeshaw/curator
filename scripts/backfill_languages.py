#!/usr/bin/env python
"""
Backfill missing language field in Periodical table.

This script updates all periodicals that have NULL language by extracting
the language from their derived_metadata or parsed_metadata fields.
"""

import sys
from pathlib import Path

# Add parent directory to path to import from project
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import ConfigLoader
from core.database import session_factory
from core.constants.language import DEFAULT_LANGUAGE
from models.database import Periodical


def backfill_languages(dry_run=True):
    """
    Backfill missing language field for all periodicals.

    Args:
        dry_run: If True, only report what would be updated without making changes
    """
    config_loader = ConfigLoader()
    config = config_loader.config
    _session_factory = session_factory(config)

    session = _session_factory()
    try:
        # Find all periodicals with NULL or empty language
        periodicals = session.query(Periodical).filter(
            (Periodical.language == None) | (Periodical.language == "")  # noqa: E711
        ).all()

        print(f"Found {len(periodicals)} periodicals with missing language field")

        updated_count = 0
        for periodical in periodicals:
            language = None

            # Try to get language from derived_metadata first (most reliable)
            if periodical.derived_metadata and isinstance(periodical.derived_metadata, dict):
                lang_data = periodical.derived_metadata.get("language")
                if lang_data:
                    if isinstance(lang_data, dict):
                        language = lang_data.get("value")
                    else:
                        language = lang_data

            # Fallback to parsed_metadata
            if not language and periodical.parsed_metadata:
                if isinstance(periodical.parsed_metadata, dict):
                    file_scan = periodical.parsed_metadata.get("file_scan", {})
                    if isinstance(file_scan, dict):
                        language = file_scan.get("language")

            # Fallback to extra_metadata (legacy)
            if not language and periodical.extra_metadata:
                if isinstance(periodical.extra_metadata, dict):
                    language = periodical.extra_metadata.get("language")

            # Default to English if still no language found
            if not language:
                language = DEFAULT_LANGUAGE

            if dry_run:
                print(f"  Would update #{periodical.id} '{periodical.title}' → language='{language}'")
            else:
                periodical.language = language
                updated_count += 1

        if not dry_run:
            session.commit()
            print(f"\n✅ Updated {updated_count} periodicals with language field")
        else:
            print(f"\n🔍 Dry run complete. Run with --apply to update {len(periodicals)} periodicals")

    finally:
        session.close()


if __name__ == "__main__":
    # Check for --apply flag
    apply = "--apply" in sys.argv

    if apply:
        print("🚀 Applying language backfill...")
        backfill_languages(dry_run=False)
    else:
        print("🔍 Running in dry-run mode (use --apply to make changes)...")
        backfill_languages(dry_run=True)

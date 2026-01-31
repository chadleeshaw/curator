#!/usr/bin/env python3
"""
Synchronize language fields between tracking records and periodicals.

This script helps fix language inconsistencies where:
1. Periodicals linked to tracking have different languages than their tracking record
2. Tracking records have no language set but their periodicals do

Run this after upgrading to ensure all periodical languages match their tracking records.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import ConfigLoader
from core.database import DatabaseManager
from models.database import Periodical, PeriodicalTracking

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def sync_tracking_languages(dry_run: bool = True) -> None:
    """
    Synchronize language fields between tracking and periodicals.

    Args:
        dry_run: If True, only report what would be changed without making changes
    """
    # Load config to get database URL
    config_loader = ConfigLoader()
    storage_config = config_loader.get_storage()
    db_url = f"sqlite:///{storage_config.get('db_path', './local/data/periodicals.db')}"

    db_manager = DatabaseManager(db_url)
    db_manager.create_tables()
    session = db_manager.session_factory()

    try:
        # Get all tracking records
        tracking_records = session.query(PeriodicalTracking).all()
        logger.info(f"Found {len(tracking_records)} tracking records")

        total_periodicals_updated = 0
        total_tracking_updated = 0
        changes = []

        for tracking in tracking_records:
            # Get all periodicals linked to this tracking
            periodicals = session.query(Periodical).filter(Periodical.tracking_id == tracking.id).all()

            if not periodicals:
                continue

            # Determine the correct language
            if tracking.language:
                # Tracking has a language - periodicals should match
                correct_language = tracking.language
                for periodical in periodicals:
                    if periodical.language != correct_language:
                        change = {
                            "type": "periodical",
                            "tracking_id": tracking.id,
                            "tracking_title": tracking.title,
                            "periodical_id": periodical.id,
                            "periodical_title": periodical.title,
                            "old_language": periodical.language,
                            "new_language": correct_language,
                        }
                        changes.append(change)

                        if not dry_run:
                            periodical.language = correct_language

                        total_periodicals_updated += 1
            else:
                # Tracking has no language - use most common language from periodicals
                languages = [p.language for p in periodicals if p.language]
                if languages:
                    # Use most common language
                    from collections import Counter

                    most_common_lang = Counter(languages).most_common(1)[0][0]

                    change = {
                        "type": "tracking",
                        "tracking_id": tracking.id,
                        "tracking_title": tracking.title,
                        "old_language": None,
                        "new_language": most_common_lang,
                        "periodical_count": len(periodicals),
                    }
                    changes.append(change)

                    if not dry_run:
                        tracking.language = most_common_lang

                        # Also update all periodicals to match
                        for periodical in periodicals:
                            if periodical.language != most_common_lang:
                                periodical.language = most_common_lang
                                total_periodicals_updated += 1

                    total_tracking_updated += 1

        if not dry_run:
            session.commit()
            logger.info("✅ Changes committed to database")
        else:
            logger.info("🔍 DRY RUN - No changes made")

        # Report changes
        logger.info(f"\n{'=' * 80}")
        logger.info("SUMMARY")
        logger.info(f"{'=' * 80}")
        logger.info(f"Tracking records updated: {total_tracking_updated}")
        logger.info(f"Periodical records updated: {total_periodicals_updated}")
        logger.info(f"Total changes: {len(changes)}")

        if changes:
            logger.info(f"\n{'=' * 80}")
            logger.info("DETAILED CHANGES")
            logger.info(f"{'=' * 80}\n")

            for change in changes:
                if change["type"] == "periodical":
                    logger.info(
                        f"📄 Periodical #{change['periodical_id']} - {change['periodical_title']}\n"
                        f"   Tracking: {change['tracking_title']} (#{change['tracking_id']})\n"
                        f"   Language: {change['old_language']} → {change['new_language']}\n"
                    )
                else:  # tracking
                    logger.info(
                        f"📌 Tracking #{change['tracking_id']} - {change['tracking_title']}\n"
                        f"   Language: {change['old_language']} → {change['new_language']}\n"
                        f"   Affects {change['periodical_count']} periodicals\n"
                    )

    except Exception as e:
        logger.error(f"Error during sync: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Synchronize language fields between tracking and periodicals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would change
  python scripts/sync_tracking_languages.py

  # Actually apply the changes
  python scripts/sync_tracking_languages.py --apply

  # Run with verbose logging
  python scripts/sync_tracking_languages.py --apply --verbose
        """,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes (default is dry run)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.apply:
        logger.info("🔍 Running in DRY RUN mode - no changes will be made")
        logger.info("   Use --apply to actually make changes\n")

    sync_tracking_languages(dry_run=not args.apply)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Script to fix incorrectly parsed dates in the database.

This script re-parses all periodical filenames and updates the database
with the correct issue_date, year, and month information.
"""

import logging
from pathlib import Path
from datetime import datetime

from core.config import ConfigLoader
from core.database import DatabaseManager
from core.parsers import Parser
from models.database import Periodical

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fix_incorrect_dates(dry_run: bool = True):
    """
    Re-parse all periodical filenames and fix incorrect dates.

    Args:
        dry_run: If True, only log what would be changed without making changes
    """
    # Load config and initialize database
    config_loader = ConfigLoader()
    storage_config = config_loader.get_storage()
    db_path = storage_config.get("db_path", "./local/data/periodicals.db")
    db_url = f"sqlite:///{db_path}"

    db_manager = DatabaseManager(db_url)
    session = db_manager.session_factory()
    parser = Parser()

    try:
        # Get all periodicals
        periodicals = session.query(Periodical).all()
        logger.info(f"Found {len(periodicals)} periodicals in database")

        fixed_count = 0
        error_count = 0
        current_date = datetime.now()

        for periodical in periodicals:
            try:
                # Skip if no file_path
                if not periodical.file_path:
                    logger.debug(f"Skipping ID {periodical.id}: No file_path")
                    continue

                file_path = Path(periodical.file_path)

                # Check if current date looks suspicious (within 30 days of current date)
                if periodical.issue_date:
                    days_diff = abs((periodical.issue_date - current_date).days)
                    if days_diff > 30:
                        # Date looks reasonable, skip
                        continue

                # Re-parse the filename
                parsed = parser.parse_file(file_path)

                # Check if parsed date is different
                if parsed.issue_date != periodical.issue_date:
                    old_date_str = periodical.issue_date.strftime("%Y-%m-%d") if periodical.issue_date else "None"
                    new_date_str = parsed.issue_date.strftime("%Y-%m-%d") if parsed.issue_date else "None"

                    logger.info(
                        f"ID {periodical.id}: '{periodical.title}' - "
                        f"Old date: {old_date_str} -> New date: {new_date_str} "
                        f"(file: {file_path.name}, pattern: {parsed.matched_pattern})"
                    )

                    if not dry_run:
                        periodical.issue_date = parsed.issue_date
                        periodical.year = parsed.year
                        periodical.month = parsed.month

                        # Update extra_metadata with month_name if available
                        if parsed.month_name:
                            if not periodical.extra_metadata:
                                periodical.extra_metadata = {}
                            periodical.extra_metadata["month_name"] = parsed.month_name

                    fixed_count += 1

            except Exception as e:
                logger.error(f"Error processing periodical ID {periodical.id} ('{periodical.title}'): {e}")
                error_count += 1
                continue

        if not dry_run:
            session.commit()
            logger.info(f"Successfully fixed {fixed_count} periodicals")
        else:
            logger.info(f"DRY RUN: Would fix {fixed_count} periodicals")

        if error_count > 0:
            logger.warning(f"Encountered {error_count} errors during processing")

    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser_arg = argparse.ArgumentParser(description="Fix incorrectly parsed dates in the database")
    parser_arg.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the fixes (default is dry-run mode)",
    )
    args = parser_arg.parse_args()

    logger.info("=" * 80)
    if args.apply:
        logger.info("RUNNING IN APPLY MODE - Changes will be made to the database")
    else:
        logger.info("RUNNING IN DRY-RUN MODE - No changes will be made")
    logger.info("=" * 80)

    fix_incorrect_dates(dry_run=not args.apply)

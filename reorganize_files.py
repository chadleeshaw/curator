#!/usr/bin/env python3
"""
Script to reorganize existing files in the organized directory.
This will clean up messy folder structures from early imports and ensure
all files follow the proper organization pattern.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from core.config import ConfigLoader
from models.database import init_db
from services.file_organizer import FileOrganizer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Reorganize all files in the organized directory based on database metadata."""

    # Load configuration
    config = ConfigLoader.load()

    # Initialize database
    db_path = config.get("storage", {}).get("db_path", "./local/config/periodicals.db")
    session_factory = init_db(db_path)
    session = session_factory()

    try:
        # Get organization settings
        organize_dir = config.get("storage", {}).get("organize_dir", "./local/data")
        organization_pattern = config.get("import", {}).get(
            "organization_pattern", "{category}/{title}/{year}/"
        )
        category_prefix = config.get("import", {}).get("category_prefix", "_")

        logger.info(f"Organize directory: {organize_dir}")
        logger.info(f"Organization pattern: {organization_pattern}")
        logger.info(f"Category prefix: {category_prefix}")

        # Create file organizer
        organizer = FileOrganizer(organize_dir, category_prefix=category_prefix)

        # Ask user for confirmation
        print("\n" + "=" * 80)
        print("REORGANIZATION PREVIEW")
        print("=" * 80)
        print(f"This will reorganize all files in: {organize_dir}")
        print(f"Pattern: {organization_pattern}")
        print()
        print("This operation will:")
        print("  1. Move files to correct folders based on database metadata")
        print("  2. Remove old empty/messy directories")
        print("  3. Update database paths to match new locations")
        print()

        # Dry run first to show what will be done
        print("Running dry run to preview changes...\n")

        categories = ["Magazines", "Comics", "Articles", "News"]

        for category in categories:
            category_dir = Path(organize_dir) / f"{category_prefix}{category}"
            if not category_dir.exists():
                continue

            print(f"\n--- Checking {category} ---")
            results = organizer.reorganize_from_database(
                session,
                category=category,
                pattern=organization_pattern,
                dry_run=True,
            )

            if results.get("success"):
                print(f"  Files found: {results.get('files_found', 0)}")
                print(f"  Files to reorganize: {results.get('files_reorganized', 0)}")
                print(f"  Files already correct: {results.get('files_skipped', 0)}")

                if results.get("errors"):
                    print(f"  Errors: {len(results.get('errors', []))}")
                    for error in results.get("errors", [])[:3]:  # Show first 3 errors
                        print(f"    - {error}")
            else:
                print(f"  Error: {results.get('error')}")

        print("\n" + "=" * 80)
        response = (
            input("\nDo you want to proceed with reorganization? (yes/no): ")
            .strip()
            .lower()
        )

        if response not in ["yes", "y"]:
            print("Reorganization cancelled.")
            return

        # Run actual reorganization
        print("\nStarting reorganization...\n")

        for category in categories:
            category_dir = Path(organize_dir) / f"{category_prefix}{category}"
            if not category_dir.exists():
                continue

            print(f"\n--- Reorganizing {category} ---")
            results = organizer.reorganize_from_database(
                session,
                category=category,
                pattern=organization_pattern,
                dry_run=False,
            )

            if results.get("success"):
                print(f"  ✓ Files reorganized: {results.get('files_reorganized', 0)}")
                print(f"  ✓ Files already correct: {results.get('files_skipped', 0)}")

                if results.get("errors"):
                    print(f"  ⚠ Errors: {len(results.get('errors', []))}")
                    for error in results.get("errors", []):
                        print(f"    - {error}")
            else:
                print(f"  ✗ Error: {results.get('error')}")

        print("\n" + "=" * 80)
        print("Reorganization complete!")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Error during reorganization: {e}", exc_info=True)
        return 1
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

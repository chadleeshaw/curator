#!/usr/bin/env python3
"""
Script to diagnose and fix download queue issues.
Shows status of downloads and can clear stuck downloads.
"""

import sys
import logging
from pathlib import Path
from collections import Counter

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import ConfigLoader
from core.database import DatabaseManager
from models.database import DownloadSubmission

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def diagnose_downloads():
    """Diagnose download queue status"""

    # Load configuration
    config_loader = ConfigLoader()
    storage_config = config_loader.get_storage()

    # Initialize database
    db_path = storage_config.get("db_path", "./local/config/periodicals.db")
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    db_manager.create_tables()

    session_factory = db_manager.session_factory
    db_session = session_factory()

    try:
        # Count downloads by status
        from sqlalchemy import func

        status_counts = (
            db_session.query(DownloadSubmission.status, func.count(DownloadSubmission.id))
            .group_by(DownloadSubmission.status)
            .all()
        )

        print("📊 Download Queue Status:")
        print("=" * 40)

        total = 0
        for status, count in status_counts:
            print(f"  {status.value}: {count}")
            total += count

        print(f"  Total: {total}")
        print()

        # Check for stuck downloads
        from datetime import datetime, timedelta

        # Downloads that have been pending too long (stuck)
        stuck_threshold = datetime.now() - timedelta(hours=1)
        stuck_pending = (
            db_session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING,
                DownloadSubmission.created_at < stuck_threshold,
            )
            .all()
        )

        stuck_downloading = (
            db_session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status == DownloadSubmission.StatusEnum.DOWNLOADING,
                DownloadSubmission.created_at < stuck_threshold,
            )
            .all()
        )

        if stuck_pending or stuck_downloading:
            print("⚠️  Potentially Stuck Downloads:")
            print("-" * 40)

            for download in stuck_pending:
                age_hours = (datetime.now() - download.created_at).total_seconds() / 3600
                print(f"    PENDING: {download.result_title} ({age_hours:.1f}h old)")
            for download in stuck_downloading:
                age_hours = (datetime.now() - download.created_at).total_seconds() / 3600
                print(f"    DOWNLOADING: {download.result_title} ({age_hours:.1f}h old)")
            print()

        # Show recent activity
        recent = (
            db_session.query(DownloadSubmission)
            .filter(DownloadSubmission.created_at > datetime.now() - timedelta(minutes=30))
            .order_by(DownloadSubmission.created_at.desc())
            .limit(5)
            .all()
        )

        if recent:
            print("🕒 Recent Download Activity (last 30 min):")
            print("-" * 40)
            for download in recent:
                print(
                    f"  {download.created_at.strftime('%H:%M:%S')} - {download.status.value} - {download.result_title}"
                )
            print()

        return {
            "total": total,
            "by_status": dict(status_counts),
            "stuck_pending": len(stuck_pending),
            "stuck_downloading": len(stuck_downloading),
        }

    except Exception as e:
        logger.error(f"Error diagnosing downloads: {e}")
        return {"error": str(e)}
    finally:
        db_session.close()


def clear_stuck_downloads():
    """Clear downloads that appear to be stuck"""

    # Load configuration
    config_loader = ConfigLoader()
    storage_config = config_loader.get_storage()

    # Initialize database
    db_path = storage_config.get("db_path", "./local/config/periodicals.db")
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    db_manager.create_tables()

    session_factory = db_manager.session_factory
    db_session = session_factory()

    try:
        from datetime import datetime, timedelta

        # Find stuck downloads (older than 2 hours)
        stuck_threshold = datetime.now() - timedelta(hours=2)

        stuck_downloads = (
            db_session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                    ]
                ),
                DownloadSubmission.created_at < stuck_threshold,
            )
            .all()
        )

        count = len(stuck_downloads)

        if count == 0:
            print("✅ No stuck downloads found to clear")
            return {"cleared": 0}

        print(f"🧹 Clearing {count} stuck downloads...")

        for download in stuck_downloads:
            print(
                f"  Clearing: {download.result_title} (status: {download.status.value}, age: {(datetime.now() - download.created_at).total_seconds() / 3600:.1f}h)"
            )
            db_session.delete(download)

        db_session.commit()
        print(f"✅ Cleared {count} stuck downloads")

        return {"cleared": count}

    except Exception as e:
        logger.error(f"Error clearing stuck downloads: {e}")
        db_session.rollback()
        return {"error": str(e)}
    finally:
        db_session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose and fix download queue issues")
    parser.add_argument("--clear-stuck", action="store_true", help="Clear stuck downloads")
    parser.add_argument("--diagnose", action="store_true", help="Show download queue status")

    args = parser.parse_args()

    if args.clear_stuck:
        result = clear_stuck_downloads()
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            sys.exit(1)
    elif args.diagnose:
        result = diagnose_downloads()
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            sys.exit(1)
    else:
        # Default: diagnose
        result = diagnose_downloads()
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            sys.exit(1)

#!/usr/bin/env python3
"""
Diagnostic script to check OCR queue status and suggest fixes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import ConfigLoader
from core.database import DatabaseManager
from models.database import Magazine, OCRJob
from services.ocr.service import OCRService


def main():
    print("=" * 60)
    print("OCR Queue Diagnostic Report")
    print("=" * 60)

    # Check OCR availability
    print("\n1. OCR Service Availability")
    print("-" * 60)
    ocr_available = OCRService.is_available()
    print(f"   OCR Available: {'✅ YES' if ocr_available else '❌ NO'}")

    if not ocr_available:
        print("\n   ⚠️  OCR is not available. Install with:")
        print("      pip install pytesseract paddleocr")
        return

    # Load config
    config_loader = ConfigLoader()
    storage_config = config_loader.get_storage()

    # Connect to database
    db_url = f"sqlite:///{storage_config.get('db_path', './data/periodicals.db')}"
    db_manager = DatabaseManager(db_url)
    session = db_manager.session_factory()

    try:
        # Check magazines
        print("\n2. Magazine Statistics")
        print("-" * 60)
        total_magazines = session.query(Magazine).count()
        magazines_with_covers = session.query(Magazine).filter(Magazine.cover_path.isnot(None)).count()
        print(f"   Total Magazines: {total_magazines}")
        print(f"   Magazines with Covers: {magazines_with_covers}")

        # Check OCR jobs
        print("\n3. OCR Job Statistics")
        print("-" * 60)
        total_jobs = session.query(OCRJob).count()
        pending_jobs = session.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.PENDING).count()
        processing_jobs = session.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.PROCESSING).count()
        completed_jobs = session.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.COMPLETED).count()
        failed_jobs = session.query(OCRJob).filter(OCRJob.status == OCRJob.StatusEnum.FAILED).count()

        print(f"   Total Jobs: {total_jobs}")
        print(f"   ├─ Pending: {pending_jobs}")
        print(f"   ├─ Processing: {processing_jobs}")
        print(f"   ├─ Completed: {completed_jobs}")
        print(f"   └─ Failed: {failed_jobs}")

        # Check magazines without OCR jobs
        print("\n4. Coverage Analysis")
        print("-" * 60)
        magazines_with_jobs = session.query(Magazine).join(OCRJob, Magazine.id == OCRJob.magazine_id).distinct().count()
        magazines_without_jobs = total_magazines - magazines_with_jobs

        print(f"   Magazines with OCR Jobs: {magazines_with_jobs}")
        print(f"   Magazines without OCR Jobs: {magazines_without_jobs}")

        if magazines_without_jobs > 0:
            print(f"\n   ℹ️  {magazines_without_jobs} magazines have never been queued for OCR")
            print("      These are likely older imports from before OCR was enabled.")

        # Show recent pending jobs
        if pending_jobs > 0:
            print("\n5. Recent Pending Jobs (Top 5)")
            print("-" * 60)
            recent_pending = (
                session.query(OCRJob)
                .filter(OCRJob.status == OCRJob.StatusEnum.PENDING)
                .order_by(OCRJob.created_at.desc())
                .limit(5)
                .all()
            )

            for job in recent_pending:
                magazine = session.query(Magazine).filter(Magazine.id == job.magazine_id).first()
                print(f"   Job {job.id}: {magazine.title if magazine else 'Unknown'}")
                print(f"      Priority: {job.priority}, Created: {job.created_at}")

        # Show failed jobs
        if failed_jobs > 0:
            print("\n6. Recent Failed Jobs (Top 5)")
            print("-" * 60)
            recent_failed = (
                session.query(OCRJob)
                .filter(OCRJob.status == OCRJob.StatusEnum.FAILED)
                .order_by(OCRJob.created_at.desc())
                .limit(5)
                .all()
            )

            for job in recent_failed:
                magazine = session.query(Magazine).filter(Magazine.id == job.magazine_id).first()
                print(f"   Job {job.id}: {magazine.title if magazine else 'Unknown'}")
                print(f"      Error: {job.last_error}")
                print(f"      Attempts: {job.attempt_count}")

        # Recommendations
        print("\n7. Recommendations")
        print("-" * 60)

        if total_jobs == 0:
            print("   🔧 No OCR jobs found in database")
            print("      • Try importing a new magazine to test if OCR queueing works")
            print("      • Or manually queue a job: POST /api/ocr/queue/{magazine_id}")

        elif pending_jobs == 0 and completed_jobs == 0 and failed_jobs == 0:
            print("   ℹ️  All jobs have been processed")

        elif pending_jobs > 0:
            print(f"   ⏳ {pending_jobs} jobs pending")
            print("      • Check OCR processor logs")
            print("      • Verify OCR processor task is running (auto-OCR every 10s)")

        if magazines_without_jobs > 0:
            print(f"\n   💡 To queue OCR for {magazines_without_jobs} existing magazines:")
            print("      • Use the OCR queue page to manually queue magazines")
            print("      • Or use the API: POST /api/ocr/queue/{magazine_id}")

    finally:
        session.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

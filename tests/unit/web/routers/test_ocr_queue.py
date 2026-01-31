"""
Test suite for OCR queue router endpoints
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, OCRJob, Periodical
from web.routers import ocr_queue


@pytest.fixture
def test_db():
    """Create file-based test database"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_periodical(test_db):
    """Create sample periodical for testing"""
    engine, session_factory = test_db
    session = session_factory()
    periodical = Periodical(
        title="Test Magazine",
        category="Magazine",
        file_path="test/path.pdf",
        issue_date=datetime.now(UTC),
    )
    session.add(periodical)
    session.commit()
    periodical_id = periodical.id
    session.close()
    return periodical_id


class TestGetOcrQueue:
    """Test GET /api/ocr/queue endpoint"""

    def test_get_ocr_queue_all(self, test_db):
        """Test getting all OCR jobs"""
        from datetime import datetime, UTC
        from models.database import Periodical

        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        # Create test periodicals first
        mag1 = Periodical(id=1, title="Test Magazine 1", issue_date=datetime.now(UTC), file_path="/test/mag1.pdf")
        mag2 = Periodical(id=2, title="Test Magazine 2", issue_date=datetime.now(UTC), file_path="/test/mag2.pdf")
        session.add_all([mag1, mag2])
        session.flush()

        # Create test jobs
        job1 = OCRJob(periodical_id=1, status=OCRJob.StatusEnum.PENDING, priority=1)
        job2 = OCRJob(periodical_id=2, status=OCRJob.StatusEnum.COMPLETED, priority=2)
        session.add_all([job1, job2])
        session.commit()
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.get("/api/ocr/queue")
            assert response.status_code == 200
            data = response.json()
            assert "jobs" in data
            assert len(data["jobs"]) == 2

    def test_get_ocr_queue_filtered(self, test_db):
        """Test getting OCR jobs filtered by status"""
        from datetime import datetime, UTC
        from models.database import Periodical

        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        # Create test periodicals first
        mag1 = Periodical(id=1, title="Test Magazine 1", issue_date=datetime.now(UTC), file_path="/test/mag1.pdf")
        mag2 = Periodical(id=2, title="Test Magazine 2", issue_date=datetime.now(UTC), file_path="/test/mag2.pdf")
        session.add_all([mag1, mag2])
        session.flush()

        job1 = OCRJob(periodical_id=1, status=OCRJob.StatusEnum.PENDING, priority=1)
        job2 = OCRJob(periodical_id=2, status=OCRJob.StatusEnum.COMPLETED, priority=2)
        session.add_all([job1, job2])
        session.commit()
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.get("/api/ocr/queue?status=pending")
            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["status"] == "pending"


class TestGetOcrStats:
    """Test GET /api/ocr/queue/stats endpoint"""

    def test_get_ocr_stats_success(self, test_db):
        """Test getting OCR queue statistics"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        # Create jobs with different statuses
        session.add_all(
            [
                OCRJob(periodical_id=1, status=OCRJob.StatusEnum.PENDING, priority=1),
                OCRJob(periodical_id=2, status=OCRJob.StatusEnum.COMPLETED, priority=2),
                OCRJob(periodical_id=3, status=OCRJob.StatusEnum.FAILED, priority=1),
            ]
        )
        session.commit()
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.get("/api/ocr/queue/stats")
            assert response.status_code == 200
            data = response.json()
            assert "total" in data
            assert "pending" in data
            assert "completed" in data
            assert "failed" in data
            assert data["total"] == 3


class TestRetryOcrJob:
    """Test POST /api/ocr/retry/{job_id} endpoint"""

    def test_retry_ocr_job_success(self, test_db):
        """Test retrying a failed OCR job"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        job = OCRJob(periodical_id=1, status=OCRJob.StatusEnum.FAILED, priority=1)
        session.add(job)
        session.commit()
        job_id = job.id
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.post(f"/api/ocr/retry/{job_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"

    def test_retry_ocr_job_not_found(self, test_db):
        """Test retrying non-existent job"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.post("/api/ocr/retry/99999")
            assert response.status_code == 404


class TestClearFailedOcrJobs:
    """Test DELETE /api/ocr/queue/failed endpoint"""

    def test_clear_failed_jobs_success(self, test_db):
        """Test clearing failed OCR jobs"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        session.add_all(
            [
                OCRJob(periodical_id=1, status=OCRJob.StatusEnum.FAILED, priority=1),
                OCRJob(periodical_id=2, status=OCRJob.StatusEnum.FAILED, priority=2),
                OCRJob(periodical_id=3, status=OCRJob.StatusEnum.COMPLETED, priority=1),
            ]
        )
        session.commit()
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.delete("/api/ocr/queue/failed")
            assert response.status_code == 200
            data = response.json()
            assert "count" in data
            assert data["count"] == 2


class TestClearPendingOcrJobs:
    """Test DELETE /api/ocr/queue endpoint"""

    def test_clear_pending_jobs_success(self, test_db):
        """Test clearing pending OCR jobs"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        session.add_all(
            [
                OCRJob(periodical_id=1, status=OCRJob.StatusEnum.PENDING, priority=1),
                OCRJob(periodical_id=2, status=OCRJob.StatusEnum.PENDING, priority=2),
                OCRJob(periodical_id=3, status=OCRJob.StatusEnum.COMPLETED, priority=1),
            ]
        )
        session.commit()
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.delete("/api/ocr/queue")
            assert response.status_code == 200
            data = response.json()
            assert "count" in data
            assert data["count"] == 2


class TestDeleteOcrJob:
    """Test DELETE /api/ocr/queue/{job_id} endpoint"""

    def test_delete_ocr_job_success(self, test_db):
        """Test deleting a specific OCR job"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)
        session = session_factory()

        job = OCRJob(periodical_id=1, status=OCRJob.StatusEnum.FAILED, priority=1)
        session.add(job)
        session.commit()
        job_id = job.id
        session.close()

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.delete(f"/api/ocr/queue/{job_id}")
            assert response.status_code == 200
            data = response.json()
            assert "message" in data

    def test_delete_ocr_job_not_found(self, test_db):
        """Test deleting non-existent job"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.delete("/api/ocr/queue/99999")
            assert response.status_code == 404


class TestQueueMagazineOcr:
    """Test POST /api/ocr/queue/{magazine_id} endpoint"""

    def test_queue_magazine_ocr_success(self, test_db, sample_periodical):
        """Test queuing a magazine for OCR"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.post(f"/api/ocr/queue/{sample_periodical}")
            assert response.status_code == 200
            data = response.json()
            assert "message" in data or "job" in data

    def test_queue_magazine_ocr_not_found(self, test_db):
        """Test queuing non-existent magazine"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.post("/api/ocr/queue/99999")
            assert response.status_code == 404

    def test_queue_magazine_ocr_custom_priority(self, test_db, sample_periodical):
        """Test queuing magazine with custom priority"""
        engine, session_factory = test_db
        ocr_queue.set_dependencies(session_factory)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(ocr_queue.router)

        with TestClient(app) as client:
            response = client.post(f"/api/ocr/queue/{sample_periodical}?priority=5")
            assert response.status_code == 200
            data = response.json()
            assert "message" in data or "job" in data

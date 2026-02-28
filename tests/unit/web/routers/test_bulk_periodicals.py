"""
Tests for bulk operations on periodicals (move, delete).
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, Periodical, PeriodicalTracking

# Import the periodicals router package
from web.routers.periodicals import _shared
from web.routers.auth import get_verify_token

# Ensure bulk module routes are registered
import web.routers.periodicals.bulk  # noqa: F401


@pytest.fixture
def test_db():
    """Create a file-based SQLite test database."""
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
def test_app(test_db, tmp_path):
    """Create a minimal FastAPI app with the periodicals router."""
    engine, session_factory = test_db
    library_dir = tmp_path / "library"
    library_dir.mkdir()

    _shared.set_dependencies(
        session_factory=session_factory,
        library_base_dir=str(library_dir),
        category_prefix="_",
    )

    app = FastAPI(title="Test Bulk Operations")
    app.include_router(_shared.router)
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    return app


@pytest.fixture
def test_client(test_app):
    """Create a test client."""
    with TestClient(test_app) as client:
        yield client


@pytest.fixture
def tracking_records(test_db):
    """Create two tracking records for testing."""
    _, session_factory = test_db
    session = session_factory()
    try:
        tracking_a = PeriodicalTracking(
            olid="OL_TEST_A",
            title="Magazine A",
            language="English",
            category="Magazines",
            user_id=1,
        )
        tracking_b = PeriodicalTracking(
            olid="OL_TEST_B",
            title="Magazine B",
            language="English",
            category="Magazines",
            user_id=1,
        )
        session.add_all([tracking_a, tracking_b])
        session.commit()
        return tracking_a.id, tracking_b.id
    finally:
        session.close()


@pytest.fixture
def sample_issues(test_db, tracking_records, tmp_path):
    """Create sample periodicals linked to tracking_a."""
    _, session_factory = test_db
    tracking_a_id, _ = tracking_records
    session = session_factory()

    # Create actual files for them
    library_dir = tmp_path / "library"
    library_dir.mkdir(exist_ok=True)

    issue_ids = []
    for i in range(3):
        file_path = library_dir / f"issue_{i}.pdf"
        file_path.write_text("fake pdf content")
        issue = Periodical(
            title="Magazine A",
            language="English",
            category="Magazines",
            file_path=str(file_path),
            tracking_id=tracking_a_id,
            issue_date=datetime(2024, i + 1, 1),
            user_id=1,
        )
        session.add(issue)
        session.flush()
        issue_ids.append(issue.id)

    session.commit()
    session.close()
    return issue_ids


class TestBulkMoveToTracking:
    """Tests for POST /api/periodicals/bulk/move-to-tracking"""

    def test_bulk_move_success(self, test_client, tracking_records, sample_issues):
        """Move multiple issues to a different tracking record."""
        _, tracking_b_id = tracking_records

        with patch("web.routers.periodicals.bulk.reorganize_periodical_files") as mock_reorg:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.files_moved = True
            mock_reorg.return_value = mock_result

            response = test_client.post(
                "/api/periodicals/bulk/move-to-tracking",
                json={
                    "periodical_ids": sample_issues[:2],
                    "target_tracking_id": tracking_b_id,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["moved_count"] == 2
        assert data["target_tracking_id"] == tracking_b_id
        assert "Magazine B" in data["message"]

    def test_bulk_move_invalid_tracking(self, test_client, sample_issues):
        """Fail when target tracking doesn't exist."""
        response = test_client.post(
            "/api/periodicals/bulk/move-to-tracking",
            json={
                "periodical_ids": sample_issues,
                "target_tracking_id": 99999,
            },
        )

        assert response.status_code == 404

    def test_bulk_move_partial_missing(self, test_client, tracking_records, sample_issues):
        """Report missing periodicals while moving valid ones."""
        _, tracking_b_id = tracking_records

        with patch("web.routers.periodicals.bulk.reorganize_periodical_files") as mock_reorg:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.files_moved = True
            mock_reorg.return_value = mock_result

            response = test_client.post(
                "/api/periodicals/bulk/move-to-tracking",
                json={
                    "periodical_ids": [sample_issues[0], 99999],
                    "target_tracking_id": tracking_b_id,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["moved_count"] == 1
        assert 99999 in data["failed_ids"]

    def test_bulk_move_empty_list_rejected(self, test_client, tracking_records):
        """Reject empty periodical_ids list."""
        _, tracking_b_id = tracking_records

        response = test_client.post(
            "/api/periodicals/bulk/move-to-tracking",
            json={
                "periodical_ids": [],
                "target_tracking_id": tracking_b_id,
            },
        )

        assert response.status_code == 422  # Validation error

    def test_bulk_move_skips_already_in_target(self, test_client, tracking_records, sample_issues):
        """Issues already in the target tracking are skipped."""
        tracking_a_id, _ = tracking_records

        # Move to same tracking they're already in
        response = test_client.post(
            "/api/periodicals/bulk/move-to-tracking",
            json={
                "periodical_ids": sample_issues,
                "target_tracking_id": tracking_a_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["moved_count"] == 0  # All skipped


class TestBulkDelete:
    """Tests for POST /api/periodicals/bulk/delete"""

    def test_bulk_delete_db_only(self, test_client, sample_issues, test_db):
        """Delete issues from database only, keeping files."""
        response = test_client.post(
            "/api/periodicals/bulk/delete",
            json={
                "periodical_ids": sample_issues[:2],
                "delete_files": False,
                "mark_as_bad": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_count"] == 2

        # Verify they're gone from DB
        _, session_factory = test_db
        session = session_factory()
        remaining = session.query(Periodical).count()
        session.close()
        assert remaining == 1  # Only 1 of 3 left

    def test_bulk_delete_with_files(self, test_client, sample_issues, test_db):
        """Delete issues and their files from disk."""
        # Get file paths before deletion
        _, session_factory = test_db
        session = session_factory()
        issues = session.query(Periodical).filter(Periodical.id.in_(sample_issues[:2])).all()
        file_paths = [Path(i.file_path) for i in issues]
        session.close()

        # Verify files exist
        for fp in file_paths:
            assert fp.exists()

        response = test_client.post(
            "/api/periodicals/bulk/delete",
            json={
                "periodical_ids": sample_issues[:2],
                "delete_files": True,
                "mark_as_bad": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 2

        # Verify files are deleted
        for fp in file_paths:
            assert not fp.exists()

    def test_bulk_delete_missing_periodicals(self, test_client):
        """Report missing periodicals without failing entirely."""
        response = test_client.post(
            "/api/periodicals/bulk/delete",
            json={
                "periodical_ids": [99998, 99999],
                "delete_files": False,
                "mark_as_bad": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 0
        assert len(data["failed_ids"]) == 2

    def test_bulk_delete_empty_list_rejected(self, test_client):
        """Reject empty periodical_ids list."""
        response = test_client.post(
            "/api/periodicals/bulk/delete",
            json={
                "periodical_ids": [],
                "delete_files": False,
                "mark_as_bad": False,
            },
        )

        assert response.status_code == 422

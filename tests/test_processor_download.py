"""
Test download workflow end-to-end.
Tests download manager, deduplication, status tracking, and processing integration.
"""

import sys

sys.path.insert(0, ".")

import pytest
import asyncio
from datetime import datetime  # noqa: E402
from unittest.mock import Mock, patch, MagicMock  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from processor.download_manager import DownloadManager  # noqa: E402
from processor.download_monitor import DownloadMonitorTask  # noqa: E402
from models.database import (  # noqa: E402
    Base,
    MagazineTracking,
    DownloadSubmission,
    SearchResult as DBSearchResult,
)
from core.bases import SearchProvider, DownloadClient, SearchResult  # noqa: E402


# Test fixtures
@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory


@pytest.fixture
def mock_search_provider():
    """Create mock search provider"""
    provider = Mock(spec=SearchProvider)
    provider.name = "TestProvider"
    provider.type = "test"

    # Mock search results
    def search_side_effect(query):
        if "Wired" in query:
            return [
                SearchResult(
                    title="Wired Magazine - Dec 2023",
                    url="http://example.com/wired-dec-2023.nzb",
                    provider="TestProvider",
                    publication_date=datetime(2023, 12, 1),
                    raw_metadata={},
                ),
                SearchResult(
                    title="Wired Magazine - Jan 2024",
                    url="http://example.com/wired-jan-2024.nzb",
                    provider="TestProvider",
                    publication_date=datetime(2024, 1, 1),
                    raw_metadata={},
                ),
            ]
        return []

    provider.search = Mock(side_effect=search_side_effect)
    return provider


@pytest.fixture
def mock_download_client():
    """Create mock download client"""
    client = Mock(spec=DownloadClient)
    client.name = "TestClient"
    client.type = "test"

    # Mock submit
    job_counter = {"count": 0}

    def submit_side_effect(nzb_url, title):
        job_counter["count"] += 1
        return f"job_{job_counter['count']}"

    client.submit = Mock(side_effect=submit_side_effect)

    # Mock get_status
    def get_status_side_effect(job_id):
        return {
            "status": "completed",
            "progress": 100,
            "file_path": f"/downloads/{job_id}.pdf",
        }

    client.get_status = Mock(side_effect=get_status_side_effect)

    # Mock get_completed_downloads
    client.get_completed_downloads = Mock(return_value=[])

    return client


class TestDownloadManager:
    """Test DownloadManager functionality"""

    def test_search_periodical_issues(self, test_db, mock_search_provider):
        """Test searching for periodical issues"""
        engine, session_factory = test_db
        session = session_factory()

        manager = DownloadManager([mock_search_provider], Mock(), fuzzy_threshold=80)
        results = manager.search_periodical_issues("Wired", session)

        assert len(results) == 2
        assert results[0]["title"] == "Wired Magazine - Dec 2023"
        assert results[1]["title"] == "Wired Magazine - Jan 2024"
        assert all("url" in r for r in results)
        assert all("provider" in r for r in results)

        session.close()

    def test_fuzzy_group_id_generation(self, test_db, mock_download_client):
        """Test fuzzy group ID generation for deduplication"""
        engine, session_factory = test_db
        manager = DownloadManager([], mock_download_client, fuzzy_threshold=80)

        # Similar titles should generate same group ID
        group1 = manager._get_fuzzy_group_id("Wired Magazine - Dec 2023")
        group2 = manager._get_fuzzy_group_id("Wired Magazine December 2023")
        group3 = manager._get_fuzzy_group_id("National Geographic - Jan 2024")

        assert group1 == group2  # Similar titles
        assert group1 != group3  # Different titles

    def test_duplicate_detection(self, test_db, mock_download_client):
        """Test duplicate detection in submissions"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="wired_magazine",
            title="Wired Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        manager = DownloadManager([], mock_download_client, fuzzy_threshold=80)

        # Submit first issue
        search_result1 = {
            "title": "Wired Magazine - Dec 2023",
            "url": "http://example.com/wired-dec-2023.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }

        submission1 = manager.submit_download(tracking.id, search_result1, session)
        assert submission1 is not None
        assert submission1.status == DownloadSubmission.StatusEnum.PENDING

        # Try to submit similar issue (should be detected as duplicate)
        search_result2 = {
            "title": "Wired Magazine December 2023",  # Slightly different but similar
            "url": "http://example.com/wired-dec-2023-alt.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }

        submission2 = manager.submit_download(tracking.id, search_result2, session)
        # Should return None because it's a duplicate
        assert submission2 is None

        # Verify duplicate was recorded
        duplicates = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.SKIPPED)
            .all()
        )
        assert len(duplicates) == 1

        session.close()

    def test_download_submission(self, test_db, mock_download_client):
        """Test download submission to client"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
            track_all_editions=False,
        )
        session.add(tracking)
        session.commit()

        manager = DownloadManager([], mock_download_client, fuzzy_threshold=80)

        search_result = {
            "title": "Test Magazine Issue 1",
            "url": "http://example.com/test-1.nzb",
            "provider": "test",
            "publication_date": None,
            "raw_metadata": {},
        }

        submission = manager.submit_download(tracking.id, search_result, session)

        assert submission is not None
        assert submission.job_id == "job_1"
        assert submission.status == DownloadSubmission.StatusEnum.PENDING
        assert submission.client_name == "TestClient"

        # Verify submit was called with correct params
        mock_download_client.submit.assert_called_with(
            nzb_url="http://example.com/test-1.nzb",
            title="Test Magazine Issue 1",
        )

        session.close()

    def test_download_all_periodical_issues(
        self, test_db, mock_search_provider, mock_download_client
    ):
        """Test downloading all issues of a periodical"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="wired_magazine",
            title="Wired Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        manager = DownloadManager(
            [mock_search_provider], mock_download_client, fuzzy_threshold=80
        )

        results = manager.download_all_periodical_issues(tracking.id, session)

        # Should have submitted 2 downloads (no duplicates in initial search)
        assert results["submitted"] == 2
        assert results["skipped"] == 0
        assert results["failed"] == 0

        # Verify submissions were created
        submissions = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.tracking_id == tracking.id)
            .all()
        )
        assert len(submissions) == 2

        session.close()

    def test_batch_download_limit_and_english_preference(self, test_db, mock_download_client):
        """Test batch downloading limits to 10 per run and prefers English editions"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create a mock search provider that returns 15 results
        mock_provider = Mock(spec=SearchProvider)
        mock_provider.name = "TestProvider"
        mock_provider.type = "test"

        def search_side_effect(query):
            results = []
            # Use unique first-word prefixes to ensure different fuzzy group IDs
            # English: Alpha, Bravo, Charlie, Delta, Echo
            english_prefixes = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
            for i in range(5):
                results.append(
                    SearchResult(
                        title=f"{english_prefixes[i]} Test Magazine English Edition",
                        url=f"http://example.com/test-{english_prefixes[i].lower()}-en.nzb",
                        provider="TestProvider",
                        publication_date=datetime(2024, i + 1, 1),
                        raw_metadata={},
                    )
                )
            # German: Foxtrot through Oscar (10 total)
            german_prefixes = ["Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar"]
            for i in range(10):
                results.append(
                    SearchResult(
                        title=f"{german_prefixes[i]} Test Magazine German Edition",
                        url=f"http://example.com/test-{german_prefixes[i].lower()}-de.nzb",
                        provider="TestProvider",
                        publication_date=datetime(2023, i + 1, 1),
                        raw_metadata={},
                    )
                )
            return results

        mock_provider.search = Mock(side_effect=search_side_effect)

        manager = DownloadManager(
            [mock_provider], mock_download_client, fuzzy_threshold=80
        )

        # First batch - should get 10 issues (5 English + 5 German due to limit)
        results = manager.download_all_periodical_issues(tracking.id, session)

        assert results["submitted"] == 10
        assert results["skipped"] == 0

        # Verify submissions were created
        submissions = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.tracking_id == tracking.id)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING)
            .order_by(DownloadSubmission.id)  # Order by ID to get insertion order
            .all()
        )
        assert len(submissions) == 10

        # Verify English editions came first - first 5 should be English
        english_count = sum(1 for s in submissions[:5] if "English" in s.result_title)
        assert english_count == 5

        # Second batch - should get remaining 5 German issues
        results2 = manager.download_all_periodical_issues(tracking.id, session)

        assert results2["submitted"] == 5
        # Note: skipped count is 0 because duplicates are filtered before batching, not during submission
        assert results2["skipped"] == 0

        # Verify total submissions
        all_submissions = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.tracking_id == tracking.id)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING)
            .all()
        )
        assert len(all_submissions) == 15

        session.close()

    def test_batch_download_filters_duplicates(self, test_db, mock_download_client):
        """Test that batch downloading filters out already downloaded items"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking record
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
            track_all_editions=True,
        )
        session.add(tracking)
        session.commit()

        # Create existing submissions (simulate already downloaded)
        for i in range(3):
            submission = DownloadSubmission(
                tracking_id=tracking.id,
                job_id=f"job_{i}",
                status=DownloadSubmission.StatusEnum.COMPLETED,
                source_url=f"http://example.com/test-2020-{i + 1:02d}-en.nzb",
                result_title=f"Test Magazine - {['January', 'February', 'March'][i]} 2020 English",
                fuzzy_match_group=f"test-magazine-{['january', 'february', 'march'][i]}",
            )
            session.add(submission)
        session.commit()

        # Create a mock search provider that returns 8 results (3 already downloaded + 5 new)
        mock_provider = Mock(spec=SearchProvider)
        mock_provider.name = "TestProvider"
        mock_provider.type = "test"

        def search_side_effect(query):
            results = []
            months = ["January", "February", "March", "April", "May", "June", "July", "August"]
            # Add 3 already downloaded (should be filtered) - same months as existing
            for i in range(3):
                results.append(
                    SearchResult(
                        title=f"Test Magazine - {months[i]} 2020 English Edition",
                        url=f"http://example.com/test-2020-{i + 1:02d}-en.nzb",
                        provider="TestProvider",
                        publication_date=datetime(2020, i + 1, 1),
                        raw_metadata={},
                    )
                )
            # Add 5 new results - different months
            for i in range(3, 8):
                results.append(
                    SearchResult(
                        title=f"Test Magazine - {months[i]} 2021 English",
                        url=f"http://example.com/test-2021-{i + 1:02d}-en.nzb",
                        provider="TestProvider",
                        publication_date=datetime(2021, i + 1, 1),
                        raw_metadata={},
                    )
                )
            return results

        mock_provider.search = Mock(side_effect=search_side_effect)

        manager = DownloadManager(
            [mock_provider], mock_download_client, fuzzy_threshold=80
        )

        # Should only download the 5 new issues, not the 3 duplicates
        results = manager.download_all_periodical_issues(tracking.id, session)

        assert results["submitted"] == 5
        assert results["skipped"] == 0  # Duplicates are filtered before submission, so not counted as skipped

        # Verify only new submissions were created
        pending_submissions = (
            session.query(DownloadSubmission)
            .filter(DownloadSubmission.tracking_id == tracking.id)
            .filter(DownloadSubmission.status == DownloadSubmission.StatusEnum.PENDING)
            .all()
        )
        assert len(pending_submissions) == 5

        session.close()

    def test_status_update(self, test_db, mock_download_client):
        """Test updating download status"""
        engine, session_factory = test_db
        session = session_factory()

        # Create tracking and submission
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
        )
        session.add(tracking)
        session.flush()

        submission = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_1",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/test.nzb",
            result_title="Test Issue",
            fuzzy_match_group="test-issue",
            client_name="TestClient",
        )
        session.add(submission)
        session.commit()

        manager = DownloadManager([], mock_download_client, fuzzy_threshold=80)

        # Update status
        updated = manager.update_submission_status("job_1", session)

        assert updated is not None
        assert updated.status == DownloadSubmission.StatusEnum.COMPLETED
        assert updated.file_path == "/downloads/job_1.pdf"

        session.close()

    def test_get_pending_downloads(self, test_db):
        """Test getting pending downloads"""
        engine, session_factory = test_db
        session = session_factory()

        # Create test data
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
        )
        session.add(tracking)
        session.flush()

        # Create mix of submissions
        pending = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_1",
            status=DownloadSubmission.StatusEnum.PENDING,
            source_url="http://example.com/1.nzb",
            result_title="Issue 1",
            fuzzy_match_group="issue-1",
            client_name="TestClient",
        )
        downloading = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_2",
            status=DownloadSubmission.StatusEnum.DOWNLOADING,
            source_url="http://example.com/2.nzb",
            result_title="Issue 2",
            fuzzy_match_group="issue-2",
            client_name="TestClient",
        )
        completed = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_3",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/3.nzb",
            result_title="Issue 3",
            fuzzy_match_group="issue-3",
            client_name="TestClient",
            file_path="/downloads/job_3.pdf",
        )

        session.add_all([pending, downloading, completed])
        session.commit()

        manager = DownloadManager([], Mock(), fuzzy_threshold=80)
        active = manager.get_pending_downloads(session)

        assert len(active) == 2
        assert pending in active
        assert downloading in active
        assert completed not in active

        session.close()

    def test_get_completed_downloads(self, test_db):
        """Test getting completed downloads"""
        engine, session_factory = test_db
        session = session_factory()

        # Create test data
        tracking = MagazineTracking(
            olid="test_magazine",
            title="Test Magazine",
        )
        session.add(tracking)
        session.flush()

        completed1 = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_1",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/1.nzb",
            result_title="Issue 1",
            fuzzy_match_group="issue-1",
            client_name="TestClient",
            file_path="/downloads/job_1.pdf",
        )
        completed2 = DownloadSubmission(
            tracking_id=tracking.id,
            job_id="job_2",
            status=DownloadSubmission.StatusEnum.COMPLETED,
            source_url="http://example.com/2.nzb",
            result_title="Issue 2",
            fuzzy_match_group="issue-2",
            client_name="TestClient",
            file_path="/downloads/job_2.pdf",
        )

        session.add_all([completed1, completed2])
        session.commit()

        manager = DownloadManager([], Mock(), fuzzy_threshold=80)
        completed = manager.get_completed_downloads(session)

        assert len(completed) == 2

        session.close()


class TestDownloadMonitorTask:
    """Test DownloadMonitorTask functionality"""

    @pytest.mark.asyncio
    async def test_monitor_task_initialization(self, test_db):
        """Test download monitor task initialization"""
        engine, session_factory = test_db

        manager = Mock()
        file_importer = Mock()

        task = DownloadMonitorTask(
            manager, file_importer, session_factory, downloads_dir="./test_downloads"
        )

        assert task.download_manager == manager
        assert task.file_importer == file_importer
        assert task.session_factory == session_factory
        assert task.downloads_dir.name == "test_downloads"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

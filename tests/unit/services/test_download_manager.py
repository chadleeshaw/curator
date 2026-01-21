"""
Test DownloadManager - Edition variant filtering for auto-download.

Tests cover:
- Edition variant filtering (Kids, Little Kids, Professional, etc.)
- Regional edition filtering (US, UK, DE, etc.)
- Special editions are NOT filtered (Person of the Year, etc.)
- Language filter interaction with edition variants
- Normalization and variant extraction
"""

import sys

sys.path.insert(0, ".")

import pytest
from datetime import datetime, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.download_manager import DownloadManager
from core.interfaces import SearchProvider, SearchResult, DownloadClient
from models.database import Base


# Mock providers and clients


class MockSearchProvider(SearchProvider):
    """Mock search provider for testing"""

    def __init__(self, config, results=None):
        super().__init__(config)
        self.mock_results = results or []

    def search(self, query, category=None):
        """Return pre-configured mock results"""
        return self.mock_results


class MockDownloadClient(DownloadClient):
    """Mock download client for testing"""

    def submit(self, nzb_url, title=None, category=None):
        return "mock_job_123"

    def get_status(self, job_id):
        return {"status": "completed", "progress": 100}

    def get_completed_downloads(self):
        return []

    def delete(self, job_id):
        return True


# Test fixtures


@pytest.fixture
def test_db():
    """Create file-based test database for thread-safe testing"""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        from pathlib import Path

        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def mock_download_client():
    """Create mock download client"""
    return MockDownloadClient({"name": "MockClient", "type": "download_client"})


# Test Classes


class TestEditionVariantFiltering:
    """Test edition variant filtering in search_periodical_issues()"""

    def test_filter_kids_variant_from_base_search(self, test_db, mock_download_client):
        """Searching 'National Geographic' should filter out 'National Geographic Kids'"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns both base and Kids variant
        mock_results = [
            SearchResult(
                title="National Geographic - January 2024",
                url="http://example.com/natgeo-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="National Geographic Kids - January 2024",
                url="http://example.com/natgeo-kids-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        # Create download manager
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Search for base title
        results = manager.search_periodical_issues("National Geographic", session)

        # Should only return base title, not Kids variant
        assert len(results) == 1
        assert "Kids" not in results[0]["title"]
        # Parser cleans titles, so we just check that it doesn't contain "Kids"
        assert "National Geographic" in results[0]["title"]

        session.close()

    def test_filter_little_kids_variant_from_base_search(self, test_db, mock_download_client):
        """Searching 'National Geographic' should filter out 'National Geographic Little Kids'"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns both base and Little Kids variant
        mock_results = [
            SearchResult(
                title="National Geographic - January 2024",
                url="http://example.com/natgeo-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="National Geographic Little Kids - January 2024",
                url="http://example.com/natgeo-little-kids-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("National Geographic", session)

        # Should only return base title, not Little Kids variant
        assert len(results) == 1
        assert "Little Kids" not in results[0]["title"]
        assert "National Geographic" in results[0]["title"]

        session.close()

    def test_keep_kids_variant_when_searching_kids(self, test_db, mock_download_client):
        """Searching 'National Geographic Kids' should return Kids variant, not base"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns both base and Kids variant
        mock_results = [
            SearchResult(
                title="National Geographic - January 2024",
                url="http://example.com/natgeo-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="National Geographic Kids - January 2024",
                url="http://example.com/natgeo-kids-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("National Geographic Kids", session)

        # Should only return Kids variant, not base
        assert len(results) == 1
        assert "Kids" in results[0]["title"]
        assert "National Geographic" in results[0]["title"]

        session.close()

    def test_filter_regional_edition_us_vs_uk(self, test_db, mock_download_client):
        """Searching 'PC Gamer US' should filter out 'PC Gamer UK'"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns both US and UK editions
        mock_results = [
            SearchResult(
                title="PC Gamer US - January 2024",
                url="http://example.com/pcgamer-us-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="PC Gamer UK - January 2024",
                url="http://example.com/pcgamer-uk-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("PC Gamer US", session)

        # Should only return US edition, not UK
        assert len(results) == 1
        # Parser title cases words, so check case-insensitively
        assert "US" in results[0]["title"].upper()
        assert "UK" not in results[0]["title"].upper()

        session.close()

    def test_filter_professional_variant(self, test_db, mock_download_client):
        """Searching 'Business Weekly' should filter out 'Business Weekly Professional'"""
        engine, session_factory = test_db
        session = session_factory()

        mock_results = [
            SearchResult(
                title="Business Weekly - January 2024",
                url="http://example.com/bizweekly-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Business Weekly Professional - January 2024",
                url="http://example.com/bizweekly-pro-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Business Weekly", session)

        # Should only return base edition, not Professional variant
        assert len(results) == 1
        assert "Professional" not in results[0]["title"]

        session.close()

    def test_keep_special_edition_not_filtered(self, test_db, mock_download_client):
        """Special editions like 'Person of the Year' should NOT be filtered"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns both regular and special edition
        mock_results = [
            SearchResult(
                title="Time - January 2024",
                url="http://example.com/time-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Time - Person of the Year 2024",
                url="http://example.com/time-poty-2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Time", session)

        # Should return BOTH - special editions are not variants
        assert len(results) == 2
        titles = [r["title"] for r in results]
        # Parser cleans and title-cases, so check flexibly
        assert any("Time" in t for t in titles)
        assert any("Person" in t and "Year" in t for t in titles)

        session.close()

    def test_format_indicators_not_treated_as_variants(self, test_db, mock_download_client):
        """Digital/Print format indicators should not be treated as edition variants"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns both regular and digital versions
        mock_results = [
            SearchResult(
                title="Wired - January 2024",
                url="http://example.com/wired-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Wired Digital - January 2024",
                url="http://example.com/wired-digital-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Wired", session)

        # Should return BOTH - "Digital" is not a variant, it's format metadata
        assert len(results) == 2
        titles = [r["title"] for r in results]
        # Both should contain "Wired" - the parser may or may not preserve "Digital"
        assert all("Wired" in t for t in titles)

        session.close()

    def test_issue_number_not_detected_as_variant(self, test_db, mock_download_client):
        """Issue numbers like 'No 10' should not detect 'NO' as Norway"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns magazine with issue number
        mock_results = [
            SearchResult(
                title="Tech Magazine No 10 - January 2024",
                url="http://example.com/tech-no10-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Tech Magazine No 11 - February 2024",
                url="http://example.com/tech-no11-feb2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 2, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Tech Magazine", session)

        # Should return BOTH - "No 10" is issue number, not Norway edition
        assert len(results) == 2

        session.close()


class TestLanguageFilterWithEditionVariants:
    """Test interaction between language filter and edition variant filtering"""

    def test_language_filter_applied_before_edition_filter(self, test_db, mock_download_client):
        """Language filter should be applied first, then edition variant filter"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns multiple variants with different languages
        mock_results = [
            SearchResult(
                title="Tech Weekly - German - January 2024",
                url="http://example.com/tech-de-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Tech Weekly Kids - German - January 2024",
                url="http://example.com/tech-kids-de-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Tech Weekly - English - January 2024",
                url="http://example.com/tech-en-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Search with language suffix (manager splits this out)
        results = manager.search_periodical_issues("Tech Weekly - German", session)

        # Should only return German results, and filter out Kids variant
        assert len(results) == 1
        # Parser normalizes language indicators, so check original_title
        assert "German" in results[0]["original_title"]
        assert "Kids" not in results[0]["title"]

        session.close()

    def test_edition_variant_in_different_languages(self, test_db, mock_download_client):
        """Edition variants should work across different languages"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns US/UK editions in German
        mock_results = [
            SearchResult(
                title="Auto Magazine US - German - January 2024",
                url="http://example.com/auto-us-de-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Auto Magazine UK - German - January 2024",
                url="http://example.com/auto-uk-de-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Search for US edition with German language
        results = manager.search_periodical_issues("Auto Magazine US - German", session)

        # Should only return US edition, filter out UK
        assert len(results) == 1
        # Check original_title for language, cleaned title for variant
        assert "US" in results[0]["title"].upper()
        assert "UK" not in results[0]["title"].upper()

        session.close()


class TestNormalizationAndVariantExtraction:
    """Test title normalization and variant extraction in auto-download"""

    def test_dot_normalization_in_titles(self, test_db, mock_download_client):
        """Dots in titles should be normalized to spaces for variant detection"""
        engine, session_factory = test_db
        session = session_factory()

        # Mock provider returns title with dots
        mock_results = [
            SearchResult(
                title="U.S.News - January 2024",
                url="http://example.com/usnews-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="U.S.News Kids - January 2024",
                url="http://example.com/usnews-kids-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("U.S.News", session)

        # Should filter Kids variant even with dots
        assert len(results) == 1
        assert "Kids" not in results[0]["title"]

        session.close()

    def test_multiple_providers_with_edition_filtering(self, test_db, mock_download_client):
        """Edition filtering should work across multiple providers"""
        engine, session_factory = test_db
        session = session_factory()

        # Provider 1 returns base edition
        provider1_results = [
            SearchResult(
                title="Science Today - January 2024",
                url="http://provider1.com/sci-jan2024.nzb",
                provider="Provider1",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider1 = MockSearchProvider({"name": "Provider1", "type": "newsnab"}, provider1_results)

        # Provider 2 returns Kids variant (should be filtered)
        provider2_results = [
            SearchResult(
                title="Science Today Kids - January 2024",
                url="http://provider2.com/sci-kids-jan2024.nzb",
                provider="Provider2",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider2 = MockSearchProvider({"name": "Provider2", "type": "newsnab"}, provider2_results)

        manager = DownloadManager(
            search_providers=[provider1, provider2],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Science Today", session)

        # Should only return result from Provider1, filter Provider2's Kids variant
        assert len(results) == 1
        assert results[0]["provider"] == "Provider1"
        assert "Kids" not in results[0]["title"]

        session.close()


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_search_results(self, test_db, mock_download_client):
        """Empty search results should not cause errors"""
        engine, session_factory = test_db
        session = session_factory()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, [])

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Nonexistent Magazine", session)

        assert len(results) == 0

        session.close()

    def test_no_variant_in_search_or_results(self, test_db, mock_download_client):
        """Results with no variants should all be returned"""
        engine, session_factory = test_db
        session = session_factory()

        mock_results = [
            SearchResult(
                title="Simple Magazine - January 2024",
                url="http://example.com/simple-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            SearchResult(
                title="Simple Magazine - February 2024",
                url="http://example.com/simple-feb2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 2, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        results = manager.search_periodical_issues("Simple Magazine", session)

        # Both should be returned - no variants detected
        assert len(results) == 2

        session.close()

    def test_variant_matching_is_case_insensitive(self, test_db, mock_download_client):
        """Variant matching should be case-insensitive"""
        engine, session_factory = test_db
        session = session_factory()

        mock_results = [
            SearchResult(
                title="Tech Monthly KIDS - January 2024",
                url="http://example.com/tech-kids-jan2024.nzb",
                provider="MockProvider",
                publication_date=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"}, mock_results)

        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Search for base (no variant) should filter Kids regardless of case
        results = manager.search_periodical_issues("Tech Monthly", session)

        assert len(results) == 0  # Kids variant filtered out

        session.close()


class TestBlacklistFiltering:
    """Test blacklisted file extension filtering in submit_download()"""

    def test_filters_video_extension_mp4(self, test_db, mock_download_client):
        """Test that .mp4 extension in title is filtered out"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import PeriodicalTracking

        # Create tracking record
        tracking = PeriodicalTracking(
            title="Test Magazine",
            olid="test_magazine",
            language="en",
        )
        session.add(tracking)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
        )

        # Try to submit download with .mp4 in title
        search_result = {
            "title": "Test Magazine Jan 2024.mp4",
            "url": "http://example.com/test.nzb",
            "provider": "MockProvider",
        }

        result = manager.submit_download(tracking.id, search_result, session)

        # Should return None (rejected)
        assert result is None

        # Check that it was recorded as SKIPPED
        from models.database import DownloadSubmission

        submissions = session.query(DownloadSubmission).all()
        assert len(submissions) == 1
        assert submissions[0].status == DownloadSubmission.StatusEnum.SKIPPED

        session.close()

    def test_filters_video_extension_avi(self, test_db, mock_download_client):
        """Test that .avi extension in title is filtered out"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import PeriodicalTracking

        tracking = PeriodicalTracking(
            title="Test Magazine",
            olid="test_magazine",
            language="en",
        )
        session.add(tracking)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
        )

        search_result = {
            "title": "Test.Magazine.2024.avi",
            "url": "http://example.com/test.nzb",
            "provider": "MockProvider",
        }

        result = manager.submit_download(tracking.id, search_result, session)

        assert result is None

        session.close()

    def test_allows_legitimate_pdf_with_mp_in_name(self, test_db, mock_download_client):
        """Test that magazine names containing 'mp' are NOT filtered (only .mp4 extension)"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import PeriodicalTracking

        # Magazine with "MP" in name (like "Computer Music" or "Example MP")
        tracking = PeriodicalTracking(
            title="Example MP Magazine",
            olid="example_mp_magazine",
            language="en",
        )
        session.add(tracking)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
        )

        # Title contains "MP" but NOT the extension ".mp4"
        search_result = {
            "title": "Example MP Magazine - Jan 2024",
            "url": "http://example.com/test.nzb",
            "provider": "MockProvider",
        }

        result = manager.submit_download(tracking.id, search_result, session)

        # Should be accepted (not None)
        assert result is not None

        session.close()

    def test_filters_mkv_extension(self, test_db, mock_download_client):
        """Test that .mkv extension in title is filtered out"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import PeriodicalTracking

        tracking = PeriodicalTracking(
            title="Test Magazine",
            olid="test_magazine",
            language="en",
        )
        session.add(tracking)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
        )

        search_result = {
            "title": "Test Magazine 2024.mkv",
            "url": "http://example.com/test.nzb",
            "provider": "MockProvider",
        }

        result = manager.submit_download(tracking.id, search_result, session)

        assert result is None

        session.close()

    def test_case_insensitive_extension_filtering(self, test_db, mock_download_client):
        """Test that extension filtering is case-insensitive"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import PeriodicalTracking

        tracking = PeriodicalTracking(
            title="Test Magazine",
            olid="test_magazine",
            language="en",
        )
        session.add(tracking)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
        )

        # Test uppercase extension
        search_result = {
            "title": "Test Magazine 2024.MP4",
            "url": "http://example.com/test.nzb",
            "provider": "MockProvider",
        }

        result = manager.submit_download(tracking.id, search_result, session)

        assert result is None  # Should still be filtered

        session.close()

    def test_allows_normal_pdf_download(self, test_db, mock_download_client):
        """Test that normal PDF downloads are NOT filtered"""
        engine, session_factory = test_db
        session = session_factory()

        from models.database import PeriodicalTracking

        tracking = PeriodicalTracking(
            title="Test Magazine",
            olid="test_magazine",
            language="en",
        )
        session.add(tracking)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
        )

        # Normal magazine title without blacklisted extensions
        search_result = {
            "title": "Test Magazine - January 2024",
            "url": "http://example.com/test.nzb",
            "provider": "MockProvider",
        }

        result = manager.submit_download(tracking.id, search_result, session)

        # Should be accepted
        assert result is not None

        from models.database import DownloadSubmission

        submissions = session.query(DownloadSubmission).all()
        assert len(submissions) == 1
        assert submissions[0].status == DownloadSubmission.StatusEnum.PENDING

        session.close()


class TestDuplicateDetectionConsistency:
    """
    Test consistency between duplicate detection methods.

    Tests the potential issue where:
    - Search UI uses fuzzy + date range matching (TitleMatcher.matches_library_item_with_date_range)
    - Download manager uses exact title matching (Periodical.title == tracking_title)

    This could cause:
    1. Items showing as "Available" when they're already downloaded
    2. Downloading duplicates with slightly different titles
    """

    def test_fuzzy_title_duplicate_detection(self, test_db, mock_download_client):
        """
        Test that similar titles with regional indicators are detected as duplicates.

        Library: "PC Gamer US"
        Search: "PC Gamer United States" or "PC Gamer (US)"

        Expected: Should be detected as duplicate (same publication, different formatting)
        Actual: May NOT be detected because parser produces different base_titles
        """
        engine, session_factory = test_db
        session = session_factory()

        from models.database import Periodical, PeriodicalTracking

        # Create tracking
        tracking = PeriodicalTracking(
            title="PC Gamer US",
            olid="pc_gamer_us",
            language="English",
            country="US",
            category="Magazine",
        )
        session.add(tracking)
        session.commit()

        # Create library item with "US" suffix
        library_item = Periodical(
            tracking_id=tracking.id,
            title="Pc Gamer Us",  # This is what parser produces from "PC Gamer US"
            language="English",
            category="Magazine",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
            file_path="/library/PCGamerUS/2024/PCGamerUS - 2024-01.pdf",
        )
        session.add(library_item)
        session.commit()

        # Mock provider returns similar but not identical title
        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Try to download search result with "(US)" format
        search_result = {
            "title": "PC Gamer (US) - January 2024",
            "url": "http://example.com/pc-gamer-us-jan2024.nzb",
            "provider": "MockProvider",
        }

        # Check if duplicate is detected
        is_dup, existing = manager.check_duplicate_submission(tracking.id, search_result["title"], session)

        # EXPECTED: Should be detected as duplicate (same publication, different formatting)
        # ACTUAL: Will NOT be detected because:
        #   - Library has base_title="Pc Gamer Us"
        #   - Search parses to base_title="Pc Gamer (Us)"
        #   - Exact string match fails: "Pc Gamer Us" != "Pc Gamer (Us)"
        if not is_dup:
            print(
                "\nDETECTED ISSUE: Regional format variations not caught by duplicate detection!"
                "\n  Library title: 'Pc Gamer Us'"
                "\n  Search title: 'PC Gamer (US)' → parses to 'Pc Gamer (Us)'"
                "\n  Result: NOT detected as duplicate (exact match fails)"
            )

        # This assertion may fail, demonstrating the bug
        assert is_dup, (
            "Expected duplicate detection for regional format variations. "
            "Library has 'Pc Gamer Us', search has 'PC Gamer (US)' which parses to 'Pc Gamer (Us)' - "
            "these should match but exact string comparison fails"
        )

        session.close()

    def test_date_range_duplicate_detection(self, test_db, mock_download_client):
        """
        Test that issues within date tolerance are detected as duplicates.

        Library: "Tech Weekly" published on 2024-01-01
        Search: "Tech Weekly" published on 2024-01-05 (5 days later)

        Expected: Should be detected as duplicate (within 7-day tolerance)
        """
        engine, session_factory = test_db
        session = session_factory()

        from models.database import Periodical, PeriodicalTracking

        # Create tracking
        tracking = PeriodicalTracking(
            title="Tech Weekly",
            olid="tech_weekly",
            language="English",
            country="US",
            category="Magazine",
        )
        session.add(tracking)
        session.commit()

        # Create library item published on Jan 1
        library_item = Periodical(
            tracking_id=tracking.id,
            title="Tech Weekly",
            language="English",
            category="Magazine",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
            file_path="/library/TechWeekly/2024/TechWeekly - 2024-01-01.pdf",
        )
        session.add(library_item)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Try to download same issue but dated 5 days later (e.g., UK vs US release)
        search_result = {
            "title": "Tech Weekly - January 05 2024",
            "url": "http://example.com/tech-weekly-jan05.nzb",
            "provider": "MockProvider",
        }

        # Check if duplicate is detected
        is_dup, existing = manager.check_duplicate_submission(tracking.id, search_result["title"], session)

        # EXPECTED: Should be detected as duplicate because dates are within 7-day tolerance
        # ACTUAL: May not be detected because check_duplicate_submission doesn't check dates
        # NOTE: This might be intentional if we want to allow different dated releases
        # But it should be CONSISTENT with what the search UI shows
        if not is_dup:
            print(
                "INFO: Date-based duplicate detection not implemented in download_manager. "
                "This might be intentional, but should match search UI behavior."
            )

        session.close()

    def test_exact_match_works_correctly(self, test_db, mock_download_client):
        """
        Test that exact title matches are correctly detected as duplicates.

        This should always work - baseline test.
        """
        engine, session_factory = test_db
        session = session_factory()

        from models.database import Periodical, PeriodicalTracking

        # Create tracking
        tracking = PeriodicalTracking(
            title="Science Monthly",
            olid="science_monthly",
            language="English",
            country="US",
            category="Magazine",
        )
        session.add(tracking)
        session.commit()

        # Create library item
        library_item = Periodical(
            tracking_id=tracking.id,
            title="Science Monthly",
            language="English",
            category="Magazine",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
            file_path="/library/ScienceMonthly/2024/ScienceMonthly - 2024-01.pdf",
        )
        session.add(library_item)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Try to download exact same title
        search_result = {
            "title": "Science Monthly - January 2024",
            "url": "http://example.com/science-monthly-jan2024.nzb",
            "provider": "MockProvider",
        }

        # Check if duplicate is detected
        is_dup, existing = manager.check_duplicate_submission(tracking.id, search_result["title"], session)

        # EXPECTED: Should be detected as duplicate (exact title match)
        assert is_dup, "Expected duplicate detection for exact title match"

        session.close()

    def test_different_language_not_duplicate(self, test_db, mock_download_client):
        """
        Test that same title in different language is NOT detected as duplicate.

        Library: "Auto Today" (English)
        Search: "Auto Today" (German)

        Expected: Should NOT be duplicate (different languages)
        """
        engine, session_factory = test_db
        session = session_factory()

        from models.database import Periodical, PeriodicalTracking

        # Create tracking
        tracking = PeriodicalTracking(
            title="Auto Today",
            olid="auto_today",
            language="English",
            country="US",
            category="Magazine",
        )
        session.add(tracking)
        session.commit()

        # Create library item in English
        library_item = Periodical(
            tracking_id=tracking.id,
            title="Auto Today",
            language="English",
            category="Magazine",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
            file_path="/library/AutoToday/2024/AutoToday - 2024-01.pdf",
        )
        session.add(library_item)
        session.commit()

        provider = MockSearchProvider({"name": "MockProvider", "type": "newsnab"})
        manager = DownloadManager(
            search_providers=[provider],
            download_client=mock_download_client,
            fuzzy_threshold=80,
        )

        # Try to download German version
        search_result = {
            "title": "Auto Today - German - January 2024",
            "url": "http://example.com/auto-today-de-jan2024.nzb",
            "provider": "MockProvider",
        }

        # Check if duplicate is detected
        is_dup, existing = manager.check_duplicate_submission(tracking.id, search_result["title"], session)

        # EXPECTED: Should NOT be duplicate (different language)
        assert not is_dup, "Expected NO duplicate detection for different language"

        session.close()

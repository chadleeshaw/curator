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

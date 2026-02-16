"""
Tests for web/routers/search/enrichment.py

Validates that the backend enrichment adds correct parsed_title metadata
to search results so the frontend doesn't need to duplicate parsing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from web.routers.search.enrichment import (
    enrich_results_with_parsed_metadata,
    _detect_collection,
    _extract_season,
    _parse_single_result,
)


class TestDetectCollection:
    """Test collection/pack/bundle detection."""

    def test_magazine_collection(self):
        assert _detect_collection("Best.Cars.Magazine.Collection") is True

    def test_magazine_pack(self):
        assert _detect_collection("Playboy Magazine Pack") is True

    def test_magazine_bundle(self):
        assert _detect_collection("Wired Magazine Bundle") is True

    def test_complete_collection(self):
        assert _detect_collection("Complete Collection 1990-2020") is True

    def test_full_archive(self):
        assert _detect_collection("Full Archive of Magazines") is True

    def test_set_number(self):
        assert _detect_collection("Magazine Set #5") is True

    def test_collection_pdf(self):
        assert _detect_collection("Collection of 50 PDF Magazines") is True

    def test_regular_issue_not_collection(self):
        assert _detect_collection("Wired.Magazine.January.2024.True.PDF") is False

    def test_regular_title_not_collection(self):
        assert _detect_collection("National Geographic 2024-01") is False


class TestExtractSeason:
    """Test season extraction from titles."""

    def test_spring(self):
        assert _extract_season("Magazine Spring 2024") == "Spring"

    def test_summer(self):
        assert _extract_season("Magazine.Summer.2024") == "Summer"

    def test_fall(self):
        assert _extract_season("Magazine Fall Issue") == "Fall"

    def test_autumn_normalised_to_fall(self):
        assert _extract_season("Magazine Autumn 2024") == "Fall"

    def test_winter(self):
        assert _extract_season("Winter_2024_Magazine") == "Winter"

    def test_no_season(self):
        assert _extract_season("Magazine January 2024") is None


class TestParseSingleResult:
    """Test individual result parsing."""

    def test_nzb_with_date(self):
        result = {
            "title": "Wired.Magazine.January.2024.True.PDF",
            "publication_date": "2024-01-15T00:00:00",
        }
        parsed = _parse_single_result(result)
        assert parsed["year"] == 2024
        assert parsed["month"] == 1
        assert parsed["is_collection"] is False

    def test_collection_title(self):
        result = {
            "title": "Best.Cars.Magazine.Collection",
            "publication_date": None,
        }
        parsed = _parse_single_result(result)
        assert parsed["is_collection"] is True
        assert parsed["year"] == 0
        assert parsed["month"] == 0

    def test_set_with_number(self):
        result = {
            "title": "Magazine Collection Set 5",
            "publication_date": None,
        }
        parsed = _parse_single_result(result)
        assert parsed["is_collection"] is True
        assert parsed["issue"] == 5

    def test_volume_issue(self):
        result = {
            "title": "PC.Gamer.US.No.405.February.2024.pdf",
            "publication_date": "2024-02-01T00:00:00",
        }
        parsed = _parse_single_result(result)
        assert parsed["year"] == 2024
        assert parsed["month"] == 2
        assert parsed["issue"] == 405

    def test_seasonal_title(self):
        result = {
            "title": "2600.Magazine.Winter.2024",
            "publication_date": None,
        }
        parsed = _parse_single_result(result)
        # NZB parser can't extract year ("2600" is the mag name, not a year)
        # but season is detected by our fallback
        assert parsed["season"] == "Winter"

    def test_seasonal_title_with_clear_year(self):
        result = {
            "title": "Outdoor.Magazine.Spring.2024",
            "publication_date": None,
        }
        parsed = _parse_single_result(result)
        assert parsed["season"] == "Spring"

    def test_pubdate_fallback_for_month(self):
        """When NZB parsing can't extract month, fall back to publication_date."""
        result = {
            "title": "Some.Obscure.Magazine",
            "publication_date": "2024-06-15T00:00:00",
        }
        parsed = _parse_single_result(result)
        # NZB parser doesn't extract month, so publication_date provides it
        assert parsed["year"] == 2024
        assert parsed["month"] == 6
        assert parsed["is_collection"] is False

    def test_collection_ignores_pubdate_fallback(self):
        """Collections must NOT inherit year/month from publication_date.

        They should always land under year=0 so the UI groups them under
        '📦 Collections' instead of a random upload-date year.
        """
        result = {
            "title": "Best.Cars.Magazine.Collection",
            "publication_date": "2021-08-15T00:00:00",
        }
        parsed = _parse_single_result(result)
        assert parsed["is_collection"] is True
        assert parsed["year"] == 0
        assert parsed["month"] == 0

    def test_size_from_raw_metadata(self):
        """Size and files count should be extracted from raw_metadata."""
        result = {
            "title": "Best.Cars.Magazine.Collection",
            "publication_date": None,
            "raw_metadata": {"size": 524288000, "files": 12},
        }
        parsed = _parse_single_result(result)
        assert parsed["size"] == 524288000
        assert parsed["files"] == 12

    def test_size_defaults_to_zero(self):
        """When no size info is available, size and files default to 0."""
        result = {
            "title": "Wired.Magazine.January.2024.True.PDF",
            "publication_date": None,
        }
        parsed = _parse_single_result(result)
        assert parsed["size"] == 0
        assert parsed["files"] == 0

    def test_volume_extraction(self):
        result = {
            "title": "TIME.V202.N25.2023.pdf",
            "publication_date": None,
        }
        parsed = _parse_single_result(result)
        assert parsed["volume"] == 202
        assert parsed["issue"] == 25
        assert parsed["year"] == 2023


class TestEnrichResults:
    """Test the full enrichment function."""

    def test_adds_parsed_title_to_all_results(self):
        results = [
            {"title": "Wired.January.2024", "publication_date": None},
            {"title": "Best.Cars.Magazine.Collection", "publication_date": None},
            {"title": "National.Geographic.2024.01", "publication_date": None},
        ]
        enrich_results_with_parsed_metadata(results)

        for r in results:
            assert "parsed_title" in r
            assert isinstance(r["parsed_title"], dict)
            assert "year" in r["parsed_title"]
            assert "month" in r["parsed_title"]
            assert "issue" in r["parsed_title"]
            assert "volume" in r["parsed_title"]
            assert "season" in r["parsed_title"]
            assert "is_collection" in r["parsed_title"]
            assert "size" in r["parsed_title"]
            assert "files" in r["parsed_title"]

    def test_collection_detected(self):
        results = [
            {"title": "Best.Cars.Magazine.Collection", "publication_date": None},
        ]
        enrich_results_with_parsed_metadata(results)
        assert results[0]["parsed_title"]["is_collection"] is True

    def test_regular_issue_not_collection(self):
        results = [
            {"title": "Wired.Magazine.January.2024.True.PDF", "publication_date": "2024-01-01T00:00:00"},
        ]
        enrich_results_with_parsed_metadata(results)
        assert results[0]["parsed_title"]["is_collection"] is False
        assert results[0]["parsed_title"]["year"] == 2024
        assert results[0]["parsed_title"]["month"] == 1

    def test_empty_list(self):
        results = []
        enrich_results_with_parsed_metadata(results)
        assert results == []

    def test_modifies_in_place(self):
        results = [{"title": "Test 2024", "publication_date": None}]
        enrich_results_with_parsed_metadata(results)
        # Should modify the list in place, not return a new one
        assert "parsed_title" in results[0]

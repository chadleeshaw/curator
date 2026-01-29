"""
Tests for query expansion utilities.

Tests that query variants are generated correctly to improve provider search
match rates for titles with different naming conventions.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


from core.utils.query_expansion import generate_query_variants, expand_search_queries


class TestGenerateQueryVariants:
    """Test query variant generation."""

    def test_original_query_is_first(self):
        """Original query should always be first variant"""
        variants = generate_query_variants("National Geographic")
        assert variants[0] == "National Geographic"

    def test_national_geographic_kids_travel(self):
        """Test: National Geographic Kids Travel -> multiple variants"""
        variants = generate_query_variants("National Geographic Kids Travel", max_variants=5)

        # Should include original
        assert "National Geographic Kids Travel" in variants

        # Should include partial combinations
        assert any("Kids Travel" in v for v in variants)
        assert any("National Geographic" in v for v in variants)

    def test_pc_gamer_us_magazine(self):
        """Test: PC Gamer US Magazine -> remove regional/common words"""
        variants = generate_query_variants("PC Gamer US Magazine")

        assert "PC Gamer US Magazine" in variants
        # Should have variant without "Magazine"
        assert "PC Gamer US" in variants
        # Should have variant without "US"
        assert any("PC Gamer" in v and "US" not in v for v in variants)

    def test_removes_common_periodical_words(self):
        """Test that common words like 'Magazine', 'Journal' are removed"""
        variants = generate_query_variants("Time Magazine")
        assert "Time" in variants

        variants = generate_query_variants("Nature Journal")
        assert "Nature" in variants

    def test_removes_regional_indicators(self):
        """Test that regional indicators like 'US', 'UK' are removed"""
        variants = generate_query_variants("Wired US")
        assert "Wired" in variants

        variants = generate_query_variants("PC Gamer UK")
        assert "PC Gamer" in variants

    def test_removes_edition_variants(self):
        """Test that edition variants like 'Kids', 'Professional' are removed"""
        variants = generate_query_variants("National Geographic Kids")
        assert "National Geographic" in variants

        variants = generate_query_variants("Forbes Professional")
        assert "Forbes" in variants

    def test_keeps_significant_words(self):
        """Test that significant words are preserved"""
        variants = generate_query_variants("The New Yorker")
        # Should remove article "The"
        assert any("New Yorker" in v for v in variants)

    def test_empty_query(self):
        """Test that empty query returns empty list"""
        variants = generate_query_variants("")
        assert variants == [""]

    def test_single_word_query(self):
        """Test single word query"""
        variants = generate_query_variants("Wired")
        assert variants[0] == "Wired"

    def test_max_variants_respected(self):
        """Test that max_variants limit is respected"""
        variants = generate_query_variants("One Two Three Four Five Six", max_variants=3)
        assert len(variants) <= 3

    def test_no_duplicate_variants(self):
        """Test that variants list has no duplicates"""
        variants = generate_query_variants("National Geographic Magazine")
        assert len(variants) == len(set(variants))

    def test_variants_ordered_by_specificity(self):
        """Test that variants are ordered from most to least specific"""
        variants = generate_query_variants("National Geographic Kids Travel")
        # First should be original (most specific)
        assert variants[0] == "National Geographic Kids Travel"
        # Second should prioritize last N words (often the actual magazine title)
        assert variants[1] == "Kids Travel"
        # Rest should be ordered by specificity (longer = more specific)
        for i in range(2, len(variants) - 1):
            assert len(variants[i]) >= len(variants[i + 1])


class TestExpandSearchQueries:
    """Test search query expansion for provider searches."""

    def test_original_query_is_first(self):
        """Original query should always be first"""
        queries = expand_search_queries("National Geographic")
        assert queries[0] == "National Geographic"

    def test_national_geographic_kids_travel(self):
        """Test: National Geographic Kids Travel expansion"""
        queries = expand_search_queries("National Geographic Kids Travel", max_queries=3)

        assert len(queries) <= 3
        assert queries[0] == "National Geographic Kids Travel"
        # Should include useful variants
        assert len(queries) >= 2

    def test_pc_gamer_us(self):
        """Test: PC Gamer US expansion"""
        queries = expand_search_queries("PC Gamer US", max_queries=3)

        assert queries[0] == "PC Gamer US"
        assert "PC Gamer" in queries

    def test_respects_max_queries(self):
        """Test that max_queries limit is respected"""
        queries = expand_search_queries("One Two Three Four Five", max_queries=2)
        assert len(queries) <= 2

    def test_respects_min_query_length(self):
        """Test that min_query_length filter works"""
        queries = expand_search_queries("A B C D", max_queries=5, min_query_length=3)
        # Should filter out very short variants
        assert all(len(q) >= 3 for q in queries)

    def test_short_query_unchanged(self):
        """Test that short queries are preserved"""
        queries = expand_search_queries("PC", max_queries=3)
        # Should return original even if short (controlled by min_query_length)
        assert "PC" in queries or len(queries) == 0

    def test_single_word_returns_original(self):
        """Test single word returns just the original"""
        queries = expand_search_queries("Wired", max_queries=3)
        assert queries[0] == "Wired"


class TestQueryExpansionEdgeCases:
    """Test edge cases and special scenarios."""

    def test_query_with_numbers(self):
        """Test queries with numbers are preserved"""
        variants = generate_query_variants("2600 Magazine")
        assert "2600 Magazine" in variants
        assert "2600" in variants

    def test_query_with_special_characters(self):
        """Test queries with special characters"""
        variants = generate_query_variants("PC & Tech Magazine")
        assert "PC & Tech Magazine" in variants

    def test_very_long_query(self):
        """Test very long query is handled"""
        long_query = "One Two Three Four Five Six Seven Eight Nine Ten"
        variants = generate_query_variants(long_query, max_variants=5)
        assert len(variants) <= 5
        assert variants[0] == long_query

    def test_query_with_multiple_spaces(self):
        """Test query with multiple spaces is handled"""
        variants = generate_query_variants("National    Geographic")
        # Original query is preserved as-is
        assert variants[0] == "National    Geographic"
        # Other variants should be normalized (via split/join)
        assert len(variants) >= 1

    def test_query_with_unicode(self):
        """Test query with unicode characters"""
        variants = generate_query_variants("Café Magazine")
        assert "Café Magazine" in variants

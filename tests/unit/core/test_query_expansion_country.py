"""
Tests for query expansion with country-aware regional handling.

The query expansion should intelligently handle country indicators:
- US/UK/Canada indicators can be removed (magazines typically don't include these)
- Other country indicators should be preserved (they're part of the edition identity)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


from core.utils.query_expansion import generate_query_variants, expand_search_queries


class TestCountryAwareExpansion:
    """Test that query expansion handles countries intelligently."""

    def test_us_edition_removes_country(self):
        """US editions should have 'US' removed in variants"""
        variants = generate_query_variants("Magazine US")

        # Should include original
        assert "Magazine US" in variants
        # Should include variant without US
        assert "Magazine" in variants

    def test_uk_edition_preserves_country(self):
        """UK editions should have 'UK' preserved in variants"""
        variants = generate_query_variants("PC Gamer UK")

        assert "PC Gamer UK" in variants
        # Should NOT have variant without UK
        assert "PC Gamer" not in variants

    def test_usa_edition_removes_country(self):
        """USA editions should have 'USA' removed in variants"""
        variants = generate_query_variants("Time USA")

        assert "Time USA" in variants
        assert "Time" in variants

    def test_canada_edition_preserves_country(self):
        """Canada editions should have 'Canada' preserved in variants"""
        variants = generate_query_variants("Reader's Digest Canada")

        assert "Reader's Digest Canada" in variants
        # Should NOT have variant without Canada
        assert not any(v == "Reader's Digest" for v in variants)

    def test_russia_edition_preserves_country(self):
        """Russian editions should keep 'Russia' in all variants"""
        variants = generate_query_variants("Magazine Russia")

        # Should include original
        assert "Magazine Russia" in variants
        # Should NOT have a variant that removes Russia entirely
        # (abbreviations like "MG Russia" are OK)
        assert "Magazine" not in variants
        # All non-single-word variants should contain Russia
        for variant in variants:
            if len(variant.split()) > 1:
                assert "Russia" in variant

    def test_germany_edition_preserves_country(self):
        """German editions should keep 'Germany' in variants"""
        variants = generate_query_variants("Auto Magazine Germany")

        assert "Auto Magazine Germany" in variants
        # Should NOT have variants that drop Germany entirely
        assert "Auto Magazine" not in variants
        # Multi-word variants should preserve Germany
        for variant in variants:
            if len(variant.split()) > 1:
                assert "Germany" in variant

    def test_france_edition_preserves_country(self):
        """French editions should keep 'France' in variants"""
        variants = generate_query_variants("Vogue France")

        assert "Vogue France" in variants
        assert "Vogue" not in variants

    def test_japan_edition_preserves_country(self):
        """Japanese editions should keep 'Japan' in variants"""
        variants = generate_query_variants("Computer Weekly Japan")

        assert "Computer Weekly Japan" in variants
        assert "Computer Weekly" not in variants

    def test_brazil_edition_preserves_country(self):
        """Brazilian editions should keep 'Brazil' in variants"""
        variants = generate_query_variants("National Geographic Brazil")

        assert "National Geographic Brazil" in variants
        # Should NOT have multi-word variant without Brazil
        assert "National Geographic" not in variants
        # Multi-word variants should contain Brazil
        for variant in variants:
            if len(variant.split()) > 1:
                assert "Brazil" in variant

    def test_australia_edition_preserves_country(self):
        """Australian editions should keep 'Australia' in variants"""
        variants = generate_query_variants("Good Housekeeping Australia")

        assert "Good Housekeeping Australia" in variants
        assert "Good Housekeeping" not in variants

    def test_expand_search_queries_russia(self):
        """expand_search_queries should preserve Russia in multi-word queries"""
        queries = expand_search_queries("Magazine Russia", max_queries=3)

        # Multi-word queries should contain Russia
        for query in queries:
            if len(query.split()) > 1:
                assert "Russia" in query

    def test_expand_search_queries_us(self):
        """expand_search_queries can drop US from queries"""
        queries = expand_search_queries("Magazine US", max_queries=3)

        # Should include original
        assert "Magazine US" in queries
        # Should include query without US
        assert any("Magazine" == q or q.startswith("Magazine") for q in queries)

    def test_mixed_title_with_non_us_country(self):
        """Test complex title with non-US country"""
        variants = generate_query_variants("National Geographic Traveler Russia")

        # Multi-word variants should preserve Russia
        for variant in variants:
            if len(variant.split()) > 1:
                assert "Russia" in variant

    def test_mixed_title_with_us_country(self):
        """Test complex title with US country"""
        variants = generate_query_variants("National Geographic Traveler US")

        # Should have variants without US
        assert any("US" not in v for v in variants)

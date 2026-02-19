"""
Test word boundary matching in FeedMatchService.

This test suite verifies that feed matching uses word boundaries to avoid
false positive matches like "Maxim" matching "Maximo Garcia".
"""

import pytest

from services.cache.feed_match import FeedMatchService


class TestWordBoundaryMatching:
    """Test that feed matching uses word boundaries to prevent substring false positives."""

    def test_exact_word_match(self):
        """'Maxim' should match 'Maxim Magazine'"""
        service = FeedMatchService()
        assert service._title_matches_any_term("maxim magazine", ["maxim"])

    def test_no_substring_match(self):
        """'Maxim' should NOT match 'Maximo Garcia' (the bug we're fixing)"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("maximo garcia part 1", ["maxim"])

    def test_word_at_start(self):
        """Should match word at start of title"""
        service = FeedMatchService()
        assert service._title_matches_any_term("maxim for men", ["maxim"])

    def test_word_at_end(self):
        """Should match word at end of title"""
        service = FeedMatchService()
        assert service._title_matches_any_term("us edition maxim", ["maxim"])

    def test_word_in_middle(self):
        """Should match word in middle of title"""
        service = FeedMatchService()
        assert service._title_matches_any_term("the maxim magazine collection", ["maxim"])

    def test_partial_word_no_match(self):
        """'Time' should NOT match 'Times'"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("the times magazine", ["time"])

    def test_maximum_does_not_match_maxim(self):
        """'Maxim' should NOT match 'Maximum PC'"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("maximum pc the nearly complete collection", ["maxim"])

    def test_normalized_delimiters(self):
        """Delimiters (dots, underscores, hyphens) are normalized to spaces"""
        service = FeedMatchService()
        # Title "Maxim_Magazine.2025" normalized to "maxim magazine 2025"
        assert service._title_matches_any_term("maxim magazine 2025", ["maxim"])

    def test_multiple_terms_any_match(self):
        """Should match if ANY search term matches"""
        service = FeedMatchService()
        assert service._title_matches_any_term("popular mechanics 2025", ["popular", "mechanics"])
        assert service._title_matches_any_term("popular science 2025", ["popular", "mechanics"])

    def test_case_insensitive_matching(self):
        """
        Matching should be case insensitive (search terms are lowercased).
        Note: In practice, titles are lowercased by the caller before passing to this method.
        """
        service = FeedMatchService()
        # Search terms can be uppercase (they get lowercased internally)
        assert service._title_matches_any_term("maxim magazine", ["MAXIM"])
        # Titles should be lowercase when passed to this method
        assert service._title_matches_any_term("maxim magazine", ["maxim"])

    def test_wired_does_not_match_rewired(self):
        """'Wired' should not match 'Rewired Magazine'"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("rewired magazine", ["wired"])

    def test_pc_does_not_match_vpc(self):
        """'PC' should not match 'VPC Computing'"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("vpc computing monthly", ["pc"])

    def test_empty_title(self):
        """Empty title should not match anything"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("", ["maxim"])

    def test_empty_search_terms(self):
        """Empty search terms should not match"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("maxim magazine", [])


class TestRealWorldExamples:
    """Test with real-world examples that caused issues."""

    def test_maxim_vs_maximo(self):
        """Original bug: Maxim Magazine should not match 'Maximo Garcia Part 1 Mega Pack'"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("maximo garcia part 1 mega pack", ["maxim magazine", "maxim"])

    def test_nuts_vs_donuts(self):
        """'Nuts UK' should not match 'Donuts Monthly'"""
        service = FeedMatchService()
        assert not service._title_matches_any_term("donuts monthly", ["nuts"])

    def test_wired_exact_match(self):
        """'Wired' should match 'Wired Magazine UK'"""
        service = FeedMatchService()
        assert service._title_matches_any_term("wired magazine uk", ["wired"])

    def test_scientific_american_abbreviation(self):
        """'SciAm' should match as whole word"""
        service = FeedMatchService()
        assert service._title_matches_any_term("sciam march 2025", ["sciam"])
        assert not service._title_matches_any_term("sciamedia publishing", ["sciam"])

    def test_special_chars_in_search_term(self):
        """
        Should handle special characters in search terms.
        For realistic matching, special chars in titles need to be preserved.
        This test just verifies the pattern doesn't crash.
        """
        service = FeedMatchService()
        # Test that special chars don't break the matching
        # If a title actually has C++ in it (after normalization), it would work
        assert not service._title_matches_any_term("cpp magazine", ["c++"])

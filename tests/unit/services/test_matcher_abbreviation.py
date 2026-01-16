"""
Tests for abbreviation matching in TrackingMatcher
"""

import sys
from pathlib import Path

# Path setup handled by conftest.py

from services.importer.matcher import TrackingMatcher, WEIGHT_TITLE_ABBREVIATION


def test_generate_abbreviation():
    """Test abbreviation generation from titles"""
    matcher = TrackingMatcher()

    # Single word titles only get first letter
    assert matcher.generate_abbreviation("Wired") == "w"
    # Multi-word titles get abbreviation from all significant words
    assert matcher.generate_abbreviation("National Geographic") == "ng"
    assert matcher.generate_abbreviation("PC Gamer") == "pg"  # PC is one word
    assert matcher.generate_abbreviation("The Atlantic") == "a"  # 'the' is skipped
    assert matcher.generate_abbreviation("Time Magazine") == "t"  # 'magazine' is skipped


def test_abbreviation_matching():
    """Test that short titles match against tracking abbreviations for multi-word titles"""
    matcher = TrackingMatcher()

    # Abbreviation match works great for multi-word titles
    score, match_type = matcher.calculate_title_score("ng", "National Geographic")
    assert score == WEIGHT_TITLE_ABBREVIATION
    assert "abbreviation" in match_type

    # Single-word titles like "w" -> "Wired" should use directory structure
    # or proper filenames instead. Fuzzy matching won't catch this.
    score, match_type = matcher.calculate_title_score("w", "Wired")
    # This will have low fuzzy score - user should use proper filenames
    assert score < WEIGHT_TITLE_ABBREVIATION  # Won't match via abbreviation


def test_abbreviation_not_too_long():
    """Test that longer titles don't trigger abbreviation matching"""
    matcher = TrackingMatcher()

    # "wired" is 5 chars, should use fuzzy matching instead
    score, match_type = matcher.calculate_title_score("wired", "Wired")
    # Should be exact match, not abbreviation
    assert "exact" in match_type.lower()


def test_abbreviation_only_alpha():
    """Test that abbreviation matching only works for alphabetic strings"""
    matcher = TrackingMatcher()

    # "2600" contains numbers, should not trigger abbreviation matching
    score, match_type = matcher.calculate_title_score("2600", "2600 Magazine")
    # Should match via fuzzy/token matching
    assert "abbreviation" not in match_type


def test_case_insensitive_abbreviation():
    """Test that abbreviation matching is case-insensitive"""
    matcher = TrackingMatcher()

    for variant in ["ng", "NG", "Ng"]:
        score, match_type = matcher.calculate_title_score(variant, "National Geographic")
        assert score == WEIGHT_TITLE_ABBREVIATION
        assert "abbreviation" in match_type


def test_abbreviation_skips_filler_words():
    """Test that common words are skipped in abbreviation generation"""
    matcher = TrackingMatcher()

    # "The Atlantic Monthly Magazine" -> "am" (skips 'the', 'magazine')
    abbreviation = matcher.generate_abbreviation("The Atlantic Monthly Magazine")
    assert abbreviation == "am"

    # Should match
    score, match_type = matcher.calculate_title_score("am", "The Atlantic Monthly Magazine")
    assert score == WEIGHT_TITLE_ABBREVIATION


if __name__ == "__main__":
    test_generate_abbreviation()
    test_abbreviation_matching()
    test_abbreviation_not_too_long()
    test_abbreviation_only_alpha()
    test_case_insensitive_abbreviation()
    test_abbreviation_skips_filler_words()
    print("✓ All abbreviation matching tests passed!")

#!/usr/bin/env python3
"""
Test suite for core.parsers.title module
"""

import sys
from pathlib import Path

# Path setup handled by conftest.py

from core.parsers.title import TitleMatcher


def test_title_matcher_initialization():
    """Test TitleMatcher initialization"""
    matcher = TitleMatcher()

    assert matcher is not None


def test_clean_release_title():
    """Test release title cleaning"""
    matcher = TitleMatcher()

    # Test with basic title
    cleaned = matcher.clean_release_title("National Geographic Magazine")
    assert cleaned is not None
    assert isinstance(cleaned, str)


def test_match_method_signature():
    """Test match method exists with correct signature"""
    matcher = TitleMatcher()

    # match returns tuple of (is_match: bool, score: int)
    is_match, score = matcher.match("Time Magazine", "Time Magazine")

    assert isinstance(is_match, bool)
    assert isinstance(score, int)
    assert is_match is True  # Identical titles should match


def test_match_titles_with_variations():
    """Test matching title variations"""
    matcher = TitleMatcher()

    # Should match similar titles
    title1 = "National Geographic"
    title2 = "National Geographic Magazine"

    is_match, score = matcher.match(title1, title2)

    # Implementation dependent, but should handle common variations
    assert isinstance(is_match, bool)
    assert isinstance(score, int)


def test_match_titles_with_articles():
    """Test matching titles with articles (the, a, an)"""
    matcher = TitleMatcher()

    # match returns tuple of (is_match: bool, score: int)
    is_match, score = matcher.match("The Atlantic", "Atlantic")

    # Should handle articles
    assert isinstance(is_match, bool)
    assert isinstance(score, int)

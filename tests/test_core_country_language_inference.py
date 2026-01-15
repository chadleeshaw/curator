"""
Tests for automatic language inference from country detection.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.unified_parser import UnifiedParser


def test_german_inferred_from_de_country():
    """Test that German is inferred when [DE] country is detected"""
    parser = UnifiedParser()

    # Title with country but no explicit language indicator
    result = parser.parse_search_result(
        title="Wired Magazine [DE] - January 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "DE"
    assert result.language == "German", f"Expected 'German' but got '{result.language}'"


def test_french_inferred_from_fr_country():
    """Test that French is inferred when [FR] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="National Geographic [FR] December 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "FR"
    assert result.language == "French"


def test_spanish_inferred_from_es_country():
    """Test that Spanish is inferred when [ES] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Time Magazine [ES] 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "ES"
    assert result.language == "Spanish"


def test_italian_inferred_from_it_country():
    """Test that Italian is inferred when [IT] country indicator is present

    Note: [IT] is detected as a language indicator (Italian) via LANGUAGE_KEYWORDS,
    but the country detection filters out "IT" as a common English word. The language
    is still correctly set to Italian via the direct language detection.
    """
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="PC Gamer [IT] No.123 2024",
        url="http://example.com/download",
        provider="test"
    )

    # The country might not be detected due to "IT" being a common word filter
    # but language should still be Italian from LANGUAGE_KEYWORDS
    assert result.language == "Italian"


def test_italian_inferred_from_italia():
    """Test that Italian is inferred from 'Italia' keyword"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Wired Italia December 2024",
        url="http://example.com/download",
        provider="test"
    )

    # Should detect Italian language and IT country from "Italia"
    assert result.language == "Italian"
    # Country detection depends on find_country which looks for "Italia" -> "IT"


def test_portuguese_inferred_from_pt_country():
    """Test that Portuguese is inferred when [PT] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Wired [PT] Jan2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "PT"
    assert result.language == "Portuguese"


def test_portuguese_inferred_from_br_country():
    """Test that Portuguese is inferred for Brazil"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Magazine [BR] 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "BR"
    assert result.language == "Portuguese"


def test_japanese_inferred_from_jp_country():
    """Test that Japanese is inferred when [JP] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Gaming Weekly [JP] 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "JP"
    assert result.language == "Japanese"


def test_english_remains_for_us_country():
    """Test that English is correct for [US] country"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Wired [US] January 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "US"
    assert result.language == "English"


def test_english_inferred_from_uk_country():
    """Test that English is inferred when [UK] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Time Magazine [UK] 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "UK"
    assert result.language == "English"


def test_explicit_language_overrides_country_inference():
    """Test that explicit language indicator takes priority over country inference"""
    parser = UnifiedParser()

    # This has both [DE] country and explicit "GERMAN" keyword
    result = parser.parse_search_result(
        title="Wired Magazine [DE] GERMAN January 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "DE"
    assert result.language == "German"


def test_no_country_keeps_default_language():
    """Test that without country detection, language stays default"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Generic Magazine January 2024",
        url="http://example.com/download",
        provider="test"
    )

    # No country detected
    assert result.country is None
    # Should remain default (English)
    assert result.language == "English"


def test_chinese_inferred_from_cn_country():
    """Test that Chinese is inferred when [CN] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Tech Magazine [CN] 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "CN"
    assert result.language == "Chinese"


def test_polish_inferred_from_pl_country():
    """Test that Polish is inferred when [PL] country is detected"""
    parser = UnifiedParser()

    result = parser.parse_search_result(
        title="Computer World [PL] December 2024",
        url="http://example.com/download",
        provider="test"
    )

    assert result.country == "PL"
    assert result.language == "Polish"


if __name__ == "__main__":
    test_german_inferred_from_de_country()
    test_french_inferred_from_fr_country()
    test_spanish_inferred_from_es_country()
    test_italian_inferred_from_it_country()
    test_italian_inferred_from_italia()
    test_portuguese_inferred_from_pt_country()
    test_portuguese_inferred_from_br_country()
    test_japanese_inferred_from_jp_country()
    test_english_remains_for_us_country()
    test_english_inferred_from_uk_country()
    test_explicit_language_overrides_country_inference()
    test_no_country_keeps_default_language()
    test_chinese_inferred_from_cn_country()
    test_polish_inferred_from_pl_country()
    print("✓ All country-to-language inference tests passed!")

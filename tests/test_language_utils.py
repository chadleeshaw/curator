"""
Tests for language detection and processing utilities
"""

import pytest

from core.language_utils import (
    detect_language,
    generate_language_aware_olid,
    normalize_language_name,
)


class TestLanguageDetection:
    """Test language detection from text"""

    def test_detect_german(self):
        """Test detection of German language"""
        assert detect_language("Wired.Magazine.No.10.2024.GERMAN.HYBRID.MAGAZINE") == "German"
        assert detect_language("PC Gamer DEUTSCH Edition") == "German"
        assert detect_language("Magazine DE 2024") == "German"

    def test_detect_french(self):
        """Test detection of French language"""
        assert detect_language("Vogue FRENCH Edition") == "French"
        assert detect_language("Magazine FRANCAIS 2024") == "French"
        assert detect_language("Le Monde FR 2024") == "French"

    def test_detect_spanish(self):
        """Test detection of Spanish language"""
        assert detect_language("National Geographic SPANISH") == "Spanish"
        assert detect_language("Revista ESPANOL 2024") == "Spanish"
        assert detect_language("Magazine ES Edition") == "Spanish"

    def test_detect_italian(self):
        """Test detection of Italian language"""
        assert detect_language("Vogue ITALIAN Edition") == "Italian"
        assert detect_language("Magazine ITALIANO 2024") == "Italian"
        assert detect_language("IT Edition 2024") == "Italian"

    def test_detect_portuguese(self):
        """Test detection of Portuguese language"""
        assert detect_language("Magazine PORTUGUESE Edition") == "Portuguese"
        assert detect_language("Revista PORTUGUES 2024") == "Portuguese"
        assert detect_language("PT Edition") == "Portuguese"

    def test_detect_dutch(self):
        """Test detection of Dutch language"""
        assert detect_language("Magazine DUTCH Edition") == "Dutch"
        assert detect_language("Tijdschrift NEDERLANDS") == "Dutch"
        assert detect_language("NL Magazine 2024") == "Dutch"

    def test_detect_polish(self):
        """Test detection of Polish language"""
        assert detect_language("Magazine POLISH Edition") == "Polish"
        assert detect_language("Magazyn POLSKI 2024") == "Polish"
        assert detect_language("PL Edition") == "Polish"

    def test_detect_russian(self):
        """Test detection of Russian language"""
        assert detect_language("Magazine RUSSIAN Edition") == "Russian"
        assert detect_language("Журнал RU 2024") == "Russian"

    def test_detect_japanese(self):
        """Test detection of Japanese language"""
        assert detect_language("Magazine JAPANESE Edition") == "Japanese"
        assert detect_language("JP Magazine") == "Japanese"

    def test_detect_chinese(self):
        """Test detection of Chinese language"""
        assert detect_language("Magazine CHINESE Edition") == "Chinese"
        assert detect_language("ZH Magazine") == "Chinese"
        assert detect_language("CN Edition") == "Chinese"

    def test_detect_korean(self):
        """Test detection of Korean language"""
        assert detect_language("Magazine KOREAN Edition") == "Korean"
        assert detect_language("KR Magazine") == "Korean"

    def test_default_english(self):
        """Test that default language is English"""
        assert detect_language("Wired Magazine February 2024") == "English"
        assert detect_language("PC Gamer January 2024") == "English"
        assert detect_language("Simple Magazine Title") == "English"

    def test_case_insensitive(self):
        """Test that detection is case insensitive"""
        assert detect_language("magazine german edition") == "German"
        assert detect_language("MAGAZINE GERMAN EDITION") == "German"
        assert detect_language("Magazine German Edition") == "German"

    def test_empty_text(self):
        """Test handling of empty text"""
        assert detect_language("") == "English"
        assert detect_language(None) == "English"

    def test_custom_default(self):
        """Test custom default language"""
        assert detect_language("Unknown Magazine", default="Unknown") == "Unknown"

    def test_word_boundary_matching(self):
        """Test that language indicators match whole words"""
        # "IT" should match as Italian, not just any "it" substring
        assert detect_language("IT Magazine") == "Italian"
        # But "it" in middle of word shouldn't match
        assert detect_language("Fitness Magazine") == "English"

    def test_scene_release_format(self):
        """Test detection in scene release formatted names"""
        assert detect_language("PC.Gamer.UK.2024-01.GERMAN-TEAM") == "German"
        assert detect_language("Wired.Magazine.2024.02.FRENCH.RETAiL-MAGAZiNE") == "French"
        assert detect_language("National.Geographic.2024.SPANISH.iNTERNAL-GROUP") == "Spanish"


class TestNormalizeLanguageName:
    """Test language name normalization"""

    def test_normalize_uppercase(self):
        """Test normalization of uppercase names"""
        assert normalize_language_name("GERMAN") == "German"
        assert normalize_language_name("FRENCH") == "French"
        assert normalize_language_name("SPANISH") == "Spanish"

    def test_normalize_lowercase(self):
        """Test normalization of lowercase names"""
        assert normalize_language_name("german") == "German"
        assert normalize_language_name("french") == "French"
        assert normalize_language_name("spanish") == "Spanish"

    def test_normalize_language_codes(self):
        """Test normalization of ISO language codes"""
        assert normalize_language_name("en") == "English"
        assert normalize_language_name("de") == "German"
        assert normalize_language_name("fr") == "French"
        assert normalize_language_name("es") == "Spanish"
        assert normalize_language_name("it") == "Italian"
        assert normalize_language_name("pt") == "Portuguese"
        assert normalize_language_name("nl") == "Dutch"
        assert normalize_language_name("pl") == "Polish"
        assert normalize_language_name("ru") == "Russian"
        assert normalize_language_name("ja") == "Japanese"
        assert normalize_language_name("zh") == "Chinese"
        assert normalize_language_name("ko") == "Korean"

    def test_normalize_empty(self):
        """Test normalization of empty string"""
        assert normalize_language_name("") == "English"
        assert normalize_language_name(None) == "English"

    def test_normalize_unknown_language(self):
        """Test normalization of unknown language"""
        assert normalize_language_name("Klingon") == "Klingon"
        assert normalize_language_name("elvish") == "Elvish"

    def test_normalize_mixed_case(self):
        """Test normalization of mixed case"""
        assert normalize_language_name("GeRmAn") == "German"
        assert normalize_language_name("FrEnCh") == "French"


class TestGenerateLanguageAwareOlid:
    """Test language-aware OLID generation"""

    def test_english_no_suffix(self):
        """Test that English editions don't get suffix"""
        assert generate_language_aware_olid("wired", "English") == "wired"
        assert generate_language_aware_olid("pc_gamer", "English") == "pc_gamer"

    def test_german_suffix(self):
        """Test German language suffix"""
        assert generate_language_aware_olid("wired", "German") == "wired_german"
        assert generate_language_aware_olid("national_geographic", "German") == "national_geographic_german"

    def test_french_suffix(self):
        """Test French language suffix"""
        assert generate_language_aware_olid("vogue", "French") == "vogue_french"

    def test_spanish_suffix(self):
        """Test Spanish language suffix"""
        assert generate_language_aware_olid("time", "Spanish") == "time_spanish"

    def test_italian_suffix(self):
        """Test Italian language suffix"""
        assert generate_language_aware_olid("wired", "Italian") == "wired_italian"

    def test_portuguese_suffix(self):
        """Test Portuguese language suffix"""
        assert generate_language_aware_olid("vogue", "Portuguese") == "vogue_portuguese"

    def test_case_insensitive_english(self):
        """Test that 'english' in any case doesn't get suffix"""
        assert generate_language_aware_olid("wired", "english") == "wired"
        assert generate_language_aware_olid("wired", "ENGLISH") == "wired"
        assert generate_language_aware_olid("wired", "English") == "wired"

    def test_empty_language(self):
        """Test that empty language doesn't add suffix"""
        assert generate_language_aware_olid("wired", "") == "wired"
        assert generate_language_aware_olid("wired", None) == "wired"

    def test_lowercase_suffix(self):
        """Test that suffix is always lowercase"""
        assert generate_language_aware_olid("wired", "GERMAN") == "wired_german"
        assert generate_language_aware_olid("wired", "German") == "wired_german"
        assert generate_language_aware_olid("wired", "GeRmAn") == "wired_german"

    def test_multiple_underscores(self):
        """Test OLID with existing underscores"""
        assert generate_language_aware_olid("pc_gamer_uk", "German") == "pc_gamer_uk_german"

    def test_special_characters_in_olid(self):
        """Test OLID with special characters"""
        assert generate_language_aware_olid("2600-magazine", "German") == "2600-magazine_german"


class TestLanguageDetectionIntegration:
    """Integration tests for language detection workflow"""

    def test_detect_and_generate_olid(self):
        """Test complete workflow: detect language and generate OLID"""
        title = "Wired.Magazine.No.10.2024.GERMAN.HYBRID.MAGAZINE"
        language = detect_language(title)
        olid = generate_language_aware_olid("wired", language)

        assert language == "German"
        assert olid == "wired_german"

    def test_english_workflow(self):
        """Test workflow for English magazine"""
        title = "Wired Magazine - February 2024"
        language = detect_language(title)
        olid = generate_language_aware_olid("wired", language)

        assert language == "English"
        assert olid == "wired"

    def test_normalize_then_generate(self):
        """Test normalization before OLID generation"""
        raw_language = "de"
        normalized = normalize_language_name(raw_language)
        olid = generate_language_aware_olid("wired", normalized)

        assert normalized == "German"
        assert olid == "wired_german"

    def test_multiple_languages_same_base(self):
        """Test that different languages get different OLIDs"""
        base = "wired"

        english_olid = generate_language_aware_olid(base, "English")
        german_olid = generate_language_aware_olid(base, "German")
        french_olid = generate_language_aware_olid(base, "French")

        assert english_olid == "wired"
        assert german_olid == "wired_german"
        assert french_olid == "wired_french"

        # All should be unique
        assert len({english_olid, german_olid, french_olid}) == 3

"""
Tests for extract_base_title special edition detection and metadata builder field unification.

Test Coverage:
- extract_base_title: Explicit "Special Edition" patterns (Pattern 1/1b)
- extract_base_title: Keyword-based detection (Pattern 2)
- extract_base_title: Multi-word titles NOT falsely flagged as special editions
- build_derived_metadata: is_special_edition / special_edition field alias merge
"""

from core.parsers.title import TitleMatcher
from core.utils.metadata_builder import build_derived_metadata


class TestExtractBaseTitle:
    """Tests for TitleMatcher.extract_base_title special edition detection."""

    matcher: TitleMatcher

    def setup_method(self):
        self.matcher = TitleMatcher()

    # ---- Pattern 1: Explicit "Special Edition" with name ----

    def test_explicit_special_edition_with_name(self):
        """'Title Special Edition Name' should split correctly."""
        base, is_special, name = self.matcher.extract_base_title("Time Special Edition Person Of The Year")
        assert is_special is True
        assert base == "Time"
        assert name == "Person Of The Year"

    def test_explicit_special_edition_with_multi_word_base(self):
        base, is_special, name = self.matcher.extract_base_title("National Geographic Special Edition Wildlife")
        assert is_special is True
        assert base == "National Geographic"
        assert name == "Wildlife"

    # ---- Pattern 1b: "Special Edition" without name ----

    def test_explicit_special_edition_no_name(self):
        base, is_special, name = self.matcher.extract_base_title("Food & Wine Special Edition")
        assert is_special is True
        assert base == "Food & Wine"
        assert name == "Special Edition"

    # ---- Pattern 2: Keyword-based detection ----

    def test_keyword_annual_edition(self):
        base, is_special, name = self.matcher.extract_base_title("National Geographic Annual Edition")
        assert is_special is True
        assert base == "National Geographic"
        assert "Annual Edition" in name

    def test_keyword_holiday_special(self):
        base, is_special, name = self.matcher.extract_base_title("Wired Holiday Special 2024")
        assert is_special is True
        assert base == "Wired"
        assert "Holiday Special" in name

    def test_keyword_holiday_special_with_separator(self):
        """Dash separator before keyword should be stripped from base title."""
        base, is_special, name = self.matcher.extract_base_title("Wired - Holiday Special 2024")
        assert is_special is True
        assert base == "Wired"
        assert "Holiday Special" in name

    def test_keyword_swimsuit_annual(self):
        base, is_special, name = self.matcher.extract_base_title("Sports Illustrated Swimsuit Annual")
        assert is_special is True
        assert base == "Sports Illustrated"
        assert "Swimsuit Annual" in name

    def test_keyword_best_of(self):
        base, is_special, name = self.matcher.extract_base_title("PC Gamer Best Of 2024")
        assert is_special is True
        assert base == "PC Gamer"

    def test_keyword_yearbook(self):
        base, is_special, name = self.matcher.extract_base_title("Time Yearbook 2024")
        assert is_special is True
        assert base == "Time"

    def test_keyword_single_word_base_title(self):
        """Single-word periodical names should still split correctly with keyword match."""
        base, is_special, name = self.matcher.extract_base_title("Wired Holiday Special")
        assert is_special is True
        assert base == "Wired"

    # ---- NOT special editions: multi-word titles that should NOT be split ----

    def test_multi_word_title_not_special(self):
        """'GQs' is a full title, NOT a special edition."""
        base, is_special, name = self.matcher.extract_base_title("GQs")
        assert is_special is False
        assert base == "GQs"
        assert name == ""

    def test_regular_periodical_not_special(self):
        base, is_special, name = self.matcher.extract_base_title("National Geographic")
        assert is_special is False
        assert base == "National Geographic"

    def test_regular_periodical_short_not_special(self):
        """PC Gamer should not be flagged as special."""
        base, is_special, name = self.matcher.extract_base_title("PC Gamer")
        assert is_special is False
        assert base == "PC Gamer"

    def test_cars_and_driver_review_not_special(self):
        base, is_special, name = self.matcher.extract_base_title("Cars And Driver Review")
        assert is_special is False

    def test_home_and_garden_ideas_not_special(self):
        base, is_special, name = self.matcher.extract_base_title("Home & Garden Ideas")
        assert is_special is False

    def test_guns_and_ammo_not_special(self):
        base, is_special, name = self.matcher.extract_base_title("Guns & Ammo")
        assert is_special is False

    def test_GQ_filename_cleaned_not_special(self):
        """The user's exact case: dot-separated NZB filename for a GQ spinoff."""
        cleaned = self.matcher.clean_release_title("GQs.December.2005.TruePDF")
        base, is_special, name = self.matcher.extract_base_title(cleaned)
        assert is_special is False
        assert "Girls Next Door" not in name


class TestDerivedMetadataFieldUnification:
    """Tests for is_special_edition / special_edition field alias merge in build_derived_metadata."""

    def test_ocr_special_edition_overrides_file_scan(self):
        """OCR's 'special_edition: false' should override file_scan's 'is_special_edition: true'."""
        file_scan = {
            "is_special_edition": True,
            "special_edition_name": "Girls Next Door",
            "title": "GQs Sexy Girls Next Door",
            "confidence": "high",
        }
        ocr_scan = {
            "special_edition": False,
            "overall_confidence": 73,
        }

        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        # OCR has higher priority, its "special_edition: false" should win as "is_special_edition"
        assert "is_special_edition" in derived
        assert derived["is_special_edition"]["value"] is False
        assert derived["is_special_edition"]["source"] == "ocr_scan"

    def test_file_scan_wins_when_no_ocr(self):
        """Without OCR data, file_scan's is_special_edition should be used."""
        file_scan = {
            "is_special_edition": True,
            "special_edition_name": "Holiday Issue",
            "confidence": "high",
        }

        derived = build_derived_metadata(file_scan=file_scan)

        assert "is_special_edition" in derived
        assert derived["is_special_edition"]["value"] is True
        assert derived["is_special_edition"]["source"] == "file_scan"

    def test_text_scan_special_edition_overrides_file_scan(self):
        """Text scan's special_edition should also override file_scan via alias."""
        file_scan = {
            "is_special_edition": True,
            "confidence": "high",
        }
        text_scan = {
            "special_edition": False,
            "overall_confidence": 65,
        }

        derived = build_derived_metadata(file_scan=file_scan, text_scan=text_scan)

        assert "is_special_edition" in derived
        assert derived["is_special_edition"]["value"] is False
        assert derived["is_special_edition"]["source"] == "text_scan"

    def test_no_duplicate_special_edition_field(self):
        """After unification, there should be no separate 'special_edition' field in derived."""
        file_scan = {
            "is_special_edition": True,
            "confidence": "high",
        }
        ocr_scan = {
            "special_edition": False,
            "overall_confidence": 80,
        }

        derived = build_derived_metadata(file_scan=file_scan, ocr_scan=ocr_scan)

        # The canonical field is "is_special_edition"; "special_edition" should not appear separately
        assert "special_edition" not in derived

    def test_special_edition_name_preserved(self):
        """special_edition_name should still come from file_scan (only source)."""
        file_scan = {
            "is_special_edition": True,
            "special_edition_name": "Holiday Issue",
            "confidence": "high",
        }

        derived = build_derived_metadata(file_scan=file_scan)

        assert "special_edition_name" in derived
        assert derived["special_edition_name"]["value"] == "Holiday Issue"

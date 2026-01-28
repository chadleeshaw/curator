"""
Tests for anti-periodical pattern filtering.

Validates that the parser correctly rejects non-periodical content
(movies, TV shows, audiobooks, etc.) BEFORE doing expensive parsing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from core.parsers.metadata import FilenameParser


class TestAntiPeriodicalFiltering:
    """Test that non-periodical content is correctly rejected."""

    @pytest.fixture
    def parser(self):
        """Create parser instance for testing."""
        return FilenameParser()

    # ========================================================================
    # Video Resolution & Quality Indicators
    # ========================================================================

    def test_reject_1080p_video(self, parser):
        """Reject video files with 1080p resolution indicator."""
        result = parser.extract_from_nzb_title("Movie.Name.2024.1080p.BluRay.x264-GROUP")
        assert result is None

    def test_reject_720p_video(self, parser):
        """Reject video files with 720p resolution indicator."""
        result = parser.extract_from_nzb_title("TV.Show.S01E01.720p.WEB-DL")
        assert result is None

    def test_reject_4k_video(self, parser):
        """Reject video files with 4K resolution indicator."""
        result = parser.extract_from_nzb_title("Movie.2024.4K.UHD.BluRay.x265")
        assert result is None

    def test_reject_2160p_video(self, parser):
        """Reject video files with 2160p (4K) resolution."""
        result = parser.extract_from_nzb_title("Documentary.2024.2160p.WEB-DL.DDP5.1.x265")
        assert result is None

    def test_reject_bluray_rip(self, parser):
        """Reject BluRay rips."""
        result = parser.extract_from_nzb_title("Film.2024.BRRip.XviD-GROUP")
        assert result is None

    def test_reject_web_dl(self, parser):
        """Reject WEB-DL releases."""
        result = parser.extract_from_nzb_title("Series.S02E05.WEB-DL.AAC2.0.H264")
        assert result is None

    def test_reject_hdtv(self, parser):
        """Reject HDTV recordings."""
        result = parser.extract_from_nzb_title("Show.2024.01.15.HDTV.x264-GROUP")
        assert result is None

    def test_reject_dvdrip(self, parser):
        """Reject DVD rips."""
        result = parser.extract_from_nzb_title("Movie.DVDRip.XviD-GROUP")
        assert result is None

    # ========================================================================
    # Video Codecs
    # ========================================================================

    def test_reject_x264_codec(self, parser):
        """Reject videos with x264 codec."""
        result = parser.extract_from_nzb_title("Movie.2024.x264.AAC")
        assert result is None

    def test_reject_x265_codec(self, parser):
        """Reject videos with x265 codec."""
        result = parser.extract_from_nzb_title("Film.2024.x265.HEVC")
        assert result is None

    def test_reject_hevc_codec(self, parser):
        """Reject videos with HEVC codec."""
        result = parser.extract_from_nzb_title("Movie.2024.HEVC.1080p")
        assert result is None

    def test_reject_xvid_codec(self, parser):
        """Reject videos with XviD codec."""
        result = parser.extract_from_nzb_title("Old.Movie.XviD.AC3")
        assert result is None

    def test_reject_h264(self, parser):
        """Reject videos with H.264 codec."""
        result = parser.extract_from_nzb_title("Video.H264.AAC")
        assert result is None

    def test_reject_h265(self, parser):
        """Reject videos with H.265 codec."""
        result = parser.extract_from_nzb_title("Video.H.265.1080p")
        assert result is None

    # ========================================================================
    # Audio Codecs (common in video releases)
    # ========================================================================

    def test_reject_aac_audio(self, parser):
        """Reject videos with AAC audio."""
        result = parser.extract_from_nzb_title("Movie.2024.AAC.x264")
        assert result is None

    def test_reject_dts_audio(self, parser):
        """Reject videos with DTS audio."""
        result = parser.extract_from_nzb_title("Film.2024.DTS-HD.BluRay")
        assert result is None

    def test_reject_dd51_audio(self, parser):
        """Reject videos with DD5.1 surround sound."""
        result = parser.extract_from_nzb_title("Movie.2024.DD5.1.x265")
        assert result is None

    def test_reject_atmos_audio(self, parser):
        """Reject videos with Dolby Atmos audio."""
        result = parser.extract_from_nzb_title("Film.2024.Atmos.TrueHD.BluRay")
        assert result is None

    # ========================================================================
    # TV Show Indicators
    # ========================================================================

    def test_reject_tv_show_s01e01(self, parser):
        """Reject TV shows with S01E01 notation."""
        result = parser.extract_from_nzb_title("Show.Name.S01E01.1080p.WEB-DL")
        assert result is None

    def test_reject_tv_show_1x01(self, parser):
        """Reject TV shows with 1x01 notation."""
        result = parser.extract_from_nzb_title("Series.1x01.720p.HDTV")
        assert result is None

    def test_reject_tv_series_keyword(self, parser):
        """Reject titles with 'TV Series' keyword."""
        result = parser.extract_from_nzb_title("Documentary.TV.Series.2024")
        assert result is None

    def test_reject_season_pack(self, parser):
        """Reject TV season packs."""
        result = parser.extract_from_nzb_title("Show.Season.1.Complete.1080p")
        assert result is None

    # ========================================================================
    # Movie/Film Keywords
    # ========================================================================

    def test_reject_movie_keyword(self, parser):
        """Reject titles with 'movie' keyword."""
        result = parser.extract_from_nzb_title("Action.Movie.2024.1080p.BluRay")
        assert result is None

    def test_reject_film_keyword(self, parser):
        """Reject titles with 'film' keyword."""
        result = parser.extract_from_nzb_title("Independent.Film.2024.WEB-DL")
        assert result is None

    def test_reject_video_keyword(self, parser):
        """Reject titles with generic 'video' keyword."""
        result = parser.extract_from_nzb_title("Training.Video.2024")
        assert result is None
        result = parser.extract_from_nzb_title("Educational Video Series")
        assert result is None

    def test_reject_directors_cut(self, parser):
        """Reject director's cut releases."""
        result = parser.extract_from_nzb_title("Film.Directors.Cut.2024.BluRay")
        assert result is None

    def test_reject_extended_cut(self, parser):
        """Reject extended cut releases."""
        result = parser.extract_from_nzb_title("Movie.Extended.Cut.1080p")
        assert result is None

    def test_reject_imax(self, parser):
        """Reject IMAX releases."""
        result = parser.extract_from_nzb_title("Film.IMAX.2024.4K.BluRay")
        assert result is None

    # ========================================================================
    # Audiobook Indicators
    # ========================================================================

    def test_reject_audiobook(self, parser):
        """Reject audiobooks."""
        result = parser.extract_from_nzb_title("Book.Title.Audiobook.MP3")
        assert result is None

    def test_reject_unabridged_audiobook(self, parser):
        """Reject unabridged audiobooks."""
        result = parser.extract_from_nzb_title("Novel.Unabridged.Audiobook")
        assert result is None

    def test_reject_narrated_by(self, parser):
        """Reject titles with narrator information."""
        result = parser.extract_from_nzb_title("Book.Narrated.By.Famous.Actor")
        assert result is None

    # ========================================================================
    # Documentary Indicators
    # ========================================================================

    def test_reject_documentary(self, parser):
        """Reject documentaries."""
        result = parser.extract_from_nzb_title("Nature.Documentary.2024.1080p")
        assert result is None

    def test_reject_docuseries(self, parser):
        """Reject documentary series."""
        result = parser.extract_from_nzb_title("History.Docuseries.S01.1080p")
        assert result is None

    # ========================================================================
    # Music/Soundtrack Indicators
    # ========================================================================

    def test_reject_soundtrack(self, parser):
        """Reject movie soundtracks."""
        result = parser.extract_from_nzb_title("Movie.Soundtrack.2024.FLAC")
        assert result is None

    def test_reject_ost(self, parser):
        """Reject original soundtracks (OST)."""
        result = parser.extract_from_nzb_title("Game.OST.MP3.320kbps")
        assert result is None

    def test_reject_album(self, parser):
        """Reject music albums."""
        result = parser.extract_from_nzb_title("Artist.Album.2024.FLAC")
        assert result is None

    # ========================================================================
    # Video File Extensions
    # ========================================================================

    def test_reject_mkv_extension(self, parser):
        """Reject titles with .mkv extension in name."""
        result = parser.extract_from_nzb_title("Movie.mkv.1080p")
        assert result is None

    def test_reject_avi_extension(self, parser):
        """Reject titles with .avi extension in name."""
        result = parser.extract_from_nzb_title("Video.avi.XviD")
        assert result is None

    # ========================================================================
    # Multi-Subtitle/Language (common in video)
    # ========================================================================

    def test_reject_multisub(self, parser):
        """Reject multi-subtitle releases."""
        result = parser.extract_from_nzb_title("Movie.2024.1080p.MultiSub.x264")
        assert result is None

    def test_reject_multi_audio(self, parser):
        """Reject multi-audio releases."""
        result = parser.extract_from_nzb_title("Film.2024.Multi-Audio.BluRay")
        assert result is None

    # ========================================================================
    # Release Group Tags (video-specific)
    # ========================================================================

    def test_reject_yify_release(self, parser):
        """Reject YIFY releases (popular movie group)."""
        result = parser.extract_from_nzb_title("Movie.2024.1080p.YIFY")
        assert result is None

    def test_reject_rarbg_release(self, parser):
        """Reject RARBG releases (popular video group)."""
        result = parser.extract_from_nzb_title("Film.2024.1080p.RARBG")
        assert result is None

    # ========================================================================
    # Complex Real-World Examples
    # ========================================================================

    def test_reject_complex_movie_release(self, parser):
        """Reject complex movie release with multiple indicators."""
        result = parser.extract_from_nzb_title("The.Movie.Title.2024.1080p.BluRay.x265.HEVC.DTS-HD.MA.5.1-GROUP")
        assert result is None

    def test_reject_complex_tv_release(self, parser):
        """Reject complex TV show release."""
        result = parser.extract_from_nzb_title("Show.Name.S02E10.Episode.Title.1080p.WEB-DL.DD5.1.H.264-GROUP")
        assert result is None

    def test_reject_4k_hdr_movie(self, parser):
        """Reject 4K HDR movie release."""
        result = parser.extract_from_nzb_title("Film.2024.2160p.UHD.BluRay.x265.HDR.DTS-HD.MA.7.1.Atmos-GROUP")
        assert result is None

    # ========================================================================
    # Edge Cases: Should ACCEPT (not reject)
    # ========================================================================

    def test_accept_magazine_with_date(self, parser):
        """Accept magazine with proper date format."""
        result = parser.extract_from_nzb_title("Wired.Magazine.January.2024.pdf")
        assert result is not None
        assert result["title"] == "Wired Magazine"

    def test_accept_periodical_with_issue_number(self, parser):
        """Accept periodical with issue number."""
        result = parser.extract_from_nzb_title("PC.Gamer.Issue.389.2024.pdf")
        assert result is not None

    def test_accept_magazine_with_quality_indicator(self, parser):
        """Accept magazine with quality indicator (True PDF)."""
        result = parser.extract_from_nzb_title("National.Geographic.January.2024.True.PDF")
        assert result is not None
        # Note: Title parsing includes "True" - this is acceptable behavior
        # Quality indicators are extracted separately in the 'quality' field
        assert "National Geographic" in result["title"]

    def test_accept_magazine_with_country(self, parser):
        """Accept magazine with country code."""
        result = parser.extract_from_nzb_title("Time.Magazine.USA.January.2024")
        assert result is not None

    def test_accept_economist_weekly_format(self, parser):
        """Accept The Economist weekly date format."""
        result = parser.extract_from_nzb_title("The.Economist.2024.01.20.pdf")
        assert result is not None

    def test_accept_volume_issue_format(self, parser):
        """Accept volume/issue format (Science journals)."""
        result = parser.extract_from_nzb_title("Science.Vol.385.2024.pdf")
        assert result is not None

    def test_accept_magazine_2600(self, parser):
        """Accept 2600 Magazine (has number in name)."""
        # This is a famous hacker magazine - should not be rejected as "2600p"
        result = parser.extract_from_nzb_title("2600.Magazine.Spring.2024.pdf")
        assert result is not None

    # ========================================================================
    # Edge Cases: Potential False Positives
    # ========================================================================

    def test_magazine_named_film(self, parser):
        """Test magazine with 'Film' in the title (e.g., 'Film Comment')."""
        # This WILL be rejected by current patterns - might need refinement
        # Left as a known edge case for now
        result = parser.extract_from_nzb_title("Film.Comment.January.2024.pdf")
        # Currently rejects due to "film" keyword
        # Could be refined to check for date patterns before rejecting
        assert result is None  # Current behavior

    def test_magazine_about_movies(self, parser):
        """Test magazine about movies (e.g., 'Empire Movie Magazine')."""
        # This WILL be rejected - edge case that might need context-aware logic
        result = parser.extract_from_nzb_title("Empire.Movie.Magazine.January.2024.pdf")
        assert result is None  # Current behavior due to "movie" keyword


class TestAntiPeriodicalHelper:
    """Test the _has_anti_periodical_patterns helper method directly."""

    @pytest.fixture
    def parser(self):
        """Create parser instance for testing."""
        return FilenameParser()

    def test_normalizes_dots_and_underscores(self, parser):
        """Test that method normalizes dots and underscores."""
        # Should detect pattern even with dots/underscores
        assert parser._has_anti_periodical_patterns("Movie.Name.1080p.BluRay")
        assert parser._has_anti_periodical_patterns("Movie_Name_1080p_BluRay")
        assert parser._has_anti_periodical_patterns("Movie-Name-1080p-BluRay")

    def test_case_insensitive_matching(self, parser):
        """Test case-insensitive pattern matching."""
        assert parser._has_anti_periodical_patterns("MOVIE.2024.BLURAY")
        assert parser._has_anti_periodical_patterns("movie.2024.bluray")
        assert parser._has_anti_periodical_patterns("Movie.2024.BluRay")

    def test_returns_false_for_periodicals(self, parser):
        """Test that method returns False for valid periodicals."""
        assert not parser._has_anti_periodical_patterns("Wired Magazine January 2024")
        assert not parser._has_anti_periodical_patterns("National Geographic 2024-01")
        assert not parser._has_anti_periodical_patterns("PC Gamer Issue 389")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Test that sidecar tracking_id is validated against parsed metadata."""

from pathlib import Path
from unittest.mock import MagicMock
from services.importer.importer import FileImporter
from models.database import PeriodicalTracking


def test_sidecar_country_mismatch_rejects_tracking():
    """Sidecar tracking_id should be rejected if country doesn't match parsed metadata."""
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))

    # Mock tracking record: Wired USA (country=US)
    usa_tracking = PeriodicalTracking(
        id=2,
        title="Wired USA",
        country="US",
        language="English",
        user_id=1,
    )

    # Mock session
    session = MagicMock()
    session.query().filter().first.return_value = usa_tracking
    session.query().all.return_value = []

    # Try to use sidecar tracking_id=2 for a file parsed as South Africa
    result = importer._find_tracking_match(
        tracking_id=2,  # From sidecar (Wired USA)
        tracking_title="Wired",
        parsed_language="English",
        parsed_country="ZA",  # File is South Africa!
        category="Magazines",
        session=session,
    )

    # Should reject the sidecar and return None (will fall back to matching)
    assert result is None


def test_sidecar_language_mismatch_rejects_tracking():
    """Sidecar tracking_id should be rejected if language doesn't match."""
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))

    # Mock tracking record: Wired USA (language=English)
    usa_tracking = PeriodicalTracking(
        id=2,
        title="Wired USA",
        country="US",
        language="English",
        user_id=1,
    )

    session = MagicMock()
    session.query().filter().first.return_value = usa_tracking
    session.query().all.return_value = []

    # Try to use sidecar for a French edition
    result = importer._find_tracking_match(
        tracking_id=2,
        tracking_title="Wired",
        parsed_language="French",  # File is French!
        parsed_country="FR",
        category="Magazines",
        session=session,
    )

    # Should reject
    assert result is None


def test_sidecar_matching_country_language_accepts():
    """Sidecar tracking_id should be accepted if metadata matches."""
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))

    usa_tracking = PeriodicalTracking(
        id=2,
        title="Wired USA",
        country="US",
        language="English",
        user_id=1,
    )

    session = MagicMock()
    session.query().filter().first.return_value = usa_tracking

    # File matches the tracking record
    result = importer._find_tracking_match(
        tracking_id=2,
        tracking_title="Wired USA",
        parsed_language="English",
        parsed_country="US",
        category="Magazines",
        session=session,
    )

    # Should accept
    assert result == usa_tracking


def test_link_keeps_the_parsed_issue_language():
    """Linking does not copy the tracking language onto the issue."""
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))
    periodical = MagicMock()
    periodical.language = "English"
    tracking = PeriodicalTracking(
        id=7,
        title="North Title",
        country=None,
        language="Spanish",
        user_id=1,
    )
    session = MagicMock()

    importer._link_or_create_tracking(
        periodical=periodical,
        target_tracking=tracking,
        tracking_title="North Title",
        parsed_language="English",
        parsed_country=None,
        category="Magazines",
        is_special_edition=False,
        special_name=None,
        auto_track=True,
        tracking_mode="all",
        session=session,
    )

    assert periodical.language == "English"
    assert tracking.language == "Spanish"


def test_link_sets_tracking_language_when_the_record_has_none():
    """A new tracking language comes from the issue only when the record has none."""
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))
    periodical = MagicMock()
    periodical.language = "German"
    tracking = PeriodicalTracking(
        id=8,
        title="North Title",
        country=None,
        language=None,
        user_id=1,
    )
    session = MagicMock()

    importer._link_or_create_tracking(
        periodical=periodical,
        target_tracking=tracking,
        tracking_title="North Title",
        parsed_language="German",
        parsed_country="DE",
        category="Magazines",
        is_special_edition=False,
        special_name=None,
        auto_track=True,
        tracking_mode="all",
        session=session,
    )

    assert periodical.language == "German"
    assert tracking.language == "German"


def test_sidecar_no_country_on_tracking_accepts():
    """If tracking has no country set, don't reject based on country mismatch."""
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))

    # Tracking with no country specified
    generic_tracking = PeriodicalTracking(
        id=1,
        title="Wired",
        country=None,
        language="English",  # No country constraint
        user_id=1,
    )

    session = MagicMock()
    session.query().filter().first.return_value = generic_tracking

    # File has country but tracking doesn't - should accept
    result = importer._find_tracking_match(
        tracking_id=1,
        tracking_title="Wired",
        parsed_language="English",
        parsed_country="ZA",
        category="Magazines",
        session=session,
    )

    assert result == generic_tracking

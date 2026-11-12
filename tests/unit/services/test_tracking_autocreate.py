"""Auto-created tracking records need a real magazine name."""

from pathlib import Path
from unittest.mock import MagicMock

from services.importer.importer import FileImporter


def _create(title: str) -> tuple[MagicMock, MagicMock]:
    importer = FileImporter(downloads_dir=Path("/tmp"), library_base_dir=Path("/tmp"))
    periodical = MagicMock()
    periodical.tracking_id = None
    session = MagicMock()
    importer._link_or_create_tracking(
        periodical=periodical,
        target_tracking=None,
        tracking_title=title,
        parsed_language="English",
        parsed_country=None,
        category="Magazines",
        is_special_edition=False,
        special_name=None,
        auto_track=True,
        tracking_mode="all",
        session=session,
    )
    return periodical, session


def test_a_short_number_is_not_a_tracking_title():
    periodical, session = _create("137")

    assert periodical.tracking_id is None
    session.add.assert_not_called()


def test_a_leading_issue_number_is_not_a_tracking_title():
    periodical, session = _create("12 North Title")

    assert periodical.tracking_id is None
    session.add.assert_not_called()


def test_the_word_magazine_alone_is_not_a_tracking_title():
    for title in ("Magazine", "Mag"):
        periodical, session = _create(title)

        assert periodical.tracking_id is None
        session.add.assert_not_called()


def test_a_four_digit_name_and_a_plus_title_are_tracking_titles():
    for title in ("2600", "137+", "North Title", "3D World"):
        _periodical, session = _create(title)

        assert session.add.call_args[0][0].title == title

"""Results are accepted when they name the tracked title or one of its aliases."""

from types import SimpleNamespace

import pytest

from services.issue_discovery import IssueDiscoveryService

TRACKING = SimpleNamespace(title="Scientific American", search_aliases="SciAm, Sci American")


@pytest.mark.parametrize("provider", ["internet_archive", "newsnab"])
@pytest.mark.parametrize(
    "title, expected",
    [
        ("Scientific American March 2024", True),
        ("SciAm March 2024", True),  # alias only
        ("Popular Science March 2024", False),
    ],
)
def test_title_or_alias_matches(provider, title, expected):
    result = {"title": title, "provider": provider}
    assert IssueDiscoveryService()._title_matches_tracking(result, TRACKING) is expected

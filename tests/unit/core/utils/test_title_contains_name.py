"""Indexer results must name the tracked periodical before they are queued."""

import pytest

from core.utils.result_filter import title_contains_name


@pytest.mark.parametrize(
    "title, names, expected",
    [
        ("Wired.2024.06.Magazine", ["Wired"], True),
        ("Wiredrive Tutorial Collection 1", ["Wired"], False),
        ("Timeless 003 (2023) (4 Covers) (Digital)", ["Time"], False),
        ("Economists Weekly 018 (2013)", ["Economist"], False),
        # generic trailing words (magazine, country) are optional
        ("Forbes - 2012-05", ["Forbes Magazine"], True),
        ("Vogue.Winter.2025.HYBRID.MAGAZINE", ["Vogue USA"], True),
        # ...but the first word is always required
        ("People Weekly 2024-05", ["US Weekly"], False),
        # words may appear in any order; aliases count
        ("Muscle & Fitness, (Vol 62)", ["Muscle Fitness"], True),
        ("Australian.Geographic-May.2024", ["Geographic Australia", "Australian Geographic"], True),
        ("Womens Fitness UK-Issue 4", ["Mens Fitness"], False),
        # a one-word name needs an issue signal, and must not start a different title
        ("Club March 2024", ["Club"], True),
        ("Club Picnic", ["Club"], False),
        ("Club Times March 2024", ["Club"], False),
        ("Show.mkv", ["Show"], False),
    ],
)
def test_title_contains_name(title, names, expected):
    assert title_contains_name(title, names) is expected

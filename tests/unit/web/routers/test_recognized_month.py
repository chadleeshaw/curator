"""A metadata month counts only when it names a real month."""

import pytest

from web.routers.periodicals.metadata import _recognized_month


@pytest.mark.parametrize(
    ("text", "month"),
    [
        ("3", 3),
        ("03", 3),
        (3, 3),
        ("12", 12),
        ("March", 3),
        ("0", 0),
        ("00", 0),
        ("13", 0),
        ("nope", 0),
        ("3a", 0),
        ("", 0),
        (None, 0),
    ],
)
def test_recognized_month_accepts_names_and_numbers_from_1_to_12(text, month):
    assert _recognized_month(text) == month

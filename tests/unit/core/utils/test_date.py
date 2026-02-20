"""
Tests for core.utils.date module - date parsing and fuzzy matching utilities
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import pytest

from core.utils.date import dates_are_fuzzy_match, get_season_for_month


class TestGetSeasonForMonth:
    """Tests for get_season_for_month function"""

    def test_winter_months(self):
        """December, January, February are winter"""
        assert get_season_for_month(12) == "winter"
        assert get_season_for_month(1) == "winter"
        assert get_season_for_month(2) == "winter"

    def test_spring_months(self):
        """March, April, May are spring"""
        assert get_season_for_month(3) == "spring"
        assert get_season_for_month(4) == "spring"
        assert get_season_for_month(5) == "spring"

    def test_summer_months(self):
        """June, July, August are summer"""
        assert get_season_for_month(6) == "summer"
        assert get_season_for_month(7) == "summer"
        assert get_season_for_month(8) == "summer"

    def test_fall_months(self):
        """September, October, November are fall"""
        assert get_season_for_month(9) == "fall"
        assert get_season_for_month(10) == "fall"
        assert get_season_for_month(11) == "fall"


class TestDatesAreFuzzyMatch:
    """Tests for dates_are_fuzzy_match function"""

    def test_exact_match(self):
        """Same date is always a match"""
        d = date(2024, 6, 15)
        assert dates_are_fuzzy_match(d, d) is True

    def test_same_date_different_objects(self):
        """Same date in different objects is a match"""
        d1 = date(2024, 6, 15)
        d2 = date(2024, 6, 15)
        assert dates_are_fuzzy_match(d1, d2) is True

    def test_adjacent_months_within_tolerance(self):
        """
        Adjacent months (1 month apart) should match with default tolerance.
        This handles "February" search matching "January" library item.
        """
        jan = date(2024, 1, 1)
        feb = date(2024, 2, 1)
        assert dates_are_fuzzy_match(jan, feb) is True
        assert dates_are_fuzzy_match(feb, jan) is True

    def test_two_months_apart_exceeds_tolerance(self):
        """Dates 2 months apart should not match with default tolerance"""
        jan = date(2024, 1, 1)
        mar = date(2024, 3, 1)
        assert dates_are_fuzzy_match(jan, mar) is False

    def test_same_season_within_year(self):
        """
        Within a single year, same-season dates that are more than 1 month apart
        are NOT considered a match. Dec and Feb of the same year are 10 months apart
        and are clearly different issues (e.g. Winter 2024 vs Spring 2024 overlap).
        Only the cross-year boundary case (Dec -> Jan/Feb of next year) matches.
        """
        dec = date(2024, 12, 15)
        jan_same_year = date(2024, 1, 15)
        feb = date(2024, 2, 15)

        # Dec 2024 vs Feb 2024: 10 months apart — different issues, should NOT match
        assert dates_are_fuzzy_match(dec, feb) is False

        # Jan and Feb of the same year are 1 month apart — still matches via tolerance
        assert dates_are_fuzzy_match(jan_same_year, feb) is True

        # Spring: consecutive months within tolerance
        mar = date(2024, 3, 15)
        apr = date(2024, 4, 15)
        may = date(2024, 5, 15)

        assert dates_are_fuzzy_match(mar, apr) is True
        assert dates_are_fuzzy_match(apr, may) is True
        # Mar and May are 2 months apart — exceeds default tolerance
        assert dates_are_fuzzy_match(mar, may) is False

    def test_same_season_across_year_boundary(self):
        """
        Winter season spans year boundary (Dec 2024 -> Jan/Feb 2025).
        This is critical for preventing duplicate downloads of Winter issues.
        """
        dec_2024 = date(2024, 12, 15)
        jan_2025 = date(2025, 1, 15)
        feb_2025 = date(2025, 2, 15)

        # Dec 2024 and Jan 2025 are both winter - should match
        assert dates_are_fuzzy_match(dec_2024, jan_2025) is True

        # Dec 2024 and Feb 2025 are both winter - should match
        assert dates_are_fuzzy_match(dec_2024, feb_2025) is True

        # Jan 2025 and Feb 2025 are both winter - should match
        assert dates_are_fuzzy_match(jan_2025, feb_2025) is True

    def test_different_seasons_no_match(self):
        """Different seasons should not match"""
        winter = date(2024, 1, 15)
        spring = date(2024, 3, 15)
        summer = date(2024, 6, 15)
        fall = date(2024, 9, 15)

        assert dates_are_fuzzy_match(winter, spring) is False
        assert dates_are_fuzzy_match(spring, summer) is False
        assert dates_are_fuzzy_match(summer, fall) is False
        assert dates_are_fuzzy_match(fall, winter) is False

    def test_same_season_but_too_many_years_apart(self):
        """Same season but more than 1 year apart should not match"""
        jan_2024 = date(2024, 1, 15)
        jan_2026 = date(2026, 1, 15)

        # More than 1 year apart
        assert dates_are_fuzzy_match(jan_2024, jan_2026) is False

    def test_edge_case_feb_and_december_previous_year(self):
        """
        Feb 2024 and Dec 2023 are both winter but 2 months apart.
        Should match because they're in the same season.
        """
        dec_2023 = date(2023, 12, 15)
        feb_2024 = date(2024, 2, 15)

        assert dates_are_fuzzy_match(dec_2023, feb_2024) is True

    def test_custom_tolerance(self):
        """Can override tolerance for stricter/looser matching"""
        jan = date(2024, 1, 1)
        mar = date(2024, 3, 1)
        apr = date(2024, 4, 1)

        # Default tolerance (1 month) - Jan and Mar don't match
        assert dates_are_fuzzy_match(jan, mar, tolerance_months=1) is False

        # Higher tolerance (2 months) - Jan and Mar do match
        assert dates_are_fuzzy_match(jan, mar, tolerance_months=2) is True

        # Jan and Apr are 3 months apart - still don't match with tolerance=2
        assert dates_are_fuzzy_match(jan, apr, tolerance_months=2) is False

    def test_real_world_scenario_february_equals_january(self):
        """
        Real-world issue: Search shows February 2024, library has January 2024.
        This is the same issue where date was defaulted to January 1st.
        """
        library_date = date(2024, 1, 1)  # Defaulted to Jan 1
        search_date = date(2024, 2, 1)  # Search result shows Feb

        # Should match - likely the same issue
        assert dates_are_fuzzy_match(library_date, search_date) is True

    def test_real_world_scenario_winter_equals_december(self):
        """
        Real-world issue: "Winter 2024" search result shows as December,
        but library has it as January or February.
        """
        # Winter issue stored as December
        library_december = date(2024, 12, 1)

        # Winter could also be parsed as January or February
        search_january = date(2025, 1, 1)
        search_february = date(2025, 2, 1)

        # All should match - same Winter issue
        assert dates_are_fuzzy_match(library_december, search_january) is True
        assert dates_are_fuzzy_match(library_december, search_february) is True

    def test_real_world_scenario_winter_within_same_calendar_year(self):
        """
        Winter 2024 issue could be stored as any of Dec 2023, Jan 2024, or Feb 2024.
        All should be considered the same issue.
        """
        dec_2023 = date(2023, 12, 1)
        jan_2024 = date(2024, 1, 1)
        feb_2024 = date(2024, 2, 1)

        # All combinations should match
        assert dates_are_fuzzy_match(dec_2023, jan_2024) is True
        assert dates_are_fuzzy_match(dec_2023, feb_2024) is True
        assert dates_are_fuzzy_match(jan_2024, feb_2024) is True

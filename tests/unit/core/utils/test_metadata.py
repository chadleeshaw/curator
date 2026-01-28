"""
Unit tests for core/utils/metadata.py
"""

import pytest
from unittest.mock import MagicMock

from core.utils.metadata import (
    get_cover_page_index,
    set_cover_page_index,
    get_metadata_field,
)


class TestGetCoverPageIndex:
    """Tests for get_cover_page_index()"""

    def test_no_extra_metadata_zero_based(self):
        """Returns 0 when no extra_metadata exists (zero-based)"""
        periodical = MagicMock()
        periodical.extra_metadata = None

        result = get_cover_page_index(periodical, zero_based=True)

        assert result == 0

    def test_no_extra_metadata_one_based(self):
        """Returns 1 when no extra_metadata exists (one-based)"""
        periodical = MagicMock()
        periodical.extra_metadata = None

        result = get_cover_page_index(periodical, zero_based=False)

        assert result == 1

    def test_no_cover_page_in_metadata_zero_based(self):
        """Returns 0 when cover_page not in extra_metadata (zero-based)"""
        periodical = MagicMock()
        periodical.extra_metadata = {"other_field": "value"}

        result = get_cover_page_index(periodical, zero_based=True)

        assert result == 0

    def test_no_cover_page_in_metadata_one_based(self):
        """Returns 1 when cover_page not in extra_metadata (one-based)"""
        periodical = MagicMock()
        periodical.extra_metadata = {"other_field": "value"}

        result = get_cover_page_index(periodical, zero_based=False)

        assert result == 1

    def test_cover_page_exists_zero_based(self):
        """Converts stored 1-based to 0-based correctly"""
        periodical = MagicMock()
        periodical.extra_metadata = {"cover_page": 3}  # 1-based: page 3

        result = get_cover_page_index(periodical, zero_based=True)

        assert result == 2  # 0-based: index 2

    def test_cover_page_exists_one_based(self):
        """Returns stored 1-based value as-is"""
        periodical = MagicMock()
        periodical.extra_metadata = {"cover_page": 3}

        result = get_cover_page_index(periodical, zero_based=False)

        assert result == 3

    def test_cover_page_first_page_zero_based(self):
        """First page (stored as 1) returns 0 when zero-based"""
        periodical = MagicMock()
        periodical.extra_metadata = {"cover_page": 1}

        result = get_cover_page_index(periodical, zero_based=True)

        assert result == 0

    def test_default_is_zero_based(self):
        """Default behavior is zero-based"""
        periodical = MagicMock()
        periodical.extra_metadata = {"cover_page": 5}

        result = get_cover_page_index(periodical)

        assert result == 4  # 5 - 1 = 4


class TestSetCoverPageIndex:
    """Tests for set_cover_page_index()"""

    def test_creates_extra_metadata_if_none(self):
        """Creates extra_metadata dict if it doesn't exist"""
        periodical = MagicMock()
        periodical.extra_metadata = None

        set_cover_page_index(periodical, 0, zero_based=True)

        assert periodical.extra_metadata == {"cover_page": 1}

    def test_set_zero_based_index(self):
        """Converts 0-based index to 1-based for storage"""
        periodical = MagicMock()
        periodical.extra_metadata = {}

        set_cover_page_index(periodical, 2, zero_based=True)

        assert periodical.extra_metadata["cover_page"] == 3  # 2 + 1 = 3

    def test_set_one_based_index(self):
        """Stores 1-based index as-is"""
        periodical = MagicMock()
        periodical.extra_metadata = {}

        set_cover_page_index(periodical, 3, zero_based=False)

        assert periodical.extra_metadata["cover_page"] == 3

    def test_overwrites_existing_cover_page(self):
        """Overwrites existing cover_page value"""
        periodical = MagicMock()
        periodical.extra_metadata = {"cover_page": 1, "other": "value"}

        set_cover_page_index(periodical, 4, zero_based=True)

        assert periodical.extra_metadata["cover_page"] == 5
        assert periodical.extra_metadata["other"] == "value"

    def test_first_page_zero_based(self):
        """Setting first page (index 0) stores as 1"""
        periodical = MagicMock()
        periodical.extra_metadata = {}

        set_cover_page_index(periodical, 0, zero_based=True)

        assert periodical.extra_metadata["cover_page"] == 1


class TestGetMetadataField:
    """Tests for get_metadata_field()"""

    def test_returns_default_when_no_metadata(self):
        """Returns default when both metadata dicts are None"""
        periodical = MagicMock()
        periodical.derived_metadata = None
        periodical.extra_metadata = None

        result = get_metadata_field(periodical, "category", "Unknown")

        assert result == "Unknown"

    def test_returns_none_default_when_not_specified(self):
        """Returns None when field not found and no default specified"""
        periodical = MagicMock()
        periodical.derived_metadata = None
        periodical.extra_metadata = None

        result = get_metadata_field(periodical, "category")

        assert result is None

    def test_derived_metadata_takes_priority(self):
        """derived_metadata value is returned over extra_metadata"""
        periodical = MagicMock()
        periodical.derived_metadata = {"category": "Derived Category"}
        periodical.extra_metadata = {"category": "Extra Category"}

        result = get_metadata_field(periodical, "category")

        assert result == "Derived Category"

    def test_falls_back_to_extra_metadata(self):
        """Falls back to extra_metadata when field not in derived_metadata"""
        periodical = MagicMock()
        periodical.derived_metadata = {"other": "value"}
        periodical.extra_metadata = {"category": "Extra Category"}

        result = get_metadata_field(periodical, "category")

        assert result == "Extra Category"

    def test_handles_structured_derived_metadata(self):
        """Extracts value from structured derived_metadata format"""
        periodical = MagicMock()
        periodical.derived_metadata = {
            "category": {"value": "Structured Category", "source": "ocr"}
        }
        periodical.extra_metadata = None

        result = get_metadata_field(periodical, "category")

        assert result == "Structured Category"

    def test_handles_simple_derived_metadata(self):
        """Returns simple derived_metadata value directly"""
        periodical = MagicMock()
        periodical.derived_metadata = {"category": "Simple Value"}
        periodical.extra_metadata = None

        result = get_metadata_field(periodical, "category")

        assert result == "Simple Value"

    def test_empty_dicts_return_default(self):
        """Returns default when metadata dicts are empty"""
        periodical = MagicMock()
        periodical.derived_metadata = {}
        periodical.extra_metadata = {}

        result = get_metadata_field(periodical, "category", "Default")

        assert result == "Default"

    def test_none_derived_but_valid_extra(self):
        """Works when derived_metadata is None but extra_metadata has value"""
        periodical = MagicMock()
        periodical.derived_metadata = None
        periodical.extra_metadata = {"language": "English"}

        result = get_metadata_field(periodical, "language")

        assert result == "English"

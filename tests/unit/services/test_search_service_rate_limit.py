"""
Tests for SearchService.all_providers_rate_limited property.

Test Coverage:
- Returns False when no providers exist
- Returns False when at least one provider is not rate limited
- Returns True when all providers are rate limited
- Returns False when all providers are available
"""

from unittest.mock import MagicMock, PropertyMock

from core.interfaces import SearchProvider
from services.download.search_service import SearchService


def _make_mock_provider(name: str, rate_limited: bool) -> MagicMock:
    """Create a mock SearchProvider with a configurable is_rate_limited."""
    provider = MagicMock(spec=SearchProvider)
    provider.name = name
    provider.priority = 10
    type(provider).is_rate_limited = PropertyMock(return_value=rate_limited)
    return provider


class TestAllProvidersRateLimited:
    """Tests for SearchService.all_providers_rate_limited property."""

    def test_false_when_no_providers(self):
        """Should return False when there are no search providers."""
        service = SearchService(search_providers=[])
        assert not service.all_providers_rate_limited

    def test_false_when_all_available(self):
        """Should return False when all providers are available (not rate limited)."""
        providers = [
            _make_mock_provider("provider-a", rate_limited=False),
            _make_mock_provider("provider-b", rate_limited=False),
        ]
        service = SearchService(search_providers=providers)
        assert not service.all_providers_rate_limited

    def test_false_when_some_available(self):
        """Should return False when at least one provider is available."""
        providers = [
            _make_mock_provider("provider-a", rate_limited=True),
            _make_mock_provider("provider-b", rate_limited=False),
        ]
        service = SearchService(search_providers=providers)
        assert not service.all_providers_rate_limited

    def test_true_when_all_rate_limited(self):
        """Should return True when all providers are rate limited."""
        providers = [
            _make_mock_provider("provider-a", rate_limited=True),
            _make_mock_provider("provider-b", rate_limited=True),
        ]
        service = SearchService(search_providers=providers)
        assert service.all_providers_rate_limited

    def test_true_when_single_provider_rate_limited(self):
        """Should return True when the only provider is rate limited."""
        providers = [
            _make_mock_provider("sole-provider", rate_limited=True),
        ]
        service = SearchService(search_providers=providers)
        assert service.all_providers_rate_limited

    def test_false_when_single_provider_available(self):
        """Should return False when the only provider is available."""
        providers = [
            _make_mock_provider("sole-provider", rate_limited=False),
        ]
        service = SearchService(search_providers=providers)
        assert not service.all_providers_rate_limited

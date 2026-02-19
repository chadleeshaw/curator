"""
Search router dependencies and global state.

This module manages the injected dependencies used by all search endpoints.
"""

from typing import Any, Callable, Optional

# Global state (injected from main app)
_search_providers: Optional[Any] = None
_metadata_providers: Optional[Any] = None
_title_matcher: Optional[Any] = None
_session_factory: Optional[Callable] = None


def set_dependencies(
    search_providers: Any,
    metadata_providers: Any,
    title_matcher: Any,
    session_factory: Callable,
) -> None:
    """Set dependencies from main app"""
    global _search_providers, _metadata_providers, _title_matcher, _session_factory
    _search_providers = search_providers
    _metadata_providers = metadata_providers
    _title_matcher = title_matcher
    _session_factory = session_factory


def get_search_providers():
    """Get search providers."""
    return _search_providers


def get_metadata_providers():
    """Get metadata providers."""
    return _metadata_providers


def get_title_matcher():
    """Get title matcher."""
    return _title_matcher


def get_session_factory():
    """Get session factory."""
    return _session_factory

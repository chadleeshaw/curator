"""
Shared dependencies and state for tracking routers.

This module contains global state and dependency injection for all tracking-related routers.
"""

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter


logger = logging.getLogger(__name__)

# Create the main router that all sub-routers will use
router = APIRouter(prefix="/api", tags=["tracking"])

# Global state (injected from main app)
_session_factory: Optional[Callable] = None
_search_providers: Optional[Any] = None
_auto_download_task_func: Optional[Any] = None
_storage_config: Optional[Dict[str, Any]] = None
_import_config: Optional[Dict[str, Any]] = None


def set_dependencies(
    session_factory: Callable,
    search_providers: Any,
    auto_download_task: Optional[Any] = None,
    storage_config: Optional[Dict[str, Any]] = None,
    import_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Set dependencies from main app.

    Args:
        session_factory: SQLAlchemy session factory
        search_providers: List of search provider instances
        auto_download_task: Optional auto-download task function
        storage_config: Storage configuration dict
        import_config: Import configuration dict
    """
    global _session_factory, _search_providers, _auto_download_task_func, _storage_config, _import_config
    _session_factory = session_factory
    _search_providers = search_providers
    _auto_download_task_func = auto_download_task
    _storage_config = storage_config or {}
    _import_config = import_config or {}


def get_search_providers() -> Optional[Any]:
    """Get the search providers."""
    return _search_providers

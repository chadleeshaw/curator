"""
Shared state and dependencies for downloads router
"""

import logging
from typing import Any, Callable

from fastapi import APIRouter


# Router instance
router = APIRouter(prefix="/api/downloads", tags=["downloads"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_download_manager = None
_download_client = None


def set_dependencies(session_factory: Callable, download_manager: Any, download_client: Any) -> None:
    """Set dependencies from main app"""
    global _session_factory, _download_manager, _download_client
    _session_factory = session_factory
    _download_manager = download_manager
    _download_client = download_client

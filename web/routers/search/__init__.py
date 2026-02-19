"""
Search router module.

Provides search functionality for periodicals across configured providers.
"""

from web.routers.search.dependencies import set_dependencies
from web.routers.search.endpoints import router

__all__ = ["router", "set_dependencies"]

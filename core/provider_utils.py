"""
Provider utilities.
Common error handling for search providers.
"""
import logging
from functools import wraps
from typing import Callable, List

from core.bases import SearchResult

logger = logging.getLogger(__name__)


def handle_provider_errors(func: Callable) -> Callable:
    """
    Decorator for provider search methods.
    Catches and logs errors, returns empty list on failure.

    Usage:
        @handle_provider_errors
        def search(self, query: str) -> List[SearchResult]:
            # Search implementation
            return results

    Args:
        func: The search function to wrap

    Returns:
        Wrapped function with error handling
    """
    @wraps(func)
    def wrapper(self, query: str) -> List[SearchResult]:
        try:
            results = func(self, query)
            logger.info(f"{self.name} found {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.error(f"{self.name} search error for '{query}': {e}")
            return []
    return wrapper

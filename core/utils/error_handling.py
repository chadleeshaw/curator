"""
Error handling utilities for API endpoints.
Provides decorators and helpers for consistent error handling across routers.
"""

import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def handle_api_errors(operation_name: str, logger: logging.Logger):
    """
    Decorator to handle API errors consistently.

    Catches all exceptions except HTTPException (which are re-raised as-is),
    logs them with context, and converts them to 500 HTTPExceptions.

    This eliminates the need for repetitive try/except blocks in every endpoint.

    Args:
        operation_name: Human-readable operation name for logging (e.g., "Get magazine")
        logger: Logger instance to use for error logging

    Returns:
        Decorated function with automatic error handling

    Usage:
        @router.get("/periodicals/{id}")
        @handle_api_errors("Get magazine", logger)
        async def get_magazine(id: int):
            # Your code here - no need for try/except
            return result

    Example with custom error messages:
        @router.delete("/periodicals/{id}")
        @handle_api_errors("Delete magazine", logger)
        async def delete_magazine(id: int):
            # HTTPExceptions are re-raised as-is
            if not found:
                raise HTTPException(status_code=404, detail="Not found")
            return {"success": True}
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTPExceptions as-is (they're already formatted)
                raise
            except Exception as e:
                # Log unexpected errors with full traceback
                logger.error(f"{operation_name} error: {e}", exc_info=True)
                # Convert to HTTPException for consistent API error format
                raise HTTPException(status_code=500, detail="An internal server error occurred")

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"{operation_name} error: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="An internal server error occurred")

        # Return appropriate wrapper based on whether function is async
        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

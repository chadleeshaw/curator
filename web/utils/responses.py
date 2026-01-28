"""
Response utilities for standardized API responses.

This module provides utilities for creating consistent response formats
across all API endpoints.
"""

from typing import Any, Dict, Optional


def success_response(message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Create a standard success response dictionary.

    Args:
        message: Optional success message
        **kwargs: Additional fields to include in the response

    Returns:
        Dictionary with success=True and any additional fields

    Example:
        >>> success_response("Operation completed")
        {'success': True, 'message': 'Operation completed'}

        >>> success_response("Deleted item", item_id=123, count=5)
        {'success': True, 'message': 'Deleted item', 'item_id': 123, 'count': 5}
    """
    response = {"success": True}

    if message:
        response["message"] = message

    response.update(kwargs)
    return response


def error_response(message: str, **kwargs) -> Dict[str, Any]:
    """
    Create a standard error response dictionary.

    Args:
        message: Error message
        **kwargs: Additional fields to include in the response

    Returns:
        Dictionary with success=False and error message

    Example:
        >>> error_response("Item not found")
        {'success': False, 'message': 'Item not found'}

        >>> error_response("Validation failed", errors=["field1", "field2"])
        {'success': False, 'message': 'Validation failed', 'errors': ['field1', 'field2']}
    """
    response = {"success": False, "message": message}
    response.update(kwargs)
    return response


def list_response(items: list, total: Optional[int] = None, **kwargs) -> Dict[str, Any]:
    """
    Create a standard list/collection response.

    Args:
        items: List of items to return
        total: Optional total count (useful for pagination)
        **kwargs: Additional fields to include in the response

    Returns:
        Dictionary with success=True, items list, and optional total

    Example:
        >>> list_response([{"id": 1}, {"id": 2}], total=100)
        {'success': True, 'items': [{'id': 1}, {'id': 2}], 'total': 100}

        >>> list_response(magazines, total=50, page=1, per_page=20)
        {'success': True, 'items': [...], 'total': 50, 'page': 1, 'per_page': 20}
    """
    response = {"success": True, "items": items}

    if total is not None:
        response["total"] = total

    response.update(kwargs)
    return response


def data_response(data: Any, message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Create a standard data response with arbitrary payload.

    Args:
        data: Data payload to return (can be dict, list, string, etc.)
        message: Optional message
        **kwargs: Additional fields to include in the response

    Returns:
        Dictionary with success=True and data payload

    Example:
        >>> data_response({"name": "Test", "value": 42})
        {'success': True, 'data': {'name': 'Test', 'value': 42}}

        >>> data_response(config_dict, message="Config loaded")
        {'success': True, 'data': {...}, 'message': 'Config loaded'}
    """
    response = {"success": True, "data": data}

    if message:
        response["message"] = message

    response.update(kwargs)
    return response


def paginated_response(items: list, page: int, per_page: int, total: int, **kwargs) -> Dict[str, Any]:
    """
    Create a standard paginated response.

    Args:
        items: List of items for this page
        page: Current page number (1-indexed)
        per_page: Number of items per page
        total: Total number of items across all pages
        **kwargs: Additional fields to include in the response

    Returns:
        Dictionary with pagination metadata

    Example:
        >>> paginated_response(magazines[0:20], page=1, per_page=20, total=100)
        {
            'success': True,
            'items': [...],
            'page': 1,
            'per_page': 20,
            'total': 100,
            'total_pages': 5,
            'has_next': True,
            'has_prev': False
        }
    """
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    response = {
        "success": True,
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    response.update(kwargs)
    return response


def status_response(status: str, message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Create a standard status response (for legacy compatibility).

    Some endpoints use "status" instead of "success". This function provides
    compatibility with that pattern.

    Args:
        status: Status string (e.g., "success", "error", "pending")
        message: Optional message
        **kwargs: Additional fields to include in the response

    Returns:
        Dictionary with status field

    Example:
        >>> status_response("success", "Operation completed")
        {'status': 'success', 'message': 'Operation completed'}
    """
    response = {"status": status}

    if message:
        response["message"] = message

    response.update(kwargs)
    return response

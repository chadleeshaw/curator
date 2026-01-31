"""
Unit tests for web/utils/responses.py
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from web.utils.responses import (
    data_response,
    error_response,
    list_response,
    paginated_response,
    status_response,
    success_response,
)


class TestSuccessResponse:
    """Test success_response function"""

    def test_simple_success(self):
        """Test simple success response"""
        result = success_response()
        assert result == {"success": True}

    def test_success_with_message(self):
        """Test success response with message"""
        result = success_response("Operation completed")
        assert result == {"success": True, "message": "Operation completed"}

    def test_success_with_extra_fields(self):
        """Test success response with additional fields"""
        result = success_response("Deleted item", item_id=123, count=5)
        assert result == {
            "success": True,
            "message": "Deleted item",
            "item_id": 123,
            "count": 5,
        }

    def test_success_without_message_but_with_fields(self):
        """Test success response with only extra fields"""
        result = success_response(user_id=456, role="admin")
        assert result == {"success": True, "user_id": 456, "role": "admin"}


class TestErrorResponse:
    """Test error_response function"""

    def test_simple_error(self):
        """Test simple error response"""
        result = error_response("Something went wrong")
        assert result == {"success": False, "message": "Something went wrong"}

    def test_error_with_extra_fields(self):
        """Test error response with additional fields"""
        result = error_response("Validation failed", errors=["field1", "field2"], code=400)
        assert result == {
            "success": False,
            "message": "Validation failed",
            "errors": ["field1", "field2"],
            "code": 400,
        }


class TestListResponse:
    """Test list_response function"""

    def test_simple_list(self):
        """Test simple list response"""
        items = [{"id": 1}, {"id": 2}]
        result = list_response(items)
        assert result == {"success": True, "items": items}

    def test_list_with_total(self):
        """Test list response with total count"""
        items = [{"id": 1}, {"id": 2}]
        result = list_response(items, total=100)
        assert result == {"success": True, "items": items, "total": 100}

    def test_list_with_extra_fields(self):
        """Test list response with additional pagination fields"""
        items = [{"id": 1}]
        result = list_response(items, total=50, page=1, per_page=20)
        assert result == {
            "success": True,
            "items": items,
            "total": 50,
            "page": 1,
            "per_page": 20,
        }

    def test_empty_list(self):
        """Test list response with empty list"""
        result = list_response([], total=0)
        assert result == {"success": True, "items": [], "total": 0}


class TestDataResponse:
    """Test data_response function"""

    def test_dict_data(self):
        """Test data response with dictionary"""
        data = {"name": "Test", "value": 42}
        result = data_response(data)
        assert result == {"success": True, "data": data}

    def test_data_with_message(self):
        """Test data response with message"""
        data = {"config": "value"}
        result = data_response(data, message="Config loaded")
        assert result == {"success": True, "data": data, "message": "Config loaded"}

    def test_string_data(self):
        """Test data response with string"""
        result = data_response("simple string")
        assert result == {"success": True, "data": "simple string"}

    def test_list_data(self):
        """Test data response with list"""
        data = [1, 2, 3]
        result = data_response(data)
        assert result == {"success": True, "data": data}

    def test_data_with_extra_fields(self):
        """Test data response with additional fields"""
        data = {"key": "value"}
        result = data_response(data, message="Success", metadata={"version": "1.0"})
        assert result == {
            "success": True,
            "data": data,
            "message": "Success",
            "metadata": {"version": "1.0"},
        }


class TestPaginatedResponse:
    """Test paginated_response function"""

    def test_first_page(self):
        """Test paginated response for first page"""
        items = [{"id": i} for i in range(20)]
        result = paginated_response(items, page=1, per_page=20, total=100)

        assert result["success"] is True
        assert result["items"] == items
        assert result["page"] == 1
        assert result["per_page"] == 20
        assert result["total"] == 100
        assert result["total_pages"] == 5
        assert result["has_next"] is True
        assert result["has_prev"] is False

    def test_middle_page(self):
        """Test paginated response for middle page"""
        items = [{"id": i} for i in range(20)]
        result = paginated_response(items, page=3, per_page=20, total=100)

        assert result["page"] == 3
        assert result["total_pages"] == 5
        assert result["has_next"] is True
        assert result["has_prev"] is True

    def test_last_page(self):
        """Test paginated response for last page"""
        items = [{"id": i} for i in range(20)]
        result = paginated_response(items, page=5, per_page=20, total=100)

        assert result["page"] == 5
        assert result["has_next"] is False
        assert result["has_prev"] is True

    def test_single_page(self):
        """Test paginated response with all items on one page"""
        items = [{"id": i} for i in range(10)]
        result = paginated_response(items, page=1, per_page=20, total=10)

        assert result["total_pages"] == 1
        assert result["has_next"] is False
        assert result["has_prev"] is False

    def test_partial_last_page(self):
        """Test paginated response with partial last page"""
        items = [{"id": i} for i in range(7)]
        result = paginated_response(items, page=3, per_page=20, total=47)

        assert result["total_pages"] == 3
        assert result["has_next"] is False
        assert result["has_prev"] is True

    def test_with_extra_fields(self):
        """Test paginated response with additional fields"""
        items = [{"id": 1}]
        result = paginated_response(items, page=1, per_page=20, total=100, filters={"active": True})

        assert result["filters"] == {"active": True}


class TestStatusResponse:
    """Test status_response function"""

    def test_success_status(self):
        """Test status response with success"""
        result = status_response("success")
        assert result == {"status": "success"}

    def test_error_status(self):
        """Test status response with error"""
        result = status_response("error", "Something failed")
        assert result == {"status": "error", "message": "Something failed"}

    def test_pending_status(self):
        """Test status response with pending status"""
        result = status_response("pending", "Processing...", job_id=789)
        assert result == {
            "status": "pending",
            "message": "Processing...",
            "job_id": 789,
        }

    def test_custom_status(self):
        """Test status response with custom status"""
        result = status_response("processing", task_id=123, progress=50)
        assert result == {"status": "processing", "task_id": 123, "progress": 50}

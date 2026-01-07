"""
Standardized response models for consistent API responses.
"""
from typing import Any, Dict, List, Optional


class ErrorDetail:
    """Details about an error."""
    
    def __init__(self, code: str, message: str, retryable: bool = False):
        """
        Initialize error detail.
        
        Args:
            code: Error code (e.g., 'DUPLICATE', 'TIMEOUT', 'VALIDATION_ERROR')
            message: Human-readable error message
            retryable: Whether the operation can be retried
        """
        self.code = code
        self.message = message
        self.retryable = retryable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


class OperationResult:
    """
    Standardized result for batch operations.
    
    Provides consistent structure for operations like imports, downloads, etc.
    """
    
    def __init__(self, success: bool = True):
        """
        Initialize operation result.
        
        Args:
            success: Whether the overall operation succeeded
        """
        self.success = success
        self.data: Dict[str, Any] = {}
        self.errors: List[ErrorDetail] = []
    
    def add_count(self, key: str, value: int):
        """Add a count to the data dictionary."""
        self.data[key] = value
    
    def add_error(self, code: str, message: str, retryable: bool = False):
        """Add an error."""
        self.errors.append(ErrorDetail(code, message, retryable))
        self.success = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "success": self.success,
            "data": self.data,
        }
        
        if self.errors:
            result["errors"] = [e.to_dict() for e in self.errors]
        
        return result


# Common error codes
class ErrorCodes:
    """Standard error codes used across the application."""
    
    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_URL = "INVALID_URL"
    INVALID_TITLE = "INVALID_TITLE"
    
    # Duplicate/conflict errors
    DUPLICATE = "DUPLICATE"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    
    # Network/timeout errors
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    
    # Client errors
    CLIENT_ERROR = "CLIENT_ERROR"
    CLIENT_REJECTED = "CLIENT_REJECTED"
    
    # File errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_READ_ERROR = "FILE_READ_ERROR"
    FILE_WRITE_ERROR = "FILE_WRITE_ERROR"
    
    # Database errors
    DATABASE_ERROR = "DATABASE_ERROR"
    
    # Import/processing errors
    IMPORT_FAILED = "IMPORT_FAILED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    
    # Generic errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

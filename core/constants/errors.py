"""
Centralized error message constants for API responses.

This module contains standardized error messages and error codes used across
the application to ensure consistency in API responses and error handling.
"""


class ErrorMessages:
    """Standard error messages for HTTP responses."""

    # 404 Not Found errors
    TRACKING_NOT_FOUND = "Tracking record not found"
    MAGAZINE_NOT_FOUND = "Magazine not found"
    PERIODICAL_NOT_FOUND = "Periodical not found"
    SUBMISSION_NOT_FOUND = "Submission not found"
    COVER_NOT_FOUND = "Cover not found"
    OCR_JOB_NOT_FOUND = "OCR job not found"
    DOWNLOAD_NOT_FOUND = "Download not found"
    IMPORT_JOB_NOT_FOUND = "Import job not found"

    # 503 Service Unavailable errors
    FILE_IMPORTER_UNAVAILABLE = "File importer not available"
    DOWNLOAD_MANAGER_UNAVAILABLE = "Download manager not available"
    SEARCH_PROVIDERS_UNAVAILABLE = "No search providers configured"

    # 400 Bad Request errors
    INVALID_REQUEST = "Invalid request"
    MISSING_REQUIRED_FIELD = "Missing required field"
    INVALID_FILE_PATH = "Invalid file path"

    # 500 Internal Server errors
    DATABASE_ERROR = "Database error occurred"
    FILE_OPERATION_ERROR = "File operation failed"


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

"""
Pydantic models for request and response validation
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ==============================================================================
# Standard API Responses
# ==============================================================================


class APIResponse(BaseModel):
    """Standard successful API response"""

    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class APIError(BaseModel):
    """Standard error response"""

    success: bool = False
    error: str = Field(..., description="Error type or category")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )


class ValidationErrorDetail(BaseModel):
    """Detailed validation error information"""

    field: str
    message: str
    value: Optional[Any] = None


class ValidationError(APIError):
    """Validation error response with field-level details"""

    error: str = "validation_error"
    validation_errors: List[ValidationErrorDetail] = Field(
        default_factory=list, description="List of validation errors"
    )


# ==============================================================================
# Authentication
# ==============================================================================


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str


class CreateCredentialsRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateUserRequest(BaseModel):
    """Request to update username and/or password"""

    current_password: str
    username: Optional[str] = None
    new_password: Optional[str] = None


# ==============================================================================
# Search
# ==============================================================================


class SearchRequest(BaseModel):
    query: str
    mode: str = "automatic"  # "automatic" or "manual"
    providers: Optional[List[str]] = None  # For manual mode


class SearchResultResponse(BaseModel):
    title: str
    url: str
    provider: str
    publication_date: Optional[str] = None
    raw_metadata: Dict[str, Any]
    match_score: Optional[int] = None


class MagazineSearchResponse(BaseModel):
    """Response from Open Library magazine search"""

    olid: str
    title: str
    publisher: Optional[str]
    first_publish_year: Optional[int]
    issn: Optional[str]
    isbn: Optional[str]
    edition_count: int


# ==============================================================================
# Magazines/Periodicals
# ==============================================================================


class MagazineResponse(BaseModel):
    id: int
    title: str
    publisher: Optional[str]
    language: Optional[str]
    issue_date: str
    file_path: str
    cover_path: Optional[str]
    metadata: Optional[Dict[str, Any]]


class EditionInfo(BaseModel):
    """Single edition of a magazine"""

    olid: str
    title: str
    publish_date: str
    publishers: List[str]
    isbn: Optional[str]
    issn: Optional[str]
    number_of_pages: Optional[int]
    physical_format: str
    language: str


class MagazineEditionsResponse(BaseModel):
    """Response with all editions of a magazine"""

    work_olid: str
    title: str
    description: Optional[str]
    first_publish_year: Optional[int]
    total_editions: int
    editions: List[Dict[str, Any]]


# ==============================================================================
# Tracking
# ==============================================================================


class TrackingPreferencesRequest(BaseModel):
    """Request to save tracking preferences for a magazine"""

    olid: str
    title: str
    publisher: Optional[str] = None
    issn: Optional[str] = None
    first_publish_year: Optional[int] = None
    track_all_editions: bool = False
    track_new_only: bool = False
    selected_editions: Dict[str, bool] = {}
    selected_years: List[int] = []
    metadata: Optional[Dict[str, Any]] = None


class TrackingPreferencesResponse(BaseModel):
    """Response with saved tracking preferences"""

    id: int
    olid: str
    title: str
    track_all_editions: bool
    selected_editions: Dict[str, bool]
    selected_years: List[int]


# ==============================================================================
# Downloads
# ==============================================================================


class DownloadAllIssuesRequest(BaseModel):
    """Request to download all issues of a tracked periodical"""

    tracking_id: int  # ID of the tracked periodical


class DownloadSingleIssueRequest(BaseModel):
    """Request to download a single issue"""

    tracking_id: int  # ID of the tracked periodical to associate with
    title: str  # Title of the issue
    url: str  # Download URL
    provider: Optional[str] = "manual"  # Source provider
    publication_date: Optional[str] = None  # Publication date if known


class DownloadSubmissionResponse(BaseModel):
    """Response for a download submission"""

    submission_id: int
    job_id: Optional[str]
    tracking_id: int
    title: str
    url: str
    status: str
    message: str


class DownloadStatusResponse(BaseModel):
    """Response for download status"""

    submission_id: int
    tracking_id: int
    title: str
    job_id: Optional[str]
    status: str
    progress: int
    file_path: Optional[str]
    error: Optional[str]
    created_at: str
    updated_at: str


# ==============================================================================
# Import
# ==============================================================================


class ImportOptionsRequest(BaseModel):
    """Request with import options"""

    category: Optional[str] = None  # None for auto-detect
    organization_pattern: Optional[str] = (
        "data/{category}/{title}/{year}/"  # File organization pattern with tags
    )
    auto_track: bool = True
    tracking_mode: str = "all"  # "all", "new", "watch", or "none"
    scan_nested: bool = True

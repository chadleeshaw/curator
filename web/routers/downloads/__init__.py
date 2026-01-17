"""
Download management routes package
"""

# Import shared module first to initialize router and state
from . import _shared

# Import all submodules to register their routes with the router
from . import submissions, status, queue, operations, failed

# Re-export the router and set_dependencies for backward compatibility
router = _shared.router
set_dependencies = _shared.set_dependencies

# Re-export all route functions
from .submissions import download_all_periodical_issues, download_single_issue
from .status import get_download_status_for_tracking, get_completed_downloads
from .queue import (
    get_download_queue_default,
    get_download_queue_all,
    get_download_queue_status,
)
from .operations import (
    retry_download,
    clear_pending_downloads,
    clear_failed_downloads,
    delete_from_queue,
    cleanup_old_submissions,
)
from .failed import get_failed_downloads, delete_failed_download

__all__ = [
    "router",
    "set_dependencies",
    "download_all_periodical_issues",
    "download_single_issue",
    "get_download_status_for_tracking",
    "get_completed_downloads",
    "get_download_queue_default",
    "get_download_queue_all",
    "get_download_queue_status",
    "retry_download",
    "clear_pending_downloads",
    "clear_failed_downloads",
    "delete_from_queue",
    "cleanup_old_submissions",
    "get_failed_downloads",
    "delete_failed_download",
]

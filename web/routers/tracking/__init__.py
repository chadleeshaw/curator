"""
Tracking routers package.

This package contains all tracking-related API routes, split by functionality:
- crud.py: Create, read, list, delete operations
- search.py: Search functionality for tracked periodicals
- preferences.py: Save and update tracking preferences
- merge.py: Merge multiple tracking records
- downloads.py: Track single issues for download
"""

from typing import Any, Callable, Dict, Optional

# Import the shared router and dependencies
from ._shared import router, set_dependencies

# Import all route modules to register their routes with the shared router
from . import crud, search, preferences, merge, downloads

# Import and re-export all route functions for backward compatibility
from .crud import (
    start_tracking_periodical,
    list_tracked_periodicals,
    list_tracked_magazines,
    get_tracking_details,
    delete_tracking,
)
from .search import search_tracked_periodical_issues
from .preferences import save_tracking_preferences, update_tracking
from .merge import merge_tracking, _reorganize_magazine_files
from .downloads import track_single_issue

# Re-export the router and set_dependencies for backward compatibility
__all__ = [
    "router",
    "set_dependencies",
    # CRUD functions
    "start_tracking_periodical",
    "list_tracked_periodicals",
    "list_tracked_magazines",
    "get_tracking_details",
    "delete_tracking",
    # Search functions
    "search_tracked_periodical_issues",
    # Preferences functions
    "save_tracking_preferences",
    "update_tracking",
    # Merge functions
    "merge_tracking",
    "_reorganize_magazine_files",
    # Download functions
    "track_single_issue",
]

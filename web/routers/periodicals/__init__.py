"""
Periodicals router package - library/periodicals management routes
"""

# Import shared state and router first
from ._shared import router, set_dependencies

# Import all submodules to register their routes

# Re-export all route functions for backward compatibility
from .crud import (
    list_periodicals,
    get_periodical,
    delete_periodical,
    purge_database,
    purge_cache,
    get_cache_stats,
    get_periodicals_count,
)

# Bulk routes must be registered before covers and files to avoid path parameter
# conflicts (/api/periodicals/bulk/... vs /api/periodicals/{periodical_id}/...)
from .bulk import (
    bulk_move_to_tracking,
    bulk_regenerate_thumbnail_ocr,
    bulk_delete,
)
from .covers import (
    get_cover,
    regenerate_cover,
    regenerate_thumbnail_ocr,
)
from .metadata import (
    toggle_special_edition,
    update_periodical,
)
from .files import (
    get_pdf,
    move_issue_to_tracking,
)
from .progress import (
    get_progress,
    update_progress,
    delete_progress,
)

__all__ = [
    # Core exports
    "router",
    "set_dependencies",
    # CRUD operations
    "list_periodicals",
    "get_periodical",
    "delete_periodical",
    "purge_database",
    "purge_cache",
    "get_cache_stats",
    "get_periodicals_count",
    # Cover operations
    "get_cover",
    "regenerate_cover",
    "regenerate_thumbnail_ocr",
    # Metadata operations
    "toggle_special_edition",
    "update_periodical",
    # File operations
    "get_pdf",
    "move_issue_to_tracking",
    # Bulk operations
    "bulk_move_to_tracking",
    "bulk_regenerate_thumbnail_ocr",
    "bulk_delete",
    # Progress operations
    "get_progress",
    "update_progress",
    "delete_progress",
]

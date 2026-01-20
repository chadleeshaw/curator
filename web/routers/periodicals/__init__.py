"""
Periodicals router package - library/periodicals management routes
"""

# Import shared state and router first
from ._shared import router, set_dependencies

# Import all submodules to register their routes

# Re-export all route functions for backward compatibility
from .crud import (
    list_periodicals,
    get_magazine,
    delete_periodical,
    purge_database,
    purge_cache,
    get_cache_stats,
    get_periodicals_count,
)
from .covers import (
    get_cover,
    regenerate_cover,
)
from .metadata import (
    toggle_special_edition,
    update_periodical,
)
from .files import (
    get_pdf,
    move_issue_to_tracking,
)

__all__ = [
    # Core exports
    "router",
    "set_dependencies",
    # CRUD operations
    "list_periodicals",
    "get_magazine",
    "delete_periodical",
    "purge_database",
    "purge_cache",
    "get_cache_stats",
    "get_periodicals_count",
    # Cover operations
    "get_cover",
    "regenerate_cover",
    # Metadata operations
    "toggle_special_edition",
    "update_periodical",
    # File operations
    "get_pdf",
    "move_issue_to_tracking",
]

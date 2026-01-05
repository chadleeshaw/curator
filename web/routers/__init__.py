"""
API routers for the Curator application
"""

from . import (
    auth,
    config,
    downloads,
    imports,
    pages,
    periodicals,
    search,
    tasks,
    tracking,
)

__all__ = [
    "auth",
    "search",
    "periodicals",
    "tracking",
    "downloads",
    "imports",
    "tasks",
    "config",
    "pages",
]

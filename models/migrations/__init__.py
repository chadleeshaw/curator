"""
Legacy manual migration system — superseded by Alembic.

This package is kept for historical reference only.  The database migration
system now uses Alembic (see alembic/ at the project root and core/database.py).
Nothing in the active codebase imports from this package.
"""

from .data import run_data_migrations
from .schema import COLUMN_ADDITIONS, COLUMN_RENAMES, COLUMN_REMOVALS, TABLE_REMOVALS

__all__ = [
    "COLUMN_ADDITIONS",
    "COLUMN_RENAMES",
    "COLUMN_REMOVALS",
    "TABLE_REMOVALS",
    "run_data_migrations",
]

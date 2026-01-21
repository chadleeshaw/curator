"""
Database migrations for Curator.

This package contains both schema migrations (automatic column additions/renames)
and data migrations (transforming existing data after schema changes).

Schema migrations are defined in schema.py and run automatically on startup.
Data migrations are defined in data.py and run after schema changes.
"""

from .data import run_data_migrations
from .schema import COLUMN_ADDITIONS, COLUMN_RENAMES

__all__ = ["COLUMN_ADDITIONS", "COLUMN_RENAMES", "run_data_migrations"]

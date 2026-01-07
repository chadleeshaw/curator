"""
Database utilities.
Provides consistent session management patterns.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session


@contextmanager
def get_db_session(session_factory) -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    Ensures proper session cleanup and error handling.

    Usage:
        with get_db_session(session_factory) as session:
            # Use session
            pass

    Args:
        session_factory: SQLAlchemy session factory

    Yields:
        Database session

    Note:
        Automatically commits on success and rolls back on error.
        Always closes the session in the finally block.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

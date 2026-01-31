"""
Database utilities.
Provides consistent session management patterns.
"""

from contextlib import contextmanager
from typing import Callable, Generator, TypeVar

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.utils.aasync import run_in_thread

T = TypeVar("T")


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


async def with_db_session(session_factory: Callable, operation: Callable[[Session], T]) -> T:
    """
    Execute database operation in a thread with automatic session cleanup.

    This utility simplifies the common pattern of:
    - Creating a database session
    - Running blocking database operations in a thread
    - Ensuring session is always closed

    Usage:
        return await with_db_session(
            _session_factory,
            lambda db: db.query(Periodical).filter(Periodical.id == id).first()
        )

    Args:
        session_factory: SQLAlchemy session factory callable
        operation: Function that takes a session and performs database operations

    Returns:
        Result of the operation

    Note:
        The session is NOT automatically committed. If you need to commit changes,
        call db.commit() within your operation function.
    """

    def _db_operation():
        db_session = session_factory()
        try:
            return operation(db_session)
        finally:
            db_session.close()

    return await run_in_thread(_db_operation)


def mark_json_modified(obj, *field_names: str) -> None:
    """
    Mark JSON fields as modified for SQLAlchemy change detection.

    SQLAlchemy doesn't automatically detect in-place modifications to JSON fields.
    This utility marks fields as modified so changes are persisted on commit.

    Usage:
        magazine.extra_metadata["category"] = "Technology"
        mark_json_modified(magazine, "extra_metadata")

        # Or mark multiple fields at once:
        mark_json_modified(magazine, "extra_metadata", "derived_metadata")

    Args:
        obj: SQLAlchemy model instance
        *field_names: Names of JSON fields to mark as modified
    """
    for field_name in field_names:
        flag_modified(obj, field_name)

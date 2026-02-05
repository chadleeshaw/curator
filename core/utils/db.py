"""
Database utilities.
Provides consistent session management patterns and retry logic for database locks.
"""

import logging
import time
from contextlib import contextmanager
from typing import Callable, Generator, TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.utils.aasync import run_in_thread

T = TypeVar("T")
logger = logging.getLogger(__name__)


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


def with_retry(operation: Callable[[], T], max_retries: int = 3, delay: float = 0.1) -> T:
    """
    Retry a database operation if it fails with OperationalError (database locked).

    This helps handle transient database lock issues by automatically retrying with
    exponential backoff. Useful for operations that may conflict with background tasks.

    Usage:
        def db_operation():
            session = session_factory()
            try:
                # Perform database operations
                session.add(obj)
                session.commit()
                return obj
            finally:
                session.close()

        result = with_retry(db_operation, max_retries=5, delay=0.1)

    Args:
        operation: Function to execute (takes no arguments)
        max_retries: Maximum number of retry attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 0.1)

    Returns:
        Result of the operation

    Raises:
        OperationalError: If all retries are exhausted
        Exception: Any other exception from the operation
    """
    last_error = None
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return operation()
        except OperationalError as e:
            last_error = e
            error_msg = str(e).lower()

            # Only retry on database lock errors
            if "database is locked" not in error_msg and "locked" not in error_msg:
                raise

            if attempt < max_retries:
                logger.warning(
                    f"Database locked, retrying in {current_delay:.2f}s (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(current_delay)
                current_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Database operation failed after {max_retries} retries")
                raise last_error

    # Should never reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected state in with_retry")


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


def check_file_path_conflict(db_session: Session, file_path: str, current_periodical_id: int) -> bool:
    """
    Check if a file path conflicts with an existing periodical in the database.

    This utility prevents UNIQUE constraint violations when moving or reorganizing files.
    Uses no_autoflush to avoid premature flush of pending changes.

    Usage:
        if check_file_path_conflict(db, str(new_path), magazine.id):
            logger.error(f"Path conflict: {new_path}")
            return False
        # Safe to update magazine.file_path

    Args:
        db_session: Database session
        file_path: Target file path to check
        current_periodical_id: ID of the periodical being moved (to exclude from check)

    Returns:
        True if conflict exists (path already used by different periodical), False otherwise
    """
    from models.database import Periodical

    with db_session.no_autoflush:
        existing_record = db_session.query(Periodical).filter_by(file_path=file_path).first()

    return existing_record is not None and existing_record.id != current_periodical_id

"""Helper utilities for running blocking operations asynchronously."""

import asyncio
from typing import Callable, TypeVar

T = TypeVar("T")


async def run_in_thread(func: Callable[[], T]) -> T:
    """
    Run a blocking operation in a thread pool to avoid blocking the event loop.

    This is useful for:
    - Database queries (SQLAlchemy synchronous sessions)
    - File I/O operations
    - CPU-intensive operations
    - External API calls (synchronous HTTP clients)

    Args:
        func: A callable that performs the blocking operation

    Returns:
        The result of the blocking operation

    Example:
        ```python
        async def get_periodicals():
            def _query():
                session = session_factory()
                try:
                    return session.query(Periodical).all()
                finally:
                    session.close()

            periodicals = await run_in_thread(_query)
            return periodicals
        ```
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func)

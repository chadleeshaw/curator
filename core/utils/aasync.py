"""Helper utilities for running blocking operations asynchronously."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")

# Shared bounded thread pool for background blocking tasks (DB queries, file I/O, network).
# 20 workers provides enough headroom for concurrent API requests and background tasks
# (feed sync, auto-download, download monitor) without starving the event loop.
# Each single-issue download submission holds a thread for several seconds (provider HTTP
# call + DB work), so a small pool (e.g. 5) saturates quickly under rapid manual submissions.
BACKGROUND_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=20)


async def run_in_thread(func: Callable[[], T]) -> T:
    """
    Run a blocking operation in the shared bounded thread pool.

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
    return await loop.run_in_executor(BACKGROUND_TASK_EXECUTOR, func)

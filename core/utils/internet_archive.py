"""
Internet Archive socket safety utilities.

The `internetarchive` library (v5.x) monkey-patches `socket.socket.connect`
every time an ArchiveSession is created (via search_items, get_item, configure, etc.).
If a session is reinitialized or multiple sessions are created, `_original_connect`
can point to an already-patched wrapper, causing infinite recursion on ANY socket
connection — including unrelated HTTP requests (e.g., Newsnab API calls).

This module provides a context manager that saves the real `socket.socket.connect`
before calling IA functions and restores it afterward, preventing the recursion bug.
"""

import socket
from contextlib import contextmanager

# Capture the REAL socket.connect before any internetarchive import can patch it.
# This must be imported before `from internetarchive import ...` in consuming modules.
_real_socket_connect = socket.socket.connect


@contextmanager
def safe_ia_call():
    """
    Context manager that restores socket.socket.connect after an internetarchive
    library call that may monkey-patch it.

    Usage:
        from core.utils.internet_archive import safe_ia_call

        with safe_ia_call():
            item = get_item(identifier)
    """
    try:
        yield
    finally:
        socket.socket.connect = _real_socket_connect  # type: ignore[method-assign]

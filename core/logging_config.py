"""
Structured logging configuration for Curator.

Sets up a consistent log format with timestamp, level, logger name, and message.
Provides a ContextLogger helper for adding per-request/per-operation context to log records.

Usage:
    from core.logging_config import configure_logging, get_context_logger

    # At startup:
    configure_logging(level="INFO", log_file="/path/to/app.log")

    # In services — adds structured context fields to every log line:
    logger = get_context_logger(__name__)
    with logger.context(periodical_id=42, tracking_id=7):
        logger.info("Starting download")   # => "... periodical_id=42 tracking_id=7 | Starting download"
"""

import logging
import os
import sys
from contextvars import ContextVar
from typing import Any, Dict, Optional

# Thread/async-local context storage — set this before logging a block of related operations.
_log_context: ContextVar[Dict[str, Any]] = ContextVar("_log_context", default={})


class ContextualFormatter(logging.Formatter):
    """
    Log formatter that appends structured key=value context fields to each message.

    Format:  %(asctime)s [%(levelname)-8s] %(name)s | %(message)s [field=value ...]
    """

    def format(self, record: logging.LogRecord) -> str:
        ctx = _log_context.get({})
        if ctx:
            context_str = " ".join(f"{k}={v}" for k, v in ctx.items())
            record.msg = f"{record.msg}  [{context_str}]"
        return super().format(record)


class ContextLogger:
    """
    Thin wrapper around a standard Logger that supports a context() context manager.

    Example:
        logger = get_context_logger(__name__)
        with logger.context(tracking_id=5, operation="auto_download"):
            logger.info("Searching for issues")   # includes tracking_id and operation in output
    """

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    # Delegate standard logging methods.
    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self._logger.exception(msg, *args, **kwargs)

    class _ContextManager:
        def __init__(self, fields: Dict[str, Any]):
            self._fields = fields
            self._token = None
            self._prev: Dict[str, Any] = {}

        def __enter__(self):
            current = _log_context.get({})
            merged = {**current, **self._fields}
            self._prev = current
            self._token = _log_context.set(merged)
            return self

        def __exit__(self, *_):
            _log_context.set(self._prev)

    def context(self, **fields: Any) -> "_ContextManager":
        """Return a context manager that adds structured fields to all log lines within the block."""
        return self._ContextManager(fields)


def get_context_logger(name: str) -> ContextLogger:
    """Get a ContextLogger for the given module name."""
    return ContextLogger(name)


def configure_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configure root logger with the Curator format.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path to write logs to in addition to stderr.
    """
    fmt = "%(asctime)s [%(levelname)-8s] %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    formatter = ContextualFormatter(fmt=fmt, datefmt=date_fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Guard against double-initialization (e.g. during test reloads).
    if root.handlers:
        root.handlers.clear()

    # Always write to stderr.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    # Optionally write to a file.
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as e:
            root.warning(f"Could not open log file {log_file}: {e} — logging to stderr only")

    # Suppress noisy third-party loggers.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)

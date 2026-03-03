#!/usr/bin/env python3
"""
Periodical Download Manager - Main Entry Point

Run this to start the web server and periodical manager.
"""

import sys
import logging
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent))

from core.config import ConfigLoader
from core.logging_config import configure_logging

# ==============================================================================
# Application Defaults
# ==============================================================================

DEFAULT_DB_PATH = "./local/config/periodicals.db"
DEFAULT_DOWNLOAD_DIR = "./local/downloads"
DEFAULT_LIBRARY_DIR = "./local/data"
DEFAULT_CACHE_DIR = "./local/cache"
DEFAULT_LOG_FILE = "./local/logs/periodical_manager.log"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8000


def _setup_directories(config_loader: ConfigLoader) -> Dict[str, Path]:
    """
    Set up required directories from configuration.

    ``config_loader.get_storage()`` already validates and creates all storage
    directories (db parent, downloads, library, cache).  The only directory that
    ``get_storage()`` does **not** create is the log directory, so this function
    is responsible solely for that.

    Args:
        config_loader: Configuration loader instance with storage and logging config

    Returns:
        Dictionary containing Path objects for all required directories:
        - db_path: Database file path
        - download_dir: Download staging directory
        - library_dir: Library periodicals directory
        - cache_dir: Application cache directory
        - log_file: Log file path
        - log_dir: Log directory path

    Raises:
        PermissionError: If unable to create directories due to permissions
        OSError: If directory creation fails for other reasons
    """
    storage_config = config_loader.get_storage()

    paths = {
        "db_path": Path(storage_config.get("db_path", DEFAULT_DB_PATH)),
        "download_dir": Path(storage_config.get("download_dir", DEFAULT_DOWNLOAD_DIR)),
        "library_dir": Path(storage_config.get("library_dir", DEFAULT_LIBRARY_DIR)),
        "cache_dir": Path(storage_config.get("cache_dir", DEFAULT_CACHE_DIR)),
    }

    log_file = config_loader.get_logging().get("log_file", DEFAULT_LOG_FILE)
    paths["log_file"] = Path(log_file)
    paths["log_dir"] = paths["log_file"].parent

    # Storage dirs are created by get_storage() → _validate_storage_paths().
    # Only the log directory needs explicit creation here.
    paths["log_dir"].mkdir(parents=True, exist_ok=True)

    return paths


def _setup_logging(log_file: Path, log_level: str) -> None:
    """
    Configure application logging with file and console handlers.

    Delegates to :func:`core.logging_config.configure_logging` which installs the
    structured :class:`~core.logging_config.ContextualFormatter` and suppresses noisy
    third-party loggers.

    Args:
        log_file: Path to log file (parent dir created by _setup_directories)
        log_level: Resolved log level string (e.g. "INFO", "DEBUG")
    """
    configure_logging(level=log_level, log_file=str(log_file))


def main():
    """
    Main application entry point.

    Initializes configuration, sets up directories and logging, imports the FastAPI
    app, and starts the uvicorn web server. Handles graceful shutdown on keyboard
    interrupt and logs fatal errors.

    The application lifecycle:
    1. Load configuration from YAML (with env var overrides)
    2. Create required directories (db, downloads, organize, cache, logs)
    3. Configure logging (file + console)
    4. Import FastAPI app (triggers dependency initialization)
    5. Start uvicorn server (blocks until shutdown)

    Exit codes:
        0: Clean shutdown via keyboard interrupt
        1: Fatal error during initialization or runtime

    Raises:
        SystemExit: On keyboard interrupt (exit code 0) or fatal error (exit code 1)
    """
    config_loader = ConfigLoader()
    paths = _setup_directories(config_loader)
    log_level = config_loader.get_logging().get("level", DEFAULT_LOG_LEVEL).upper()
    _setup_logging(paths["log_file"], log_level)

    logger = logging.getLogger(__name__)

    # Import app after logging is configured to ensure all app startup logs are captured
    # This triggers FastAPI initialization, database setup, and dependency injection
    from web.app import app

    try:
        import uvicorn

        logger.info("Starting Curator...")

        access_log = log_level == "DEBUG"

        server_config = config_loader.get_server()
        host = server_config.get("host", DEFAULT_SERVER_HOST)
        port = server_config.get("port", DEFAULT_SERVER_PORT)

        logger.info(f"Access the web UI at: http://localhost:{port}")

        uvicorn.run(
            app,
            host=host,
            port=port,
            access_log=access_log,
            timeout_keep_alive=5,  # Reduce keep-alive timeout to prevent stale connections
            timeout_graceful_shutdown=10,  # Allow 10s for graceful shutdown
        )

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

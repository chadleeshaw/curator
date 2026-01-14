#!/usr/bin/env python3
"""
Periodical Download Manager - Main Entry Point

Run this to start the web server and periodical manager.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from core.config import ConfigLoader

# ==============================================================================
# Application Defaults
# ==============================================================================

DEFAULT_DB_PATH = "./local/config/periodicals.db"
DEFAULT_DOWNLOAD_DIR = "./local/downloads"
DEFAULT_ORGANIZE_DIR = "./local/data"
DEFAULT_CACHE_DIR = "./local/cache"
DEFAULT_LOG_FILE = "./local/logs/periodical_manager.log"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8000
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _setup_directories(config_loader: ConfigLoader) -> Dict[str, Path]:
    """
    Set up required directories from configuration.

    Creates all necessary application directories (database, downloads, organized files,
    cache, logs) based on configuration with fallback to defaults. Ensures parent
    directories exist before application startup.

    Args:
        config_loader: Configuration loader instance with storage and logging config

    Returns:
        Dictionary containing Path objects for all required directories:
        - db_path: Database file path
        - download_dir: Download staging directory
        - organize_dir: Organized periodicals directory
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
        "organize_dir": Path(storage_config.get("organize_dir", DEFAULT_ORGANIZE_DIR)),
        "cache_dir": Path(storage_config.get("cache_dir", DEFAULT_CACHE_DIR)),
    }

    log_file = config_loader.get_logging().get("log_file", DEFAULT_LOG_FILE)
    paths["log_file"] = Path(log_file)
    paths["log_dir"] = paths["log_file"].parent

    # Create all required directories
    for directory in [
        paths["db_path"].parent,
        paths["download_dir"],
        paths["organize_dir"],
        paths["cache_dir"],
        paths["log_dir"],
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    return paths


def _setup_logging(config_loader: ConfigLoader, log_file: Path) -> None:
    """
    Configure application logging with file and console handlers.

    Sets up Python logging with INFO level by default, configurable via config.
    Logs are written to both the specified file and console (stdout) for
    monitoring during development and production.

    Args:
        config_loader: Configuration loader instance
        log_file: Path to log file (must exist, parent dir created by _setup_directories)

    Raises:
        PermissionError: If log file cannot be written due to permissions
        OSError: If log file cannot be created
    """
    log_config = config_loader.get_logging()
    log_level = log_config.get("level", DEFAULT_LOG_LEVEL).upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=LOG_FORMAT,
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )


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
    # Initialize configuration and setup
    config_loader = ConfigLoader()
    paths = _setup_directories(config_loader)
    _setup_logging(config_loader, paths["log_file"])

    logger = logging.getLogger(__name__)

    # Import app after logging is configured to ensure all app startup logs are captured
    # This triggers FastAPI initialization, database setup, and dependency injection
    from web.app import app

    try:
        import uvicorn

        logger.info("Starting Curator...")
        logger.info("Access the web UI at: http://localhost:8000")

        # Enable uvicorn access logs only if DEBUG logging is enabled
        # This reduces log noise in production while keeping detailed logs in development
        log_config = config_loader.get_logging()
        log_level = log_config.get("level", DEFAULT_LOG_LEVEL).upper()
        access_log = log_level == "DEBUG"

        # Get server configuration with environment variable override support
        server_config = config_loader.get_server()
        host = server_config.get("host", DEFAULT_SERVER_HOST)
        port = server_config.get("port", DEFAULT_SERVER_PORT)

        # Start the ASGI server (blocks until shutdown signal received)
        uvicorn.run(app, host=host, port=port, access_log=access_log)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

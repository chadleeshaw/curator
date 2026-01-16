import logging
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

# ==============================================================================
# Configuration Keys
# ==============================================================================

CONFIG_KEY_SEARCH_PROVIDERS = "search_providers"
CONFIG_KEY_METADATA_PROVIDERS = "metadata_providers"
CONFIG_KEY_DOWNLOAD_CLIENT = "download_client"
CONFIG_KEY_STORAGE = "storage"
CONFIG_KEY_MATCHING = "matching"
CONFIG_KEY_IMPORT = "import"
CONFIG_KEY_PDF = "pdf"
CONFIG_KEY_DOWNLOADS = "downloads"
CONFIG_KEY_TASKS = "tasks"
CONFIG_KEY_LOGGING = "logging"
CONFIG_KEY_SERVER = "server"
CONFIG_KEY_OCR = "ocr"
CONFIG_KEY_JWT_SECRET = "jwt_secret"

# Storage Keys
STORAGE_KEY_DB_PATH = "db_path"
STORAGE_KEY_DOWNLOAD_DIR = "download_dir"
STORAGE_KEY_ORGANIZE_DIR = "organize_dir"
STORAGE_KEY_CACHE_DIR = "cache_dir"

# Environment Variable Names
ENV_CURATOR_CONFIG_PATH = "CURATOR_CONFIG_PATH"
ENV_CURATOR_DB_PATH = "CURATOR_DB_PATH"
ENV_CURATOR_DOWNLOAD_DIR = "CURATOR_DOWNLOAD_DIR"
ENV_CURATOR_ORGANIZE_DIR = "CURATOR_ORGANIZE_DIR"
ENV_CURATOR_CACHE_DIR = "CURATOR_CACHE_DIR"
ENV_CURATOR_LOG_FILE = "CURATOR_LOG_FILE"
ENV_CURATOR_LOG_LEVEL = "CURATOR_LOG_LEVEL"
ENV_CURATOR_HOST = "CURATOR_HOST"
ENV_CURATOR_PORT = "CURATOR_PORT"
ENV_CURATOR_DRY_RUN = "CURATOR_DRY_RUN"  # Set to "true" to enable dry run for reorganization (default: false)

# Default Values
DEFAULT_CONFIG_PATH = "local/config/config.yaml"
DEFAULT_TEST_CONFIG_PATH = "tests/config.test.yaml"
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8000
DEFAULT_LOG_LEVEL = "INFO"


def _validate_directory(dir_path: Path, dir_name: str) -> None:
    """
    Validate and create a directory path with write permission check.

    Creates the directory (including parents) if it doesn't exist, then validates
    that it's actually a directory (not a file) and has write permissions. This
    ensures storage locations are usable before application startup.

    Args:
        dir_path: Path to validate and create
        dir_name: Human-readable name for error messages (e.g., "download_dir")

    Raises:
        ValueError: If path exists but is not a directory, or is not writable
        PermissionError: If directory creation fails due to insufficient permissions

    Examples:
        >>> _validate_directory(Path("/tmp/downloads"), "download_dir")
        # Creates /tmp/downloads if needed and validates write access
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        if not dir_path.is_dir():
            raise ValueError(f"{dir_name} path exists but is not a directory: {dir_path}")
        if not os.access(dir_path, os.W_OK):
            raise ValueError(f"{dir_name} directory is not writable: {dir_path}")
        logger.debug(f"Validated {dir_name}: {dir_path}")
    except PermissionError as e:
        raise ValueError(f"Permission denied creating {dir_name} directory: {dir_path}") from e


def _validate_database_path(db_path: Path) -> None:
    """
    Validate database path by ensuring parent directory exists and is writable.

    Args:
        db_path: Path to database file

    Raises:
        ValueError: If database directory is not writable
        PermissionError: If directory creation fails due to permissions
    """
    db_dir = db_path.parent
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(db_dir, os.W_OK):
            raise ValueError(f"Database directory is not writable: {db_dir}")
        logger.debug(f"Validated db_path: {db_path}")
    except PermissionError as e:
        raise ValueError(f"Permission denied creating database directory: {db_dir}") from e


def _apply_storage_env_overrides(storage: Dict[str, Any]) -> None:
    """
    Apply environment variable overrides to storage configuration.

    Environment variables take precedence over YAML config for deployment flexibility.
    This allows Docker containers, systemd services, or CI/CD to override paths
    without modifying config files.

    Args:
        storage: Storage configuration dictionary (modified in place)
    """
    # Override each storage path if corresponding environment variable is set
    # Pattern: CURATOR_<KEY> overrides config.<key>
    if os.environ.get(ENV_CURATOR_DB_PATH):
        storage[STORAGE_KEY_DB_PATH] = os.environ[ENV_CURATOR_DB_PATH]
    if os.environ.get(ENV_CURATOR_DOWNLOAD_DIR):
        storage[STORAGE_KEY_DOWNLOAD_DIR] = os.environ[ENV_CURATOR_DOWNLOAD_DIR]
    if os.environ.get(ENV_CURATOR_ORGANIZE_DIR):
        storage[STORAGE_KEY_ORGANIZE_DIR] = os.environ[ENV_CURATOR_ORGANIZE_DIR]
    if os.environ.get(ENV_CURATOR_CACHE_DIR):
        storage[STORAGE_KEY_CACHE_DIR] = os.environ[ENV_CURATOR_CACHE_DIR]


def _validate_storage_paths(storage: Dict[str, Any]) -> None:
    """
    Validate all storage paths in configuration.

    Args:
        storage: Storage configuration dictionary

    Raises:
        ValueError: If any path is invalid or not writable
    """
    # Validate directories
    for key in [
        STORAGE_KEY_DOWNLOAD_DIR,
        STORAGE_KEY_ORGANIZE_DIR,
        STORAGE_KEY_CACHE_DIR,
    ]:
        if key in storage:
            dir_path = Path(storage[key])
            _validate_directory(dir_path, key)

    # Validate database path
    if STORAGE_KEY_DB_PATH in storage:
        db_path = Path(storage[STORAGE_KEY_DB_PATH])
        _validate_database_path(db_path)


class ConfigLoader:
    """Load, validate, and save configuration from YAML"""

    def get_ocr(self) -> Dict[str, Any]:
        """Get OCR/image preprocessing configuration"""
        from core.constants.ocr import (
            OCR_RESIZE_WIDTH,
            OCR_CONTRAST_ENHANCE,
            OCR_DENOISE_H,
            OCR_SHARPEN_KERNEL,
        )

        return self.config.get(
            CONFIG_KEY_OCR,
            {
                "resize_width": OCR_RESIZE_WIDTH,
                "contrast_enhance": OCR_CONTRAST_ENHANCE,
                "denoise_h": OCR_DENOISE_H,
                "sharpen_kernel": OCR_SHARPEN_KERNEL,
            },
        )

    def __init__(self, config_path: str = None):
        # Allow environment variable to override, fall back to local dev path
        if config_path is None:
            config_path = os.environ.get(ENV_CURATOR_CONFIG_PATH, DEFAULT_CONFIG_PATH)
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load config from YAML file"""
        if not self.config_path.exists():
            # Try test config as fallback (for CI/CD environments)
            test_config_path = Path(DEFAULT_TEST_CONFIG_PATH)
            if test_config_path.exists():
                logger.warning(
                    f"Config file not found at {self.config_path}, " f"using test config: {test_config_path}"
                )
                self.config_path = test_config_path
            else:
                raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("Config file is empty")

        logger.debug(f"Loaded config from {self.config_path}")
        return config

    def get_search_providers(self) -> List[Dict[str, Any]]:
        """Get enabled search providers (for finding and downloading issues)"""
        providers = self.config.get(CONFIG_KEY_SEARCH_PROVIDERS, [])
        return [p for p in providers if p.get("enabled", True)]

    def get_metadata_providers(self) -> List[Dict[str, Any]]:
        """Get enabled metadata providers (for periodical information)"""
        providers = self.config.get(CONFIG_KEY_METADATA_PROVIDERS, [])
        return [p for p in providers if p.get("enabled", True)]

    def get_download_client(self) -> Dict[str, Any]:
        """Get configured download client"""
        client = self.config.get(CONFIG_KEY_DOWNLOAD_CLIENT, {})
        if not client:
            raise ValueError("No download client configured")
        return client

    def get_storage(self) -> Dict[str, Any]:
        """Get storage configuration with environment variable overrides and validation"""
        storage = self.config.get(CONFIG_KEY_STORAGE, {}).copy()

        # Apply environment variable overrides
        _apply_storage_env_overrides(storage)

        # Validate all paths
        _validate_storage_paths(storage)

        return storage

    def get_matching(self) -> Dict[str, Any]:
        """Get matching configuration"""
        from core.constants.app import DEFAULT_FUZZY_THRESHOLD
        from core.constants.date import DUPLICATE_DATE_THRESHOLD_DAYS

        return self.config.get(
            CONFIG_KEY_MATCHING,
            {
                "fuzzy_threshold": DEFAULT_FUZZY_THRESHOLD,
                "duplicate_date_threshold_days": DUPLICATE_DATE_THRESHOLD_DAYS,
            },
        )

        return self.config.get(
            CONFIG_KEY_MATCHING,
            {
                "fuzzy_threshold": DEFAULT_FUZZY_THRESHOLD,
                "duplicate_date_threshold_days": DUPLICATE_DATE_THRESHOLD_DAYS,
            },
        )

    def get_import(self) -> Dict[str, Any]:
        """Get import configuration"""
        return self.config.get(
            CONFIG_KEY_IMPORT,
            {
                "organization_pattern": None,
                "auto_track_imports": True,
                "category_prefix": "_",
                "enable_text_scan": True,
                "enable_ocr": True,
            },
        )

    def get_pdf(self) -> Dict[str, Any]:
        """Get PDF processing configuration"""
        from core.constants.files import (
            PDF_COVER_DPI_LOW,
            PDF_COVER_DPI_HIGH,
            PDF_COVER_QUALITY,
            PDF_COVER_QUALITY_HIGH,
        )

        return self.config.get(
            CONFIG_KEY_PDF,
            {
                "cover_dpi_low": PDF_COVER_DPI_LOW,
                "cover_dpi_high": PDF_COVER_DPI_HIGH,
                "cover_quality_low": PDF_COVER_QUALITY,
                "cover_quality_high": PDF_COVER_QUALITY_HIGH,
            },
        )

    def get_downloads(self) -> Dict[str, Any]:
        """Get downloads configuration"""
        from core.constants.app import MAX_DOWNLOAD_RETRIES, MAX_DOWNLOADS

        return self.config.get(
            CONFIG_KEY_DOWNLOADS,
            {
                "max_retries": MAX_DOWNLOAD_RETRIES,
                "max_per_batch": MAX_DOWNLOADS,
            },
        )

    def get_tasks(self) -> Dict[str, Any]:
        """Get task scheduling configuration"""
        from core.constants.app import (
            AUTO_DOWNLOAD_INTERVAL,
            DOWNLOAD_MONITOR_INTERVAL,
            CLEANUP_COVERS_INTERVAL,
        )

        return self.config.get(
            CONFIG_KEY_TASKS,
            {
                "auto_download_interval": AUTO_DOWNLOAD_INTERVAL,
                "download_monitor_interval": DOWNLOAD_MONITOR_INTERVAL,
                "cleanup_covers_interval": CLEANUP_COVERS_INTERVAL,
            },
        )

    def get_logging(self) -> Dict[str, Any]:
        """Get logging configuration with environment variable overrides"""
        logging_config = self.config.get(CONFIG_KEY_LOGGING, {"level": DEFAULT_LOG_LEVEL}).copy()

        # Environment variables override YAML config
        if os.environ.get(ENV_CURATOR_LOG_FILE):
            logging_config["log_file"] = os.environ[ENV_CURATOR_LOG_FILE]
        if os.environ.get(ENV_CURATOR_LOG_LEVEL):
            logging_config["level"] = os.environ[ENV_CURATOR_LOG_LEVEL]

        return logging_config

    def get_all_config(self) -> Dict[str, Any]:
        """Get entire configuration"""
        return self.config

    def get_jwt_secret(self) -> str:
        """Get or generate JWT secret key"""
        if CONFIG_KEY_JWT_SECRET not in self.config:
            # Generate new secret and save it
            self.config[CONFIG_KEY_JWT_SECRET] = secrets.token_urlsafe(32)
            self.save_config(self.config)
            logger.info("Generated and saved new JWT secret")
        return self.config[CONFIG_KEY_JWT_SECRET]

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to YAML file"""
        try:
            with open(self.config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            self.config = config
            logger.info(f"Saved config to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

    def get_server(self) -> Dict[str, Any]:
        """Get server configuration with environment variable overrides"""
        server = self.config.get(
            CONFIG_KEY_SERVER,
            {"host": DEFAULT_SERVER_HOST, "port": DEFAULT_SERVER_PORT},
        ).copy()

        # Environment variables override YAML config
        if os.environ.get(ENV_CURATOR_HOST):
            server["host"] = os.environ[ENV_CURATOR_HOST]
        if os.environ.get(ENV_CURATOR_PORT):
            server["port"] = int(os.environ[ENV_CURATOR_PORT])

        return server

    def reload_config(self) -> None:
        """Reload config from file"""
        self.config = self._load_config()
        logger.debug("Reloaded config from file")

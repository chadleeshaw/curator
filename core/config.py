import logging
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

class ConfigLoader:
    """Load, validate, and save configuration from YAML"""

    def get_ocr(self) -> Dict[str, Any]:
        """Get OCR/image preprocessing configuration"""
        from core.constants import (
            OCR_RESIZE_WIDTH,
            OCR_CONTRAST_ENHANCE,
            OCR_DENOISE_H,
            OCR_SHARPEN_KERNEL
        )
        return self.config.get("ocr", {
            "resize_width": OCR_RESIZE_WIDTH,
            "contrast_enhance": OCR_CONTRAST_ENHANCE,
            "denoise_h": OCR_DENOISE_H,
            "sharpen_kernel": OCR_SHARPEN_KERNEL
        })

    def __init__(self, config_path: str = None):
        # Allow environment variable to override, fall back to local dev path
        if config_path is None:
            config_path = os.environ.get(
                "CURATOR_CONFIG_PATH", "local/config/config.yaml"
            )
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load config from YAML file"""
        if not self.config_path.exists():
            # Try test config as fallback (for CI/CD environments)
            test_config_path = Path("tests/config.test.yaml")
            if test_config_path.exists():
                logger.warning(
                    f"Config file not found at {self.config_path}, "
                    f"using test config: {test_config_path}"
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
        providers = self.config.get("search_providers", [])
        return [p for p in providers if p.get("enabled", True)]

    def get_metadata_providers(self) -> List[Dict[str, Any]]:
        """Get enabled metadata providers (for periodical information)"""
        providers = self.config.get("metadata_providers", [])
        return [p for p in providers if p.get("enabled", True)]

    def get_download_client(self) -> Dict[str, Any]:
        """Get configured download client"""
        client = self.config.get("download_client", {})
        if not client:
            raise ValueError("No download client configured")
        return client

    def get_storage(self) -> Dict[str, Any]:
        """Get storage configuration with environment variable overrides and validation"""
        storage = self.config.get("storage", {}).copy()

        # Environment variables override YAML config
        if os.environ.get("CURATOR_DB_PATH"):
            storage["db_path"] = os.environ["CURATOR_DB_PATH"]
        if os.environ.get("CURATOR_DOWNLOAD_DIR"):
            storage["download_dir"] = os.environ["CURATOR_DOWNLOAD_DIR"]
        if os.environ.get("CURATOR_ORGANIZE_DIR"):
            storage["organize_dir"] = os.environ["CURATOR_ORGANIZE_DIR"]
        if os.environ.get("CURATOR_CACHE_DIR"):
            storage["cache_dir"] = os.environ["CURATOR_CACHE_DIR"]

        # Validate and create directories
        for key in ["download_dir", "organize_dir", "cache_dir"]:
            if key in storage:
                dir_path = Path(storage[key])
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    if not dir_path.is_dir():
                        raise ValueError(
                            f"{key} path exists but is not a directory: {dir_path}"
                        )
                    if not os.access(dir_path, os.W_OK):
                        raise ValueError(f"{key} directory is not writable: {dir_path}")
                    logger.debug(f"Validated {key}: {dir_path}")
                except PermissionError as e:
                    raise ValueError(
                        f"Permission denied creating {key} directory: {dir_path}"
                    ) from e

        # Validate database path
        if "db_path" in storage:
            db_path = Path(storage["db_path"])
            db_dir = db_path.parent
            try:
                db_dir.mkdir(parents=True, exist_ok=True)
                if not os.access(db_dir, os.W_OK):
                    raise ValueError(f"Database directory is not writable: {db_dir}")
                logger.debug(f"Validated db_path: {db_path}")
            except PermissionError as e:
                raise ValueError(
                    f"Permission denied creating database directory: {db_dir}"
                ) from e

        return storage

    def get_matching(self) -> Dict[str, Any]:
        """Get matching configuration"""
        from core.constants import DEFAULT_FUZZY_THRESHOLD, DUPLICATE_DATE_THRESHOLD_DAYS
        return self.config.get("matching", {
            "fuzzy_threshold": DEFAULT_FUZZY_THRESHOLD,
            "duplicate_date_threshold_days": DUPLICATE_DATE_THRESHOLD_DAYS
        })

    def get_import(self) -> Dict[str, Any]:
        """Get import configuration"""
        return self.config.get("import", {
            "organization_pattern": None,
            "auto_track_imports": True,
            "category_prefix": "_"
        })

    def get_pdf(self) -> Dict[str, Any]:
        """Get PDF processing configuration"""
        from core.constants import (
            PDF_COVER_DPI_LOW,
            PDF_COVER_DPI_HIGH,
            PDF_COVER_QUALITY,
            PDF_COVER_QUALITY_HIGH
        )
        return self.config.get("pdf", {
            "cover_dpi_low": PDF_COVER_DPI_LOW,
            "cover_dpi_high": PDF_COVER_DPI_HIGH,
            "cover_quality_low": PDF_COVER_QUALITY,
            "cover_quality_high": PDF_COVER_QUALITY_HIGH
        })

    def get_downloads(self) -> Dict[str, Any]:
        """Get downloads configuration"""
        from core.constants import MAX_DOWNLOAD_RETRIES, MAX_DOWNLOADS_PER_BATCH
        return self.config.get("downloads", {
            "max_retries": MAX_DOWNLOAD_RETRIES,
            "max_per_batch": MAX_DOWNLOADS_PER_BATCH
        })

    def get_tasks(self) -> Dict[str, Any]:
        """Get task scheduling configuration"""
        from core.constants import (
            AUTO_DOWNLOAD_INTERVAL,
            DOWNLOAD_MONITOR_INTERVAL,
            CLEANUP_COVERS_INTERVAL
        )
        return self.config.get("tasks", {
            "auto_download_interval": AUTO_DOWNLOAD_INTERVAL,
            "download_monitor_interval": DOWNLOAD_MONITOR_INTERVAL,
            "cleanup_covers_interval": CLEANUP_COVERS_INTERVAL
        })

    def get_logging(self) -> Dict[str, Any]:
        """Get logging configuration with environment variable overrides"""
        logging_config = self.config.get("logging", {"level": "INFO"}).copy()

        # Environment variables override YAML config
        if os.environ.get("CURATOR_LOG_FILE"):
            logging_config["log_file"] = os.environ["CURATOR_LOG_FILE"]
        if os.environ.get("CURATOR_LOG_LEVEL"):
            logging_config["level"] = os.environ["CURATOR_LOG_LEVEL"]

        return logging_config

    def get_all_config(self) -> Dict[str, Any]:
        """Get entire configuration"""
        return self.config

    def get_jwt_secret(self) -> str:
        """Get or generate JWT secret key"""
        if "jwt_secret" not in self.config:
            # Generate new secret and save it
            self.config["jwt_secret"] = secrets.token_urlsafe(32)
            self.save_config(self.config)
            logger.info("Generated and saved new JWT secret")
        return self.config["jwt_secret"]

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
        server = self.config.get("server", {"host": "0.0.0.0", "port": 8000}).copy()

        # Environment variables override YAML config
        if os.environ.get("CURATOR_HOST"):
            server["host"] = os.environ["CURATOR_HOST"]
        if os.environ.get("CURATOR_PORT"):
            server["port"] = int(os.environ["CURATOR_PORT"])

        return server

    def reload_config(self) -> None:
        """Reload config from file"""
        self.config = self._load_config()
        logger.debug("Reloaded config from file")

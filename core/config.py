import logging
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load, validate, and save configuration from YAML"""

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

        logger.info(f"Loaded config from {self.config_path}")
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
        return self.config.get("matching", {"fuzzy_threshold": 80})

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
        logger.info("Reloaded config from file")

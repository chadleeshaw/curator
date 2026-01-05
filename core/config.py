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
            config_path = os.environ.get("CURATOR_CONFIG_PATH", "local/config/config.yaml")
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load config from YAML file"""
        if not self.config_path.exists():
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
        """Get storage configuration"""
        return self.config.get("storage", {})

    def get_matching(self) -> Dict[str, Any]:
        """Get matching configuration"""
        return self.config.get("matching", {"fuzzy_threshold": 80})

    def get_logging(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self.config.get("logging", {"level": "INFO"})

    def get_all_config(self) -> Dict[str, Any]:
        """Get entire configuration"""
        return self.config

    def get_jwt_secret(self) -> str:
        """Get or generate JWT secret key"""
        if 'jwt_secret' not in self.config:
            # Generate new secret and save it
            self.config['jwt_secret'] = secrets.token_urlsafe(32)
            self.save_config(self.config)
            logger.info("Generated and saved new JWT secret")
        return self.config['jwt_secret']

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

    def reload_config(self) -> None:
        """Reload config from file"""
        self.config = self._load_config()
        logger.info("Reloaded config from file")

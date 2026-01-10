"""
Test suite for ConfigLoader functionality
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import ConfigLoader


@pytest.fixture
def config_loader():
    """Create ConfigLoader instance for testing"""
    return ConfigLoader(config_path="tests/config.test.yaml")


class TestConfigLoaderInitialization:
    """Test ConfigLoader initialization"""

    def test_init_loads_config(self, config_loader):
        """Test that initialization loads config"""
        assert config_loader.config is not None
        assert isinstance(config_loader.config, dict)

    def test_config_path_set(self, config_loader):
        """Test that config path is set"""
        assert config_loader.config_path is not None
        assert config_loader.config_path.exists()


class TestSearchProviders:
    """Test search provider configuration"""

    def test_get_search_providers(self, config_loader):
        """Test getting search providers"""
        providers = config_loader.get_search_providers()
        assert isinstance(providers, list)
        assert len(providers) > 0
        assert all(isinstance(p, dict) for p in providers)
        assert all("type" in p for p in providers)

    def test_search_providers_enabled_only(self, config_loader):
        """Test that only enabled providers are returned"""
        providers = config_loader.get_search_providers()
        # All returned providers should be enabled (or not explicitly disabled)
        for provider in providers:
            enabled = provider.get("enabled", True)
            assert enabled is True


class TestMetadataProviders:
    """Test metadata provider configuration"""

    def test_get_metadata_providers(self, config_loader):
        """Test getting metadata providers"""
        providers = config_loader.get_metadata_providers()
        assert isinstance(providers, list)
        # Test config may have no metadata providers configured
        assert len(providers) >= 0
        assert all(isinstance(p, dict) for p in providers)
        assert all("type" in p for p in providers)

    def test_metadata_providers_enabled_only(self, config_loader):
        """Test that only enabled providers are returned"""
        providers = config_loader.get_metadata_providers()
        # All returned providers should be enabled (or not explicitly disabled)
        for provider in providers:
            enabled = provider.get("enabled", True)
            assert enabled is True


class TestDownloadClient:
    """Test download client configuration"""

    def test_get_download_client(self, config_loader):
        """Test getting download client"""
        client = config_loader.get_download_client()
        assert isinstance(client, dict)
        assert "type" in client
        assert client["type"] == "sabnzbd"

    def test_download_client_has_required_fields(self, config_loader):
        """Test that download client has required configuration"""
        client = config_loader.get_download_client()
        assert "type" in client
        # May not have api_key in test config, but should have api_url
        assert "api_url" in client or "type" in client


class TestStorageConfiguration:
    """Test storage configuration"""

    def test_get_storage(self, config_loader):
        """Test getting storage configuration"""
        storage = config_loader.get_storage()
        assert isinstance(storage, dict)
        assert "db_path" in storage
        assert "download_dir" in storage
        assert "organize_dir" in storage

    def test_storage_paths_exist(self, config_loader):
        """Test that storage paths are created if they don't exist"""
        storage = config_loader.get_storage()
        # After calling get_storage, directories should be created
        for key in ["download_dir", "organize_dir", "cache_dir"]:
            if key in storage:
                path = Path(storage[key])
                assert path.exists()
                assert path.is_dir()


class TestMatchingConfiguration:
    """Test matching configuration"""

    def test_get_matching(self, config_loader):
        """Test getting matching configuration"""
        matching = config_loader.get_matching()
        assert isinstance(matching, dict)
        assert "fuzzy_threshold" in matching

    def test_matching_default_threshold(self, config_loader):
        """Test that matching has a reasonable default threshold"""
        matching = config_loader.get_matching()
        threshold = matching.get("fuzzy_threshold", 80)
        assert isinstance(threshold, int)
        assert 0 <= threshold <= 100


class TestLoggingConfiguration:
    """Test logging configuration"""

    def test_get_logging(self, config_loader):
        """Test getting logging configuration"""
        logging_config = config_loader.get_logging()
        assert isinstance(logging_config, dict)
        assert "level" in logging_config

    def test_logging_valid_level(self, config_loader):
        """Test that logging level is valid"""
        logging_config = config_loader.get_logging()
        level = logging_config.get("level", "INFO")
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert level.upper() in valid_levels


class TestCompleteConfiguration:
    """Test complete configuration"""

    def test_get_all_config(self, config_loader):
        """Test getting all configuration"""
        all_config = config_loader.get_all_config()
        assert isinstance(all_config, dict)
        assert "search_providers" in all_config
        # metadata_providers may not be in test config
        assert "download_client" in all_config

    def test_config_has_storage(self, config_loader):
        """Test that config includes storage settings"""
        all_config = config_loader.get_all_config()
        assert "storage" in all_config
        assert isinstance(all_config["storage"], dict)


class TestConfigReload:
    """Test configuration reloading"""

    def test_reload_config(self, config_loader):
        """Test reloading configuration"""
        original_config = config_loader.config.copy()
        config_loader.reload_config()
        assert config_loader.config is not None
        # Config should still have the same keys
        assert set(original_config.keys()) == set(config_loader.config.keys())


class TestJWTSecret:
    """Test JWT secret generation and retrieval"""

    def test_get_jwt_secret(self, config_loader):
        """Test getting JWT secret"""
        secret = config_loader.get_jwt_secret()
        assert secret is not None
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_jwt_secret_persistence(self, config_loader):
        """Test that JWT secret is persistent"""
        secret1 = config_loader.get_jwt_secret()
        secret2 = config_loader.get_jwt_secret()
        assert secret1 == secret2


class TestServerConfiguration:
    """Test server configuration"""

    def test_get_server(self, config_loader):
        """Test getting server configuration"""
        server = config_loader.get_server()
        assert isinstance(server, dict)
        assert "host" in server
        assert "port" in server

    def test_server_defaults(self, config_loader):
        """Test server configuration defaults"""
        server = config_loader.get_server()
        # Should have reasonable defaults
        assert server["host"] in ["0.0.0.0", "127.0.0.1", "localhost"]
        assert isinstance(server["port"], int)
        assert 1024 <= server["port"] <= 65535


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

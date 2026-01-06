"""
Test suite for config router API endpoints
Tests the masking of sensitive data and preservation of API keys
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.routers.config import _mask_sensitive_config, _deep_merge


class TestMaskSensitiveConfig:
    """Test masking of sensitive configuration data"""

    def test_mask_search_provider_api_keys(self):
        """Test that search provider API keys are masked"""
        config = {
            "search_providers": [
                {"name": "Provider1", "api_key": "secret_key_123", "api_url": "http://example.com"},
                {"name": "Provider2", "api_key": "another_secret", "api_url": "http://example2.com"}
            ]
        }

        masked = _mask_sensitive_config(config)

        assert masked["search_providers"][0]["api_key"] == "***"
        assert masked["search_providers"][1]["api_key"] == "***"
        # Other fields should remain unchanged
        assert masked["search_providers"][0]["name"] == "Provider1"
        assert masked["search_providers"][0]["api_url"] == "http://example.com"

    def test_mask_download_client_api_key(self):
        """Test that download client API key is masked"""
        config = {
            "download_client": {
                "type": "sabnzbd",
                "api_url": "http://localhost:8080",
                "api_key": "download_secret_key"
            }
        }

        masked = _mask_sensitive_config(config)

        assert masked["download_client"]["api_key"] == "***"
        assert masked["download_client"]["type"] == "sabnzbd"
        assert masked["download_client"]["api_url"] == "http://localhost:8080"

    def test_mask_empty_api_keys(self):
        """Test that empty API keys remain empty"""
        config = {
            "search_providers": [
                {"name": "Provider1", "api_key": "", "api_url": "http://example.com"}
            ],
            "download_client": {
                "type": "sabnzbd",
                "api_key": ""
            }
        }

        masked = _mask_sensitive_config(config)

        assert masked["search_providers"][0]["api_key"] == ""
        assert masked["download_client"]["api_key"] == ""

    def test_mask_missing_api_keys(self):
        """Test that missing API keys don't cause errors"""
        config = {
            "search_providers": [
                {"name": "Provider1", "api_url": "http://example.com"}
            ],
            "download_client": {
                "type": "sabnzbd"
            }
        }

        masked = _mask_sensitive_config(config)

        # Should not have added api_key fields
        assert "api_key" not in masked["search_providers"][0]


class TestDeepMerge:
    """Test deep merge functionality for config updates"""

    def test_preserve_search_provider_api_keys_when_masked(self):
        """Test that masked API keys are preserved from base config"""
        base = {
            "search_providers": [
                {"name": "Provider1", "api_key": "real_secret_123", "api_url": "http://example.com"},
                {"name": "Provider2", "api_key": "real_secret_456", "api_url": "http://example2.com"}
            ]
        }

        update = {
            "search_providers": [
                {"name": "Provider1", "api_key": "***", "api_url": "http://example.com"},
                {"name": "Provider2", "api_key": "***", "api_url": "http://example2.com"}
            ]
        }

        result = _deep_merge(base, update)

        # API keys should be preserved from base
        assert result["search_providers"][0]["api_key"] == "real_secret_123"
        assert result["search_providers"][1]["api_key"] == "real_secret_456"

    def test_update_search_provider_api_key_when_not_masked(self):
        """Test that real API keys are updated when provided"""
        base = {
            "search_providers": [
                {"name": "Provider1", "api_key": "old_key", "api_url": "http://example.com"}
            ]
        }

        update = {
            "search_providers": [
                {"name": "Provider1", "api_key": "new_real_key", "api_url": "http://example.com"}
            ]
        }

        result = _deep_merge(base, update)

        # API key should be updated to new value
        assert result["search_providers"][0]["api_key"] == "new_real_key"

    def test_preserve_download_client_api_key_when_masked(self):
        """Test that masked download client API key is preserved"""
        base = {
            "download_client": {
                "type": "sabnzbd",
                "api_url": "http://localhost:8080",
                "api_key": "real_download_key"
            }
        }

        update = {
            "download_client": {
                "type": "sabnzbd",
                "api_url": "http://localhost:8080",
                "api_key": "***"
            }
        }

        result = _deep_merge(base, update)

        # API key should be preserved from base
        assert result["download_client"]["api_key"] == "real_download_key"

    def test_update_download_client_api_key_when_not_masked(self):
        """Test that download client API key is updated when real value provided"""
        base = {
            "download_client": {
                "type": "sabnzbd",
                "api_key": "old_key"
            }
        }

        update = {
            "download_client": {
                "type": "sabnzbd",
                "api_key": "new_real_key"
            }
        }

        result = _deep_merge(base, update)

        # API key should be updated
        assert result["download_client"]["api_key"] == "new_real_key"

    def test_mixed_masked_and_real_keys(self):
        """Test updating with a mix of masked and real API keys"""
        base = {
            "search_providers": [
                {"name": "Provider1", "api_key": "real_key_1", "api_url": "http://example1.com"},
                {"name": "Provider2", "api_key": "real_key_2", "api_url": "http://example2.com"}
            ]
        }

        update = {
            "search_providers": [
                {"name": "Provider1", "api_key": "***", "api_url": "http://example1.com"},  # Masked - preserve
                {"name": "Provider2", "api_key": "new_key_2", "api_url": "http://example2.com"}  # Real - update
            ]
        }

        result = _deep_merge(base, update)

        # First provider's key should be preserved
        assert result["search_providers"][0]["api_key"] == "real_key_1"
        # Second provider's key should be updated
        assert result["search_providers"][1]["api_key"] == "new_key_2"

    def test_preserve_other_fields_while_updating_api_key(self):
        """Test that non-API key fields are updated correctly"""
        base = {
            "search_providers": [
                {"name": "OldName", "api_key": "real_key", "api_url": "http://old.com", "enabled": False}
            ]
        }

        update = {
            "search_providers": [
                {"name": "NewName", "api_key": "***", "api_url": "http://new.com", "enabled": True}
            ]
        }

        result = _deep_merge(base, update)

        # API key should be preserved
        assert result["search_providers"][0]["api_key"] == "real_key"
        # Other fields should be updated
        assert result["search_providers"][0]["name"] == "NewName"
        assert result["search_providers"][0]["api_url"] == "http://new.com"
        assert result["search_providers"][0]["enabled"] is True

    def test_add_new_provider_with_real_key(self):
        """Test adding a new provider with a real API key"""
        base = {
            "search_providers": [
                {"name": "Provider1", "api_key": "real_key_1", "api_url": "http://example1.com"}
            ]
        }

        update = {
            "search_providers": [
                {"name": "Provider1", "api_key": "***", "api_url": "http://example1.com"},
                {"name": "Provider2", "api_key": "new_real_key_2", "api_url": "http://example2.com"}
            ]
        }

        result = _deep_merge(base, update)

        # First provider's key should be preserved
        assert result["search_providers"][0]["api_key"] == "real_key_1"
        # New provider should have the new key
        assert result["search_providers"][1]["api_key"] == "new_real_key_2"

    def test_handle_mismatched_provider_counts(self):
        """Test handling when provider arrays have different lengths"""
        base = {
            "search_providers": [
                {"name": "Provider1", "api_key": "real_key_1", "api_url": "http://example1.com"},
                {"name": "Provider2", "api_key": "real_key_2", "api_url": "http://example2.com"}
            ]
        }

        # Update has only one provider (e.g., user removed one)
        update = {
            "search_providers": [
                {"name": "Provider1", "api_key": "***", "api_url": "http://example1.com"}
            ]
        }

        result = _deep_merge(base, update)

        # Should have only one provider with preserved key
        assert len(result["search_providers"]) == 1
        assert result["search_providers"][0]["api_key"] == "real_key_1"

    def test_deep_merge_nested_dicts(self):
        """Test that nested dictionaries are merged correctly"""
        base = {
            "storage": {
                "db_path": "/old/path",
                "download_dir": "/downloads"
            }
        }

        update = {
            "storage": {
                "db_path": "/new/path"
            }
        }

        result = _deep_merge(base, update)

        # Updated field should change
        assert result["storage"]["db_path"] == "/new/path"
        # Non-updated field should be preserved
        assert result["storage"]["download_dir"] == "/downloads"

    def test_regression_bug_scenario(self):
        """
        Test the original bug scenario:
        UI sends masked config back to server, which should preserve real keys
        """
        # Simulate real config loaded from file
        base_config = {
            "search_providers": [
                {"name": "Provider1", "api_key": "super_secret_key_123", "api_url": "http://api.example.com"}
            ],
            "download_client": {
                "type": "sabnzbd",
                "api_url": "http://localhost:8080",
                "api_key": "download_secret_456"
            }
        }

        # Simulate what UI would send (masked values from a previous GET request)
        ui_update = {
            "search_providers": [
                {"name": "Provider1", "api_key": "***", "api_url": "http://api.example.com"}
            ]
        }

        result = _deep_merge(base_config, ui_update)

        # The real keys should be preserved, NOT overwritten with "***"
        assert result["search_providers"][0]["api_key"] == "super_secret_key_123"
        assert result["search_providers"][0]["api_key"] != "***"

        # Download client should remain unchanged
        assert result["download_client"]["api_key"] == "download_secret_456"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

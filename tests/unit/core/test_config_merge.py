"""
Tests for config merge functionality
"""

import sys
from pathlib import Path

import pytest
from ruamel.yaml import YAML

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.config_merge import (
    _deep_merge,
    _remove_deprecated_keys,
    merge_config_with_sample,
)


class TestDeepMerge:
    """Test deep merge logic"""

    def test_merge_preserves_user_scalars(self):
        """User scalar values should override sample values"""
        user = "user_value"
        sample = "template_value"

        result = _deep_merge(user, sample)
        assert result == "user_value"

    def test_merge_uses_template_when_user_missing(self):
        """Sample value should be used when user value is None"""
        user = None
        sample = "template_value"

        result = _deep_merge(user, sample)
        assert result == "template_value"

    def test_merge_dict_adds_missing_keys(self):
        """Missing keys from sample should be added to user dict"""
        user = {"existing": "user_value"}
        sample = {"existing": "template_value", "new_key": "new_value"}

        result = _deep_merge(user, sample)

        assert result["existing"] == "user_value"  # User value preserved
        assert result["new_key"] == "new_value"  # New key added

    def test_merge_dict_removes_no_keys(self):
        """User keys not in sample should be preserved (not removed by deep merge)"""
        user = {"existing": "user_value", "extra": "extra_value"}
        sample = {"existing": "template_value"}

        result = _deep_merge(user, sample)

        assert result["existing"] == "user_value"
        assert result["extra"] == "extra_value"  # Extra key preserved

    def test_merge_dict_recursive(self):
        """Deep merge should work recursively"""
        user = {"level1": {"level2": {"user_key": "user_value"}}}
        sample = {"level1": {"level2": {"user_key": "template_value", "new_key": "new_value"}}}

        result = _deep_merge(user, sample)

        assert result["level1"]["level2"]["user_key"] == "user_value"
        assert result["level1"]["level2"]["new_key"] == "new_value"

    def test_merge_list_prefers_user(self):
        """Lists should use user value entirely (not merge elements)"""
        user = [{"type": "user", "value": 1}]
        sample = [{"type": "sample", "value": 2}, {"type": "sample2", "value": 3}]

        result = _deep_merge(user, sample)

        assert result == user  # User list used entirely

    def test_merge_type_mismatch_prefers_user(self):
        """Type mismatches should prefer user value with warning"""
        user = "string_value"
        sample = 123

        result = _deep_merge(user, sample)
        assert result == "string_value"


class TestRemoveDeprecatedKeys:
    """Test removal of deprecated config keys"""

    def test_remove_invalid_top_level_keys(self):
        """Invalid top-level keys should be removed"""
        config = {
            "search_providers": [],
            "storage": {},
            "invalid_key": "value",
            "another_invalid": "value",
        }

        cleaned, removed = _remove_deprecated_keys(config)

        assert "search_providers" in cleaned
        assert "storage" in cleaned
        assert "invalid_key" not in cleaned
        assert "another_invalid" not in cleaned
        assert removed == ["invalid_key", "another_invalid"]

    def test_preserve_all_valid_keys(self):
        """All valid keys should be preserved"""
        config = {
            "search_providers": [],
            "download_client": {},
            "storage": {},
            "matching": {},
            "import": {},
            "pdf": {},
            "downloads": {},
            "ocr": {},
            "metadata": {},
            "tasks": {},
            "logging": {},
            "server": {},
            "jwt_secret": "secret",
        }

        cleaned, removed = _remove_deprecated_keys(config)

        assert len(cleaned) == len(config)
        assert removed == []


class TestMergeConfigWithTemplate:
    """Test full config merge workflow"""

    @pytest.fixture
    def template_config_file(self, tmp_path):
        """Create a template config file"""
        yaml = YAML()
        sample = {
            "storage": {"db_path": "./data/db.sqlite", "download_dir": "./downloads"},
            "logging": {"level": "INFO"},
            "new_section": {"new_option": "default_value"},
        }

        template_path = tmp_path / "config.template.yaml"
        with open(template_path, "w", encoding="utf-8") as f:
            yaml.dump(sample, f)

        return template_path

    @pytest.fixture
    def user_config_file(self, tmp_path):
        """Create a user config file"""
        yaml = YAML()
        user = {
            "storage": {"db_path": "./custom/db.sqlite"},  # Custom value
            "logging": {"level": "DEBUG"},  # Custom value
            "deprecated_key": "should_be_removed",  # Invalid key
        }

        user_path = tmp_path / "config.yaml"
        with open(user_path, "w", encoding="utf-8") as f:
            yaml.dump(user, f)

        return user_path

    def test_merge_preserves_user_values(self, user_config_file, template_config_file):
        """Merge should preserve user's custom values"""
        changed, message = merge_config_with_sample(
            config_path=user_config_file,
            template_path=template_config_file,
            create_backup=False,
        )

        assert changed is True

        # Read merged config
        yaml = YAML()
        with open(user_config_file, "r", encoding="utf-8") as f:
            merged = yaml.load(f)

        # User values preserved
        assert merged["storage"]["db_path"] == "./custom/db.sqlite"
        assert merged["logging"]["level"] == "DEBUG"

        # New keys added
        assert "new_section" in merged
        assert merged["new_section"]["new_option"] == "default_value"

        # Missing keys from sample added
        assert "download_dir" in merged["storage"]

    def test_merge_removes_deprecated_keys(self, user_config_file, template_config_file):
        """Merge should remove deprecated keys"""
        changed, message = merge_config_with_sample(
            config_path=user_config_file,
            template_path=template_config_file,
            create_backup=False,
        )

        assert changed is True
        assert "deprecated" in message.lower()

        # Read merged config
        yaml = YAML()
        with open(user_config_file, "r", encoding="utf-8") as f:
            merged = yaml.load(f)

        assert "deprecated_key" not in merged

    def test_merge_creates_backup(self, user_config_file, template_config_file):
        """Merge should create backup file"""
        merge_config_with_sample(
            config_path=user_config_file,
            template_path=template_config_file,
            create_backup=True,
        )

        # Check for backup file (format: config.YYYYMMDD_HHMMSS.bak)
        backup_files = list(user_config_file.parent.glob("*.bak"))
        assert len(backup_files) == 1
        assert "config" in backup_files[0].name

    def test_merge_no_changes_when_already_synced(self, tmp_path, template_config_file):
        """Merge should not modify file if already in sync"""
        yaml = YAML()

        # Create user config identical to sample
        with open(template_config_file, "r", encoding="utf-8") as f:
            sample = yaml.load(f)

        user_path = tmp_path / "config.yaml"
        with open(user_path, "w", encoding="utf-8") as f:
            yaml.dump(sample, f)

        changed, message = merge_config_with_sample(
            config_path=user_path,
            template_path=template_config_file,
            create_backup=False,
        )

        assert changed is False
        assert "up to date" in message.lower()

    def test_merge_dry_run_no_changes(self, user_config_file, template_config_file):
        """Dry run should not modify files"""
        # Read original content
        with open(user_config_file, "r", encoding="utf-8") as f:
            original = f.read()

        changed, message = merge_config_with_sample(
            config_path=user_config_file,
            template_path=template_config_file,
            dry_run=True,
        )

        assert changed is True
        assert "[DRY RUN]" in message

        # File should not be modified
        with open(user_config_file, "r", encoding="utf-8") as f:
            current = f.read()

        assert current == original

    def test_merge_nonexistent_template_raises_error(self, user_config_file, tmp_path):
        """Merge should raise error if sample doesn't exist"""
        with pytest.raises(FileNotFoundError):
            merge_config_with_sample(
                config_path=user_config_file,
                template_path=tmp_path / "nonexistent.yaml",
            )

    def test_merge_nonexistent_user_returns_false(self, tmp_path, template_config_file):
        """Merge should return False if user config doesn't exist"""
        changed, message = merge_config_with_sample(
            config_path=tmp_path / "nonexistent.yaml",
            template_path=template_config_file,
        )

        assert changed is False
        assert "doesn't exist" in message.lower()

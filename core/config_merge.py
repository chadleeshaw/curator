"""
Config merge utilities for keeping user config in sync with config.template.yaml

Merges user config with template config on startup to:
- Add new configuration options with defaults and documentation
- Preserve all existing user values
- Remove deprecated/unsupported options
- Maintain YAML formatting and comments
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from ruamel.yaml import YAML

    HAS_RUAMEL = True
except ImportError:
    HAS_RUAMEL = False
    YAML = None  # type: ignore

logger = logging.getLogger(__name__)

# Valid top-level config keys (defined in core/config.py)
VALID_CONFIG_KEYS = {
    "search_providers",
    "metadata_providers",
    "download_client",
    "download_clients",
    "storage",
    "cache",
    "matching",
    "import",
    "pdf",
    "downloads",
    "ocr",
    "metadata",
    "tasks",
    "logging",
    "server",
    "jwt_secret",
}


def _deep_merge(user_value: Any, template_value: Any, path: str = "") -> Any:
    """
    Deep merge user config into template config, preserving user values.

    Args:
        user_value: Value from user's config
        template_value: Value from template config (with defaults/docs)
        path: Current path in config tree (for logging)

    Returns:
        Merged value with user settings preserved
    """
    # If user value doesn't exist, use template
    if user_value is None:
        return template_value

    # If template value doesn't exist or is None, keep user value
    # This handles cases where:
    # - User has deprecated config that's been removed from template
    # - Template has null/optional fields (e.g., jwt_secret: null)
    if template_value is None:
        return user_value

    # For dictionaries, recursively merge (check isinstance, not type equality)
    # This handles both dict and ruamel.yaml CommentedMap
    if isinstance(user_value, dict) and isinstance(template_value, dict):
        result = template_value.copy()  # Start with template (includes new keys)
        for key in user_value:
            result[key] = _deep_merge(
                user_value.get(key), template_value.get(key), f"{path}.{key}"
            )
        return result

    # For lists, prefer user value entirely (don't merge list items)
    # This is important for things like search_providers where order matters
    if isinstance(user_value, list):
        return user_value

    # For scalars (str, int, bool), always use user value
    # Only warn about type mismatches for actual type conflicts (not None vs value)
    if type(user_value) is not type(template_value):  # noqa: E721
        # Only log as debug since this is expected for optional fields
        logger.debug(
            f"Config type mismatch at '{path}': user={type(user_value).__name__}, "
            f"template={type(template_value).__name__}. Using user value."
        )

    return user_value


def _migrate_download_clients(config: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Migrate old split download_client/download_clients format to the unified list format.

    Old format:
        download_client:          # singular dict — the NZB client
          type: sabnzbd
          ...
        download_clients:         # named dict — additional clients by type key
          internet_archive:
            type: internet_archive
            ...

    New format:
        download_clients:         # list of all clients
          - type: sabnzbd
            ...
          - type: internet_archive
            ...

    Args:
        config: User config dictionary (may be old or new format)

    Returns:
        Tuple of (migrated config, was_migrated)
    """
    has_legacy_singular = "download_client" in config and isinstance(
        config["download_client"], dict
    )
    has_legacy_plural = "download_clients" in config and isinstance(
        config["download_clients"], dict
    )

    # Already in new list format — nothing to do
    if not has_legacy_singular and not has_legacy_plural:
        return config, False

    # If download_clients is already a list, it's already migrated
    if "download_clients" in config and isinstance(config["download_clients"], list):
        # Clean up any leftover singular key
        if has_legacy_singular:
            migrated = {k: v for k, v in config.items() if k != "download_client"}
            logger.info(
                "Removed legacy 'download_client' key (download_clients list already present)"
            )
            return migrated, True
        return config, False

    clients_list: List[Dict[str, Any]] = []

    # Add the primary NZB client first
    if has_legacy_singular:
        primary = dict(config["download_client"])
        clients_list.append(primary)
        logger.info(
            f"Migrating legacy 'download_client' ({primary.get('type', 'unknown')}) to unified list"
        )

    # Add additional clients (old named-dict format)
    if has_legacy_plural:
        for client_type, client_cfg in config["download_clients"].items():
            if isinstance(client_cfg, dict):
                entry = dict(client_cfg)
                # Ensure type is set
                if "type" not in entry:
                    entry["type"] = client_type
                clients_list.append(entry)
                logger.info(
                    f"Migrating legacy 'download_clients.{client_type}' to unified list"
                )

    migrated = {
        k: v
        for k, v in config.items()
        if k not in ("download_client", "download_clients")
    }
    migrated["download_clients"] = clients_list

    logger.info(
        f"Migrated {len(clients_list)} download client(s) to unified list format"
    )
    return migrated, True


def _remove_deprecated_keys(config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Remove deprecated top-level keys from config.

    Args:
        config: User config dictionary

    Returns:
        Tuple of (cleaned config, list of removed keys)
    """
    removed_keys = []
    cleaned = {}

    for key, value in config.items():
        if key in VALID_CONFIG_KEYS:
            cleaned[key] = value
        else:
            removed_keys.append(key)
            logger.info(f"Removing deprecated config key: '{key}'")

    return cleaned, removed_keys


def merge_config_with_sample(
    config_path: Path,
    template_path: Path,
    create_backup: bool = True,
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """
    Merge user config with template config, preserving user values.

    Process:
    1. Load user config and template config using ruamel.yaml (preserves comments)
    2. Remove deprecated keys from user config
    3. Deep merge: user values override sample, but missing keys are added from sample
    4. Create backup if changes detected
    5. Write merged config back to file

    Args:
        config_path: Path to user's config file
        template_path: Path to config.template.yaml
        create_backup: Whether to create .bak file before writing
        dry_run: If True, don't write changes (just report what would change)

    Returns:
        Tuple of (changed, message) where:
        - changed: True if config was modified
        - message: Description of changes made

    Raises:
        FileNotFoundError: If template config doesn't exist
        ValueError: If config files are invalid
    """
    # Check if ruamel.yaml is available
    if not HAS_RUAMEL:
        logger.warning(
            "Config sync skipped: ruamel.yaml not installed (run: pip install ruamel.yaml)"
        )
        return False, "ruamel.yaml not installed"

    # Validate inputs
    if not template_path.exists():
        raise FileNotFoundError(f"Template config not found: {template_path}")

    if not config_path.exists():
        logger.info(f"User config doesn't exist yet: {config_path}")
        return False, "Config file doesn't exist, skipping merge"

    # Load configs with ruamel.yaml to preserve comments
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    try:
        with open(template_path, "r") as f:
            template_config = yaml.load(f)

        with open(config_path, "r") as f:
            user_config = yaml.load(f)

    except Exception as e:
        raise ValueError(f"Failed to load config files: {e}") from e

    if not template_config:
        raise ValueError(f"Template config is empty: {template_path}")

    if not user_config:
        logger.warning(f"User config is empty: {config_path}")
        user_config = {}

    # Accumulate change descriptions throughout the merge process
    changes = []

    # Step 1: Migrate legacy download client format to unified list
    user_config, migration_happened = _migrate_download_clients(user_config)
    if migration_happened:
        changes.append(
            "Migrated download_client/download_clients to unified download_clients list"
        )

    # Step 2: Remove deprecated keys
    cleaned_config, removed_keys = _remove_deprecated_keys(user_config)

    # Step 3: Deep merge user config into template config
    merged_config = _deep_merge(cleaned_config, template_config)

    # Step 4: Check if anything changed
    changed = merged_config != user_config or migration_happened

    if not changed:
        logger.debug("Config is already up to date")
        return False, "Config is already up to date"

    # Build change summary
    if removed_keys:
        changes.append(
            f"Removed {len(removed_keys)} deprecated keys: {', '.join(removed_keys)}"
        )

    # Count new keys added (approximate - just check top-level)
    new_keys = set(merged_config.keys()) - set(user_config.keys())
    if new_keys:
        changes.append(f"Added {len(new_keys)} new keys: {', '.join(new_keys)}")

    change_summary = "; ".join(changes) if changes else "Updated configuration values"

    if dry_run:
        logger.info(f"[DRY RUN] Would update config: {change_summary}")
        return True, f"[DRY RUN] {change_summary}"

    # Step 4: Create backup
    if create_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_suffix(f".{timestamp}.bak")
        try:
            shutil.copy2(config_path, backup_path)
            logger.info(f"Created config backup: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            # Continue anyway - backup failure shouldn't prevent merge

    # Step 5: Write merged config
    try:
        with open(config_path, "w") as f:
            yaml.dump(merged_config, f)
        logger.info(f"Updated config file: {change_summary}")
        return True, change_summary

    except Exception as e:
        logger.error(f"Failed to write merged config: {e}")
        raise


def sync_config_on_startup(config_path: Path) -> None:
    """
    Sync user config with template config on application startup.

    This is called automatically by ConfigLoader to ensure the user's
    config file always has the latest options and documentation.

    Args:
        config_path: Path to user's config file
    """
    # Determine template config path (same directory as this module)
    module_dir = Path(__file__).parent.parent
    template_path = module_dir / "config.template.yaml"

    if not template_path.exists():
        logger.warning(f"Template config not found, skipping merge: {template_path}")
        return

    try:
        changed, message = merge_config_with_sample(
            config_path=config_path,
            template_path=template_path,
            create_backup=True,
            dry_run=False,
        )

        if changed:
            logger.info(f"Config synchronized: {message}")
        else:
            logger.debug("Config already synchronized with sample")

    except Exception as e:
        # Don't fail startup if merge fails - just log and continue
        logger.warning(f"Failed to sync config with sample: {e}")

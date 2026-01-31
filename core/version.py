"""
Version management for Curator

Reads version information from git tags or falls back to package.json
"""

import subprocess
import json
import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_version() -> str:
    """
    Get the current version of Curator.

    Tries to get version from:
    1. Git tags (git describe --tags) - if it includes a tag
    2. package.json
    3. Falls back to "unknown"

    Returns:
        Version string (e.g., "v3.14.2" or "v3.14.2-5-g1a2b3c4")
    """
    # Try to get version from git tags
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).parent.parent,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            version = result.stdout.strip()
            # Only use git version if it's a proper tag (contains 'v' or '-')
            # If it's just a bare commit hash, fall through to package.json
            if "v" in version or "-" in version:
                logger.debug("Version from git tags: %s", version)
                return version

            logger.debug("Git returned bare hash '%s', falling back to package.json", version)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("Could not get version from git: %s", e)

    # Try to get version from package.json
    try:
        package_json_path = Path(__file__).parent.parent / "package.json"
        if package_json_path.exists():
            with open(package_json_path, "r", encoding="utf-8") as f:
                package_data = json.load(f)
                version = package_data.get("version", "unknown")
                if version != "unknown":
                    version = f"v{version}"
                    logger.debug("Version from package.json: %s", version)
                    return version
    except (json.JSONDecodeError, IOError, Exception) as e:
        logger.debug("Could not get version from package.json: %s", e)

    # Fall back to unknown
    logger.warning("Could not determine version, using 'unknown'")
    return "unknown"


def get_version_info() -> dict:
    """
    Get detailed version information.

    Returns:
        Dictionary with version details:
        - version: The version string
        - is_dev: Whether this is a development version (has commits after tag)
    """
    version = get_version()
    is_dev = "-" in version and version != "unknown"

    return {
        "version": version,
        "is_dev": is_dev,
    }

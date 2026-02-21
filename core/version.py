"""
Version management for Curator

Reads version information from git tags or falls back to package.json
"""

import os
import subprocess
import json
import logging
from pathlib import Path
from functools import lru_cache

from core.constants.app import VERSION_CHECK_TIMEOUT

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_build_hash() -> str:
    """
    Get the current git commit hash.

    Checks (in order):
    1. BUILD_HASH environment variable (set during Docker build)
    2. Git rev-parse (for development environments)

    Returns:
        Short commit hash (7 characters) or "unknown" if not available
    """
    # Check environment variable first (set during Docker build)
    env_hash = os.environ.get("BUILD_HASH", "").strip()
    if env_hash and env_hash != "unknown":
        logger.debug("Build hash from environment: %s", env_hash)
        return env_hash

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=VERSION_CHECK_TIMEOUT,
            cwd=Path(__file__).parent.parent,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            build_hash = result.stdout.strip()
            logger.debug("Build hash from git: %s", build_hash)
            return build_hash
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("Could not get build hash from git: %s", e)

    return "unknown"


@lru_cache(maxsize=1)
def get_version() -> str:
    """
    Get the current base version tag of Curator.

    Tries to get version from:
    1. BUILD_VERSION environment variable (set during Docker build)
    2. Git tags (git describe --tags --abbrev=0) - returns just the tag name
    3. package.json
    4. Falls back to "unknown"

    Only the env var and git sources are cached. If resolution falls through
    to package.json the cache is bypassed so subsequent calls retry git,
    ensuring a temporary git failure doesn't permanently freeze the version.

    Returns:
        Base version tag (e.g., "v1.0.0")
    """
    return _resolve_version()


def _resolve_version() -> str:
    """Resolve the version without caching (called by get_version with cache bypass logic)."""
    # Check environment variable first (set during Docker build)
    env_version = os.environ.get("BUILD_VERSION", "").strip()
    if env_version and env_version != "unknown":
        logger.debug("Version from environment: %s", env_version)
        return env_version

    # Try to get version from git tags (--abbrev=0 returns just the tag name)
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=VERSION_CHECK_TIMEOUT,
            cwd=Path(__file__).parent.parent,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            version = result.stdout.strip()
            logger.debug("Version from git tag: %s", version)
            return version
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("Could not get version from git: %s", e)

    # Try to get version from package.json — clear lru_cache so the next
    # call retries git in case this was a transient failure
    get_version.cache_clear()
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
        - version: The base version tag (e.g., "v1.0.0")
        - is_dev: Whether this is a development version (has commits after tag)
        - build_hash: The git commit hash
    """
    version = get_version()
    build_hash = get_build_hash()

    # Determine if this is a dev build by checking if HEAD is beyond the tag
    is_dev = False
    if build_hash != "unknown":
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True,
                text=True,
                timeout=VERSION_CHECK_TIMEOUT,
                cwd=Path(__file__).parent.parent,
                check=False,
            )
            if result.returncode == 0:
                raw = result.stdout.strip()
                # If git describe includes commit count (e.g., v1.0.0-159-g028aaf1),
                # we're ahead of the tag
                is_dev = raw != version
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    return {
        "version": version,
        "is_dev": is_dev,
        "build_hash": build_hash,
    }

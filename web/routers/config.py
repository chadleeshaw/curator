"""
Configuration management routes
"""

import logging
import os
import sys
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException

router = APIRouter(prefix="/api/config", tags=["configuration"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_config_loader = None


def set_dependencies(config_loader):
    """Set dependencies from main app"""
    global _config_loader
    _config_loader = config_loader


def _mask_sensitive_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive data in config for UI display"""
    masked = config.copy()

    # Mask API keys in search providers
    if "search_providers" in masked:
        for provider in masked["search_providers"]:
            if "api_key" in provider:
                provider["api_key"] = "***" if provider["api_key"] else ""

    # Mask download client API key
    if "download_client" in masked and "api_key" in masked["download_client"]:
        masked["download_client"]["api_key"] = "***" if masked["download_client"].get("api_key") else ""

    return masked


def _deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge update into base dict, handling arrays properly and preserving masked keys"""
    result = base.copy()

    for key, value in update.items():
        if key in result:
            if isinstance(result[key], list) and isinstance(value, list):
                # For lists, replace the entire list
                result[key] = value
            elif isinstance(result[key], dict) and isinstance(value, dict):
                # For dicts, recursively merge
                result[key] = _deep_merge(result[key], value)
            else:
                # For primitives, replace
                result[key] = value
        else:
            result[key] = value

    # Preserve original API keys if masked values are submitted
    if "search_providers" in result and "search_providers" in update:
        for i, provider in enumerate(update.get("search_providers", [])):
            if provider.get("api_key") == "***" and i < len(base.get("search_providers", [])):
                # User didn't change the API key, preserve the original
                result["search_providers"][i]["api_key"] = base["search_providers"][i].get("api_key", "***")

    # Preserve download client API key if masked
    if "download_client" in update and update["download_client"].get("api_key") == "***":
        if "download_client" in base:
            result["download_client"]["api_key"] = base["download_client"].get("api_key", "***")

    return result


@router.get("")
async def get_config():
    """Get current configuration"""
    try:
        config = _config_loader.get_all_config()

        # Mask sensitive data in response
        safe_config = _mask_sensitive_config(config)

        return {"status": "success", "config": safe_config}
    except Exception as e:
        logger.error(f"Get config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def update_config(config_update: Dict[str, Any]):
    """Update configuration"""
    try:
        current_config = _config_loader.get_all_config()

        # Deep merge the update with current config
        updated_config = _deep_merge(current_config, config_update)

        # Save to file
        _config_loader.save_config(updated_config)

        # Return masked config
        safe_config = _mask_sensitive_config(updated_config)

        logger.info("Configuration updated via UI")

        return {
            "status": "success",
            "message": "Configuration updated. Please restart the application for changes to take effect.",
            "config": safe_config,
        }
    except Exception as e:
        logger.error(f"Update config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_config():
    """Reload configuration and reinitialize providers"""
    try:
        # Note: This would typically call a reinitialization function
        # But that logic needs to stay in main app due to global state dependencies
        # This endpoint signals the need to reload but actual reloading happens elsewhere
        _config_loader.reload_config()

        return {"status": "success", "message": "Configuration reloaded. Providers will be reinitialized."}
    except Exception as e:
        logger.error(f"Reload config error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart")
async def restart_application(background_tasks: BackgroundTasks):
    """Restart the application"""
    try:
        logger.info("Restart request received - restarting application")

        def restart_process():
            import time

            time.sleep(1)  # Give time for response to be sent
            os.execv(sys.executable, [sys.executable] + sys.argv)

        background_tasks.add_task(restart_process)

        return {"status": "success", "message": "Application restarting..."}
    except Exception as e:
        logger.error(f"Restart error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

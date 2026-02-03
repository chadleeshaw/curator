"""
Configuration management routes
"""

import copy
import logging
import os
import sys
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException

from core.utils.error_handling import handle_api_errors
from web.utils.responses import error_response, status_response, success_response

router = APIRouter(prefix="/api/config", tags=["configuration"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_config_loader = None


def set_dependencies(config_loader: Any) -> None:
    """Set dependencies from main app"""
    global _config_loader
    _config_loader = config_loader


def _mask_sensitive_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive data in config for UI display"""
    masked = copy.deepcopy(config)

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
                # For search_providers, preserve original API keys where they're masked
                if key == "search_providers":
                    # Create new list to avoid modifying the input
                    merged_list = []
                    for i, provider in enumerate(value):
                        provider_copy = provider.copy()
                        # If the API key is masked and there's an original, use the original
                        if provider_copy.get("api_key") == "***" and i < len(result[key]):
                            original_key = result[key][i].get("api_key", "")
                            provider_copy["api_key"] = original_key
                        merged_list.append(provider_copy)
                    result[key] = merged_list
                else:
                    # For other lists, replace entirely
                    result[key] = value
            elif isinstance(result[key], dict) and isinstance(value, dict):
                # For dicts, recursively merge
                result[key] = _deep_merge(result[key], value)
            else:
                # For primitives, replace
                result[key] = value
        else:
            result[key] = value

    # Preserve download client API key if masked
    if "download_client" in update and update["download_client"].get("api_key") == "***":
        if "download_client" in base:
            result["download_client"]["api_key"] = base["download_client"].get("api_key", "")

    return result


@router.get("")
@handle_api_errors("Get config", logger)
async def get_config():
    """Get current configuration"""
    # Reload from file to ensure we have the latest (including manual edits)
    _config_loader.reload_config()
    config = _config_loader.get_all_config()

    # Mask sensitive data in response
    safe_config = _mask_sensitive_config(config)

    return status_response("success", config=safe_config)


@router.post("")
@handle_api_errors("Update config", logger)
async def update_config(config_update: Dict[str, Any], background_tasks: BackgroundTasks):
    """Update configuration and restart application"""
    # Reload from file to ensure we have the latest (including manual edits)
    _config_loader.reload_config()
    current_config = _config_loader.get_all_config()

    # Deep merge the update with current config
    updated_config = _deep_merge(current_config, config_update)

    # Save to file
    _config_loader.save_config(updated_config)

    # Return masked config
    safe_config = _mask_sensitive_config(updated_config)

    logger.info("Configuration updated via UI")

    # Schedule restart in background
    def restart_process():
        import time

        time.sleep(1)  # Give time for response to be sent
        os.execv(sys.executable, [sys.executable] + sys.argv)

    background_tasks.add_task(restart_process)

    return success_response(
        "Configuration updated. Application restarting...",
        status="success",
        config=safe_config,
    )


@router.post("/save")
@handle_api_errors("Save config", logger)
async def save_config_only(config_update: Dict[str, Any]):
    """Save configuration without restarting"""
    # Reload from file to ensure we have the latest (including manual edits)
    _config_loader.reload_config()
    current_config = _config_loader.get_all_config()

    # Deep merge the update with current config
    updated_config = _deep_merge(current_config, config_update)

    # Save to file
    _config_loader.save_config(updated_config)

    # Apply logging level changes immediately (no restart needed)
    if "logging" in config_update and "level" in config_update["logging"]:
        new_level = config_update["logging"]["level"].upper()
        level_value = getattr(logging, new_level, logging.INFO)

        # Update all loggers
        logging.getLogger().setLevel(level_value)
        for name in logging.Logger.manager.loggerDict:
            log = logging.getLogger(name)
            log.setLevel(level_value)

        logger.info(f"Logging level changed to {new_level} (applied immediately)")

    # Return masked config
    safe_config = _mask_sensitive_config(updated_config)

    logger.info("Configuration saved via UI (no restart)")

    return success_response(
        "Configuration saved successfully.",
        status="success",
        config=safe_config,
    )


@router.post("/reload")
@handle_api_errors("Reload config", logger)
async def reload_config():
    """Reload configuration and reinitialize providers"""
    # Note: This would typically call a reinitialization function
    # But that logic needs to stay in main app due to global state dependencies
    # This endpoint signals the need to reload but actual reloading happens elsewhere
    _config_loader.reload_config()

    return status_response("success", "Configuration reloaded. Providers will be reinitialized.")


@router.post("/restart")
@handle_api_errors("Restart application", logger)
async def restart_application(background_tasks: BackgroundTasks):
    """Restart the application"""
    logger.info("Restart request received - restarting application")

    def restart_process():
        import time

        time.sleep(1)  # Give time for response to be sent
        os.execv(sys.executable, [sys.executable] + sys.argv)

    background_tasks.add_task(restart_process)

    return status_response("success", "Application restarting...")


@router.post("/test-provider")
@handle_api_errors("Test provider connection", logger)
async def test_provider_connection(provider_config: Dict[str, Any]):
    """
    Test connection to a search provider.

    Args:
        provider_config: Provider configuration with type, api_url, api_key, etc.

    Returns:
        Connection test result
    """
    try:
        provider_type = provider_config.get("type")
        if not provider_type:
            raise HTTPException(status_code=400, detail="Provider type is required")

        # Import provider classes
        if provider_type == "newsnab":
            from providers.newsnab import NewsnabProvider

            provider = NewsnabProvider(provider_config)
            result = provider.test_connection()
        elif provider_type == "internet_archive":
            from providers.internet_archive import InternetArchiveProvider

            provider = InternetArchiveProvider(provider_config)
            result = provider.test_connection()
        elif provider_type == "rss":
            return success_response("RSS providers don't require authentication")
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider type: {provider_type}")

        return result

    except ValueError as e:
        # Configuration errors (e.g., missing API key)
        return error_response(str(e))
    except Exception as e:
        logger.error(f"Test provider connection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-download-client")
@handle_api_errors("Test download client connection", logger)
async def test_download_client_connection(client_config: Dict[str, Any]):
    """
    Test connection to a download client.

    Args:
        client_config: Download client configuration with type, api_url, api_key, etc.

    Returns:
        Connection test result
    """
    try:
        client_type = client_config.get("type")
        if not client_type:
            raise HTTPException(status_code=400, detail="Download client type is required")

        # Import client classes
        if client_type == "sabnzbd":
            from clients.sabnzbd import SABnzbdClient

            client = SABnzbdClient(client_config)
            result = client.test_connection()
        elif client_type == "nzbget":
            from clients.nzbget import NZBGetClient

            client = NZBGetClient(client_config)
            result = client.test_connection()
        elif client_type == "internet_archive":
            from clients.internet_archive import InternetArchiveClient

            client = InternetArchiveClient(client_config)
            result = client.test_connection()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown download client type: {client_type}")

        return result

    except ValueError as e:
        # Configuration errors (e.g., missing API key/password)
        return error_response(str(e))
    except Exception as e:
        logger.error(f"Test download client connection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

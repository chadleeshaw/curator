"""
Metadata and parser configuration routes
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter

from core.constants import SUPPORTED_LANGUAGES, ISO_COUNTRIES

router = APIRouter(prefix="/api", tags=["metadata"])
logger = logging.getLogger(__name__)


@router.get("/constants/languages")
async def get_supported_languages() -> Dict[str, Any]:
    """Get list of supported languages"""
    return {
        "success": True,
        "languages": SUPPORTED_LANGUAGES
    }


@router.get("/constants/countries")
async def get_iso_countries() -> Dict[str, Any]:
    """Get ISO country codes and names"""
    return {
        "success": True,
        "countries": ISO_COUNTRIES
    }


@router.get("/constants")
async def get_all_constants() -> Dict[str, Any]:
    """Get all UI-relevant constants"""
    return {
        "success": True,
        "languages": SUPPORTED_LANGUAGES,
        "countries": ISO_COUNTRIES
    }


# Deprecated endpoints - kept for compatibility
@router.get("/metadata/languages")
async def get_supported_languages_legacy() -> Dict[str, Any]:
    """Get list of supported languages (legacy)"""
    return await get_supported_languages()


@router.get("/metadata/countries")
async def get_supported_countries() -> Dict[str, Any]:
    """Get list of supported countries with ISO codes (legacy)"""
    countries = [
        {"code": code, "name": name}
        for code, name in ISO_COUNTRIES.items()
    ]

    # Sort by name
    countries.sort(key=lambda x: x["name"])

    return {
        "success": True,
        "countries": countries
    }

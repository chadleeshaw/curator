"""
Application constants API endpoints.

Exposes configuration constants (languages, categories, countries, etc.) to the frontend.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter

from core.constants.app import MAX_DOWNLOAD_RETRIES
from core.constants.category import CATEGORIES
from core.constants.country import (
    ISO_COUNTRIES,
    LANGUAGE_TO_COUNTRY,
    COUNTRY_INDICATORS,
)
from core.constants.language import (
    SUPPORTED_LANGUAGES,
    LANGUAGE_KEYWORDS,
)

router = APIRouter(prefix="/api", tags=["metadata"])
logger = logging.getLogger(__name__)


@router.get("/constants/languages")
async def get_supported_languages() -> Dict[str, Any]:
    """Get list of supported languages"""
    return {"success": True, "languages": SUPPORTED_LANGUAGES}


@router.get("/constants/categories")
async def get_categories() -> Dict[str, Any]:
    """Get list of content categories"""
    return {"success": True, "categories": CATEGORIES}


@router.get("/constants/countries")
async def get_iso_countries() -> Dict[str, Any]:
    """Get ISO country codes and names"""
    return {"success": True, "countries": ISO_COUNTRIES}


@router.get("/constants")
async def get_all_constants() -> Dict[str, Any]:
    """Get all UI-relevant constants"""
    return {
        "success": True,
        "languages": SUPPORTED_LANGUAGES,
        "categories": CATEGORIES,
        "countries": ISO_COUNTRIES,
        "language_to_country": LANGUAGE_TO_COUNTRY,
        "country_indicators": COUNTRY_INDICATORS,
        "language_keywords": LANGUAGE_KEYWORDS,
        "max_download_retries": MAX_DOWNLOAD_RETRIES,
    }


# Deprecated endpoints - kept for compatibility
@router.get("/metadata/languages")
async def get_supported_languages_legacy() -> Dict[str, Any]:
    """Get list of supported languages (legacy)"""
    return await get_supported_languages()


@router.get("/metadata/countries")
async def get_supported_countries() -> Dict[str, Any]:
    """Get list of supported countries with ISO codes (legacy)"""
    countries = [{"code": code, "name": name} for code, name in ISO_COUNTRIES.items()]

    # Sort by name
    countries.sort(key=lambda x: x["name"])

    return {"success": True, "countries": countries}

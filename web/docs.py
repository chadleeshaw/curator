"""
API Documentation Configuration for Curator
"""

# API metadata and OpenAPI configuration
OPENAPI_METADATA = {
    "title": "Curator - Periodical Management System",
    "description": """
## Curator API

A comprehensive periodical management system for discovering, downloading, and organizing
magazines, comics, and newspapers.

### Features

* 🔍 **Multi-Provider Search** - Integrates with Newsnab APIs, and RSS feeds
* 📥 **Download Management** - Supports SABnzbd and NZBGet download clients
* 📚 **Smart Organization** - Automatic file organization with metadata enrichment
* 🎯 **Tracking System** - Monitor and automatically download specific periodicals
* 🔐 **Secure Authentication** - JWT-based authentication with secure password hashing
* 🚀 **Automated Tasks** - Background tasks for monitoring downloads and imports

### Authentication

Most endpoints require authentication. To get started:

1. Create initial credentials: `POST /api/auth/setup`
2. Login to get JWT token: `POST /api/auth/login`
3. Include token in requests: `Authorization: Bearer <token>`

### Quick Start

1. Set up credentials
2. Search for periodicals: `GET /api/search/periodicals`
3. Start tracking: `POST /api/tracking/start`
4. Download issues: `POST /api/downloads/all-issues`
5. Monitor progress: `GET /api/downloads/status/{tracking_id}`
    """,
    "version": "1.0.0",
    "contact": {
        "name": "Curator Support",
        "url": "https://github.com/chadleeshaw/curator",
    },
    "license_info": {
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
}

# OpenAPI tags for endpoint grouping
OPENAPI_TAGS = [
    {
        "name": "authentication",
        "description": "User authentication and credential management",
    },
    {
        "name": "search",
        "description": "Search for periodicals across multiple providers",
    },
    {
        "name": "tracking",
        "description": "Track periodicals for automatic downloads",
    },
    {
        "name": "downloads",
        "description": "Manage download submissions and monitor progress",
    },
    {
        "name": "periodicals",
        "description": "View and manage organized periodicals",
    },
    {
        "name": "imports",
        "description": "Import and organize downloaded files",
    },
    {
        "name": "config",
        "description": "Application configuration and settings",
    },
    {
        "name": "tasks",
        "description": "Background task management and monitoring",
    },
]

# Documentation URLs
DOCS_URLS = {
    "docs_url": "/api/docs",  # Swagger UI
    "redoc_url": "/api/redoc",  # ReDoc
    "openapi_url": "/api/openapi.json",
}

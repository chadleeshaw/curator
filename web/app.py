import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from core.auth import AuthManager
from core.config import ConfigLoader
from core.database import DatabaseManager
from core.factory import ClientFactory, ProviderFactory
from core.matching import TitleMatcher
from models.database import Magazine, MagazineTracking
from processor.download_manager import DownloadManager
from processor.download_monitor import DownloadMonitorTask
from processor.file_importer import FileImporter
from processor.organizer import FileProcessor
from processor.task_scheduler import TaskScheduler

# Import all routers
from web.routers import (
    auth,
    config,
    downloads,
    imports,
    pages,
    periodicals,
    search,
    tasks,
    tracking,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
config_loader = ConfigLoader()
storage_config = config_loader.get_storage()
matching_config = config_loader.get_matching()

# Initialize database
db_url = f"sqlite:///{storage_config.get('db_path', './data/periodicals.db')}"
db_manager = DatabaseManager(db_url)
db_manager.create_tables()
db_manager.run_migrations()
session_factory = db_manager.session_factory

# Initialize auth manager with JWT secret from config
jwt_secret = config_loader.get_jwt_secret()
auth_manager = AuthManager(session_factory, jwt_secret)

search_providers = []
metadata_providers = []
download_client = None
download_manager = None
download_monitor_task = None
title_matcher = None
file_processor = None
file_importer = None
task_scheduler = None
scheduler_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global download_client, download_manager, download_monitor_task, title_matcher, file_processor, file_importer, task_scheduler, scheduler_task

    # Startup
    try:
        # Initialize search providers (Newsnab, RSS)
        search_provider_configs = config_loader.get_search_providers()
        for provider_config in search_provider_configs:
            try:
                if not provider_config.get("type"):
                    logger.warning(f"Skipping provider with no type: {provider_config.get('name')}")
                    continue

                # Check if provider is properly configured
                provider_type = provider_config.get("type")
                if provider_type == "newsnab" and not provider_config.get("api_key"):
                    logger.warning("Skipping Newsnab provider: API key not configured")
                    continue
                elif provider_type == "rss" and not provider_config.get("feed_url"):
                    logger.warning("Skipping RSS provider: Feed URL not configured")
                    continue

                logger.debug(f"Creating search provider: {provider_config.get('name')} (type: {provider_type})")
                provider = ProviderFactory.create(provider_config)
                search_providers.append(provider)
                logger.info(f"Loaded search provider: {provider.name}")
            except Exception as e:
                logger.error(
                    f"Failed to load search provider {provider_config.get('name')}: {e}",
                    exc_info=True,
                )

        # Initialize metadata providers (CrossRef, Wikipedia)
        metadata_provider_configs = config_loader.get_metadata_providers()
        for provider_config in metadata_provider_configs:
            try:
                if not provider_config.get("type"):
                    logger.warning(f"Skipping metadata provider with no type: {provider_config.get('name')}")
                    continue

                logger.debug(
                    f"Creating metadata provider: {provider_config.get('name')} (type: {provider_config.get('type')})"
                )
                provider = ProviderFactory.create(provider_config)
                metadata_providers.append(provider)
                logger.info(f"Loaded metadata provider: {provider.name}")
            except Exception as e:
                logger.error(
                    f"Failed to load metadata provider {provider_config.get('name')}: {e}",
                    exc_info=True,
                )

        # Initialize download client (optional - can fail gracefully)
        try:
            client_config = config_loader.get_download_client()
            if not client_config.get("api_key"):
                logger.warning("Download client not available: API key not configured (configure in Settings)")
                download_client = None
            else:
                download_client = ClientFactory.create(client_config)
                logger.info(f"Loaded download client: {download_client.name}")
        except Exception as e:
            logger.warning(f"Download client not available (configure in Settings): {e}")
            download_client = None

        # Initialize other components
        title_matcher = TitleMatcher(matching_config.get("fuzzy_threshold", 80))
        file_processor = FileProcessor(storage_config.get("organize_dir", "./_Magazines"))
        file_importer = FileImporter(
            downloads_dir=storage_config.get("download_dir", "./downloads"),
            organize_base_dir=storage_config.get("organize_dir", "./_Magazines"),
            fuzzy_threshold=matching_config.get("fuzzy_threshold", 80),
            organization_pattern=storage_config.get("organization_pattern"),
        )

        # Initialize download manager (if download client is available)
        if download_client and search_providers:
            download_manager = DownloadManager(
                search_providers=search_providers,
                download_client=download_client,
                fuzzy_threshold=matching_config.get("fuzzy_threshold", 80),
            )
            logger.info("Download manager initialized")

            # Initialize download monitor task
            download_monitor_task = DownloadMonitorTask(
                download_manager=download_manager,
                file_importer=file_importer,
                session_factory=session_factory,
                downloads_dir=storage_config.get("download_dir", "./downloads"),
            )
            logger.info("Download monitor task initialized")
        else:
            logger.warning("Download manager not initialized: missing download client or search providers")

        # Initialize task scheduler
        task_scheduler = TaskScheduler()

        # Define auto-download task
        async def auto_download_task():
            """Search and download new issues for tracked periodicals every 30 minutes"""
            try:
                db_session = session_factory()
                try:
                    if download_manager:
                        logger.debug("Auto-download: Checking tracked periodicals for new issues")

                        # Get all tracked periodicals with any form of tracking enabled
                        tracked = (
                            db_session.query(MagazineTracking)
                            .filter(
                                (MagazineTracking.track_all_editions.is_(True))
                                | (MagazineTracking.track_new_only.is_(True))
                            )
                            .all()
                        )

                        # Also get periodicals with selected editions
                        tracked_with_selections = (
                            db_session.query(MagazineTracking)
                            .filter(MagazineTracking.selected_editions.isnot(None))
                            .all()
                        )

                        # Combine and deduplicate
                        all_tracked = {t.id: t for t in tracked}
                        for t in tracked_with_selections:
                            if t.id not in all_tracked and t.selected_editions:
                                # Check if any editions are actually selected (True values)
                                if any(t.selected_editions.values()):
                                    all_tracked[t.id] = t

                        if all_tracked:
                            logger.info(f"Auto-download: Found {len(all_tracked)} periodicals to check")

                            for periodical in all_tracked.values():
                                try:
                                    logger.debug(f"Auto-download: Checking '{periodical.title}' for new issues")

                                    # Determine which download method to use
                                    if periodical.track_all_editions or periodical.track_new_only:
                                        # Download all available issues
                                        results = download_manager.download_all_periodical_issues(
                                            periodical.id, db_session
                                        )
                                    elif periodical.selected_editions and any(periodical.selected_editions.values()):
                                        # Download only selected editions
                                        results = download_manager.download_selected_editions(periodical.id, db_session)
                                    else:
                                        continue

                                    if results.get("submitted", 0) > 0:
                                        logger.info(
                                            f"Auto-download: Submitted {results['submitted']} issues for '{periodical.title}'"
                                        )
                                except Exception as e:
                                    logger.error(f"Auto-download: Error checking '{periodical.title}': {e}")
                finally:
                    db_session.close()
            except Exception as e:
                logger.error(f"Auto-download error: {e}", exc_info=True)

        # Define download monitoring task
        async def download_monitoring_task():
            """Monitor download client and scan downloads folder for files to import (runs every 30 seconds)"""
            if download_monitor_task:
                try:
                    await download_monitor_task.run()
                except Exception as e:
                    logger.error(f"Download monitoring error: {e}", exc_info=True)

        # Define cover cleanup task
        async def cleanup_orphaned_covers_task():
            """Clean up cover files that aren't tied to any periodical (runs every 24 hours)"""
            try:
                db_session = session_factory()
                try:
                    # Get all covers in the database
                    periodicals = db_session.query(Magazine).filter(Magazine.cover_path is not None).all()
                    db_cover_paths = {m.cover_path for m in periodicals if m.cover_path}

                    # Find all cover files on disk
                    covers_dir = Path(storage_config.get("organize_base_dir", "./local/data")) / ".covers"
                    if covers_dir.exists():
                        cover_files = set(str(f) for f in covers_dir.glob("*.jpg"))

                        # Find orphaned covers (files that exist on disk but not in DB)
                        orphaned_covers = cover_files - db_cover_paths

                        # Delete orphaned covers
                        deleted_count = 0
                        for orphan_path in orphaned_covers:
                            try:
                                Path(orphan_path).unlink()
                                deleted_count += 1
                                logger.debug(f"Deleted orphaned cover: {orphan_path}")
                            except Exception as e:
                                logger.error(f"Error deleting orphaned cover {orphan_path}: {e}")

                        if deleted_count > 0:
                            logger.info(f"Cleanup covers: Deleted {deleted_count} orphaned cover files")
                    else:
                        logger.debug("Covers directory does not exist yet")
                finally:
                    db_session.close()
            except Exception as e:
                logger.error(f"Cover cleanup error: {e}", exc_info=True)

        # Schedule auto-download every 30 minutes (1800 seconds)
        task_scheduler.schedule_periodic("auto_download", auto_download_task, 1800)

        # Schedule download monitoring every 30 seconds
        task_scheduler.schedule_periodic("download_monitor", download_monitoring_task, 30)

        # Schedule cover cleanup every 24 hours (86400 seconds)
        task_scheduler.schedule_periodic("cleanup_orphaned_covers", cleanup_orphaned_covers_task, 86400)

        # Start scheduler in background
        scheduler_task = asyncio.create_task(task_scheduler.start())

        # Initialize router dependencies
        auth.set_auth_manager(auth_manager)
        search.set_dependencies(search_providers, metadata_providers, title_matcher, session_factory)
        periodicals.set_dependencies(session_factory)
        tracking.set_dependencies(session_factory, search_providers)
        downloads.set_dependencies(session_factory, download_manager, download_client)
        imports.set_dependencies(session_factory, file_importer, storage_config)
        tasks.set_dependencies(session_factory, download_monitor_task, file_importer, storage_config)
        config.set_dependencies(config_loader)
        pages.set_dependencies(session_factory)

        logger.info("Curator initialized successfully with auto-import and download monitoring enabled")

    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

    yield

    # Shutdown
    try:
        if task_scheduler:
            task_scheduler.stop()
            logger.info("Task scheduler stopped")

        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass

        logger.info("Curator shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Initialize FastAPI app with comprehensive documentation
app = FastAPI(
    title="Curator - Periodical Management System",
    description="""
## Curator API

A comprehensive periodical management system for discovering, downloading, and organizing
magazines, comics, and newspapers.

### Features

* 🔍 **Multi-Provider Search** - Integrates with Newsnab APIs, RSS feeds, CrossRef, and Wikipedia
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
    version="1.0.0",
    contact={
        "name": "Curator Support",
        "url": "https://github.com/chadleeshaw/curator",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
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
    ],
    lifespan=lifespan,
    docs_url="/api/docs",  # Swagger UI
    redoc_url="/api/redoc",  # ReDoc
    openapi_url="/api/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
from web.middleware import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    calls=60,  # 60 calls per minute for regular endpoints
    period=60,
    auth_calls=10,  # 10 calls per minute for auth endpoints
    auth_period=60,
)


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Docker and monitoring"""
    try:
        # Test database connectivity
        session = session_factory()
        try:
            # Simple query to verify DB is accessible
            session.execute(text("SELECT 1"))
            session.commit()
            db_status = "connected"
        except Exception as e:
            logger.error(f"Health check database error: {e}")
            db_status = "error"
            return {
                "status": "unhealthy",
                "service": "curator",
                "database": db_status,
            }, 503
        finally:
            session.close()

        return {"status": "healthy", "service": "curator", "database": db_status}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "service": "curator", "error": str(e)}, 503


@app.get("/api/status")
async def get_status():
    """Get manager status"""
    return {
        "status": "running",
        "providers": [p.get_provider_info() for p in search_providers],
        "download_client": (download_client.get_client_info() if download_client else None),
    }


# Include all routers
# Note: tracking must come before periodicals to avoid route conflicts
# (/periodicals/tracking must match before /periodicals/{magazine_id})
app.include_router(auth.router)
app.include_router(search.router)
app.include_router(tracking.router)
app.include_router(periodicals.router)
app.include_router(downloads.router)
app.include_router(imports.router)
app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(pages.router)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)

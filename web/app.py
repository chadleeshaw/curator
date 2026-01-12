import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from core.auth import AuthManager
from core.config import ConfigLoader
from core import constants
from core.database import DatabaseManager
from core.factory import ClientFactory, ProviderFactory
from core.parsers import TitleMatcher
from models.database import MagazineTracking
from services import DownloadManager, FileImporter, FileOrganizer
from scheduler import TaskScheduler, DownloadMonitorTask, CoverCleanupTask, OCRProcessorTask, OCRCoverGeneratorTask

# Import all routers
from web.routers import (
    auth,
    config,
    downloads,
    imports,
    metadata,
    ocr_queue,
    pages,
    periodicals,
    search,
    tasks,
    tracking,
)

# Import documentation configuration
from web.docs import OPENAPI_METADATA, OPENAPI_TAGS, DOCS_URLS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
config_loader = ConfigLoader()
storage_config = config_loader.get_storage()
matching_config = config_loader.get_matching()
pdf_config = config_loader.get_pdf()
downloads_config = config_loader.get_downloads()
tasks_config = config_loader.get_tasks()

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
cover_cleanup_task = None
ocr_cover_generator_task = None
title_matcher = None
file_processor = None
file_importer = None
task_scheduler = None
scheduler_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global download_client, download_manager, download_monitor_task, cover_cleanup_task, ocr_cover_generator_task, title_matcher, file_processor, file_importer, task_scheduler, scheduler_task

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
        fuzzy_threshold = matching_config.get("fuzzy_threshold")
        import_config = config_loader.get_import()
        category_prefix = import_config.get("category_prefix", "_")
        title_matcher = TitleMatcher(fuzzy_threshold)
        file_processor = FileOrganizer(
            storage_config.get("organize_dir", "./_Magazines"), category_prefix=category_prefix
        )
        file_importer = FileImporter(
            downloads_dir=storage_config.get("download_dir", "./downloads"),
            organize_base_dir=storage_config.get("organize_dir", "./_Magazines"),
            fuzzy_threshold=fuzzy_threshold,
            organization_pattern=import_config.get("organization_pattern"),
            category_prefix=category_prefix,
            enable_text_scan=import_config.get("enable_text_scan", True),
        )

        # Initialize download manager (if download client is available)
        if download_client and search_providers:
            download_manager = DownloadManager(
                search_providers=search_providers,
                download_client=download_client,
                fuzzy_threshold=fuzzy_threshold,
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

        # Initialize cover cleanup task
        cover_cleanup_task = CoverCleanupTask(
            session_factory=session_factory,
            organize_base_dir=storage_config.get("organize_dir", "./_Magazines"),
            file_importer=file_importer,
        )
        logger.info("Cover cleanup task initialized")

        # Initialize OCR cover generator task
        ocr_cover_generator_task = OCRCoverGeneratorTask(
            session_factory=session_factory,
            organize_base_dir=storage_config.get("organize_dir", "./_Magazines"),
            config_loader=config_loader,
        )
        logger.info("OCR cover generator task initialized")

        # Initialize OCR processor task
        ocr_processor_task = OCRProcessorTask(
            session_factory=session_factory,
            config_loader=config_loader,
            max_workers=tasks_config.get("ocr_max_workers", 3),
            batch_size=tasks_config.get("ocr_batch_size", 10)
        )
        logger.info("OCR processor task initialized")

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

                        # Check how many downloads are currently pending or downloading
                        from models.database import Download

                        pending_count = (
                            db_session.query(Download)
                            .filter(Download.status.in_([Download.StatusEnum.PENDING, Download.StatusEnum.DOWNLOADING]))
                            .count()
                        )

                        if pending_count >= constants.MAX_DOWNLOADS_PER_BATCH:
                            logger.info(
                                f"Auto-download: Skipping - already at max downloads ({pending_count}/{constants.MAX_DOWNLOADS_PER_BATCH})"
                            )
                            return

                        remaining_slots = constants.MAX_DOWNLOADS_PER_BATCH - pending_count
                        logger.info(
                            f"Auto-download: {remaining_slots} download slots available ({pending_count} already queued)"
                        )

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
                    from datetime import datetime, timedelta
                    
                    # Update next run time before execution
                    interval = tasks_config.get("download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL)
                    download_monitor_task.next_run_time = datetime.now() + timedelta(seconds=interval)
                    
                    await download_monitor_task.run()
                except Exception as e:
                    logger.error(f"Download monitoring error: {e}", exc_info=True)

        # Define cover cleanup task wrapper
        async def cleanup_orphaned_covers_task():
            """Clean up cover files that aren't tied to any periodical and generate missing covers (runs every hour)"""
            await cover_cleanup_task.run()

        # Define OCR cover generator task wrapper
        async def ocr_cover_generator_task_wrapper():
            """Generate high-res PNG covers for OCR and clean up orphaned files (runs every 5 minutes)"""
            try:
                stats = await ocr_cover_generator_task.run()
                if stats.get("generated_count", 0) > 0 or stats.get("deleted_orphaned", 0) > 0 or stats.get("deleted_completed", 0) > 0:
                    logger.info(f"OCR cover generator: {stats}")
            except Exception as e:
                logger.error(f"OCR cover generator error: {e}", exc_info=True)

        # Define OCR processor task wrapper
        async def ocr_processing_task():
            """Process queued OCR jobs with process pool (runs every hour)"""
            try:
                from datetime import datetime, timedelta
                
                # Update next run time before execution
                interval = tasks_config.get("ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL)
                ocr_processor_task.next_run_time = datetime.now() + timedelta(seconds=interval)
                
                stats = await ocr_processor_task.run()
                if stats.get("processed", 0) > 0:
                    logger.info(f"OCR processor: {stats}")
            except Exception as e:
                logger.error(f"OCR processor error: {e}", exc_info=True)

        # Schedule tasks with intervals from config
        task_scheduler.schedule_periodic(
            "auto_download", auto_download_task, tasks_config.get("auto_download_interval", constants.AUTO_DOWNLOAD_INTERVAL)
        )

        task_scheduler.schedule_periodic(
            "download_monitor", download_monitoring_task, tasks_config.get("download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL)
        )

        task_scheduler.schedule_periodic(
            "cleanup_orphaned_covers", cleanup_orphaned_covers_task, tasks_config.get("cleanup_covers_interval", constants.CLEANUP_COVERS_INTERVAL)
        )

        task_scheduler.schedule_periodic(
            "ocr_cover_generator", ocr_cover_generator_task_wrapper, tasks_config.get("ocr_cover_generator_interval", constants.OCR_COVER_GENERATOR_INTERVAL)
        )

        task_scheduler.schedule_periodic(
            "ocr_processor", ocr_processing_task, tasks_config.get("ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL)
        )

        # Start scheduler in background
        scheduler_task = asyncio.create_task(task_scheduler.start())

        # Initialize router dependencies
        auth.set_auth_manager(auth_manager)
        search.set_dependencies(search_providers, metadata_providers, title_matcher, session_factory)
        periodicals.set_dependencies(session_factory)
        tracking.set_dependencies(session_factory, search_providers, auto_download_task)
        downloads.set_dependencies(session_factory, download_manager, download_client)
        imports.set_dependencies(session_factory, file_importer, storage_config)
        tasks.set_dependencies(session_factory, download_monitor_task, file_importer, storage_config, ocr_processor_task, task_scheduler)
        config.set_dependencies(config_loader)
        pages.set_dependencies(session_factory)
        ocr_queue.set_dependencies(session_factory)

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

        # Shutdown OCR processor
        if ocr_processor_task:
            ocr_processor_task.shutdown()
            logger.info("OCR processor shutdown complete")

        logger.info("Curator shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Initialize FastAPI app with comprehensive documentation
app = FastAPI(
    **OPENAPI_METADATA,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
    **DOCS_URLS,
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
app.include_router(metadata.router)
app.include_router(search.router)
app.include_router(tracking.router)
app.include_router(periodicals.router)
app.include_router(downloads.router)
app.include_router(imports.router)
app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(pages.router)
app.include_router(ocr_queue.router)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)

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
from core.factories import ClientFactory, ProviderFactory
from core.parsers import TitleMatcher
from services import (
    DownloadManager,
    FileImporter,
    FileOrganizer,
    IssueDiscoveryService,
    SearchScheduler,
)
from tasks import (
    TaskScheduler,
    DownloadMonitor,
    CoverCleanup,
    OCRProcessor,
    FolderCleanup,
)

# Import all routers
from web.routers import (
    auth,
    config,
    discovery,
    downloads,
    imports,
    constants_router,
    ocr_queue,
    pages,
    periodicals,
    search,
    tasks,
    tracking,
)
from web.middleware.auth import AuthMiddleware

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
import_config = config_loader.get_import()

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
title_matcher = None
file_processor = None
file_importer = None
task_scheduler = None
scheduler_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global \
        download_client, \
        download_manager, \
        download_monitor_task, \
        cover_cleanup_task, \
        title_matcher, \
        file_processor, \
        file_importer, \
        task_scheduler, \
        scheduler_task

    # Startup
    try:
        # Initialize search providers (Newsnab, RSS)
        search_provider_configs = config_loader.get_search_providers()
        for provider_config in search_provider_configs:
            try:
                if not provider_config.get("type"):
                    logger.warning(
                        f"Skipping provider with no type: {provider_config.get('name')}"
                    )
                    continue

                # Check if provider is properly configured
                provider_type = provider_config.get("type")
                if provider_type == "newsnab" and not provider_config.get("api_key"):
                    logger.warning("Skipping Newsnab provider: API key not configured")
                    continue
                elif provider_type == "rss" and not provider_config.get("feed_url"):
                    logger.warning("Skipping RSS provider: Feed URL not configured")
                    continue

                logger.debug(
                    f"Creating search provider: {provider_config.get('name')} (type: {provider_type})"
                )
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
                logger.warning(
                    "Download client not available: API key not configured (configure in Settings)"
                )
                download_client = None
            else:
                download_client = ClientFactory.create(client_config)
                logger.info(f"Loaded download client: {download_client.name}")
        except Exception as e:
            logger.warning(
                f"Download client not available (configure in Settings): {e}"
            )
            download_client = None

        # Initialize other components
        fuzzy_threshold = matching_config.get("fuzzy_threshold")
        import_config = config_loader.get_import()
        category_prefix = import_config.get("category_prefix", "_")
        title_matcher = TitleMatcher(fuzzy_threshold)
        file_processor = FileOrganizer(
            storage_config.get("organize_dir", "./_Magazines"),
            category_prefix=category_prefix,
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
                max_downloads=downloads_config.get("max_concurrent", 10),
            )
            logger.info("Download manager initialized")

            # Initialize download monitor task
            download_monitor_task = DownloadMonitor(
                download_manager=download_manager,
                file_importer=file_importer,
                session_factory=session_factory,
                downloads_dir=storage_config.get("download_dir", "./downloads"),
            )
            logger.info("Download monitor task initialized")
        else:
            logger.warning(
                "Download manager not initialized: missing download client or search providers"
            )

        # Initialize cover cleanup task
        cover_cleanup_task = CoverCleanup(
            session_factory=session_factory,
            organize_base_dir=storage_config.get("organize_dir", "./_Magazines"),
            file_importer=file_importer,
        )
        logger.info("Cover cleanup task initialized")

        # Initialize OCR processor task
        ocr_processor_task = OCRProcessor(
            session_factory=session_factory,
            config_loader=config_loader,
            max_workers=tasks_config.get("ocr_max_workers", constants.OCR_MAX_WORKERS),
            batch_size=tasks_config.get("ocr_batch_size", constants.OCR_BATCH_SIZE),
        )
        logger.info("OCR processor task initialized")

        # Initialize folder cleanup task
        folder_cleanup_task = FolderCleanup(
            downloads_dir=storage_config.get("download_dir", "./local/downloads"),
            organized_dir=storage_config.get("organize_dir", "./_Magazines"),
            dry_run=False,  # Set to True for testing
        )
        logger.info("Folder cleanup task initialized")

        # Initialize Issue Discovery services
        issue_discovery_service = IssueDiscoveryService(
            fuzzy_threshold=fuzzy_threshold,
            default_max_retries=downloads_config.get("max_retries", 1),
        )
        search_scheduler = SearchScheduler(
            max_periodicals_per_run=tasks_config.get("max_periodicals_per_search", 2),
            rapid_interval_hours=tasks_config.get("rapid_search_interval", 1),
            normal_interval_hours=tasks_config.get("normal_search_interval", 6),
            slow_interval_hours=tasks_config.get("slow_search_interval", 24),
            very_slow_interval_hours=tasks_config.get("very_slow_search_interval", 168),
        )
        logger.info("Issue discovery services initialized")

        # Initialize task scheduler
        task_scheduler = TaskScheduler()

        # Define auto-download task (NEW: uses Issue Discovery & Tracking system)
        async def auto_download_task():
            """
            Adaptive search and download for tracked periodicals.

            New behavior:
            - Searches 1-2 periodicals per run (not ALL) using adaptive scheduling
            - Records discovered issues in DiscoveredIssue table
            - Evaluates issues against tracking rules
            - Downloads from priority queue
            """
            try:
                db_session = session_factory()
                try:
                    if not download_manager:
                        return

                    logger.debug(
                        "Auto-download: Starting Issue Discovery & Tracking run"
                    )

                    # Phase 1: Select periodicals to search (adaptive scheduling)
                    periodicals_to_search = (
                        search_scheduler.select_periodicals_to_search(db_session)
                    )

                    if not periodicals_to_search:
                        logger.debug(
                            "Auto-download: No periodicals need searching at this time"
                        )
                        return

                    logger.info(
                        f"Auto-download: Selected {len(periodicals_to_search)} periodicals to search: "
                        f"{[p.title for p in periodicals_to_search]}"
                    )

                    # Phase 2: Search each selected periodical and record results
                    for periodical in periodicals_to_search:
                        try:
                            logger.debug(
                                f"Auto-download: Searching for '{periodical.title}'"
                            )

                            # Search all providers for this periodical
                            search_results = download_manager.search_periodical_issues(
                                periodical.title, db_session
                            )

                            if not search_results:
                                logger.debug(
                                    f"Auto-download: No results found for '{periodical.title}'"
                                )
                                # Update stats with 0 new issues
                                search_scheduler.update_search_stats(
                                    periodical.id, 0, db_session
                                )
                                continue

                            logger.debug(
                                f"Auto-download: Found {len(search_results)} search results for '{periodical.title}'"
                            )

                            # Record search results as discovered issues
                            record_stats = (
                                issue_discovery_service.record_search_results(
                                    periodical.id, search_results, db_session
                                )
                            )

                            # Only log if we found NEW issues (not just updated existing ones)
                            if record_stats["new"] > 0:
                                logger.info(
                                    f"Auto-download: '{periodical.title}' - {record_stats['new']} new issues discovered"
                                )

                            # Evaluate discovered issues against tracking rules
                            eval_stats = (
                                issue_discovery_service.evaluate_discovered_issues(
                                    periodical.id, db_session
                                )
                            )

                            # Only log evaluation if we have wanted issues
                            if eval_stats["wanted"] > 0:
                                logger.info(
                                    f"Auto-download: '{periodical.title}' - {eval_stats['wanted']} issues queued for download"
                                )

                            # Update search statistics (for adaptive scheduling)
                            search_scheduler.update_search_stats(
                                periodical.id, record_stats["new"], db_session
                            )

                        except Exception as e:
                            logger.error(
                                f"Auto-download: Error processing '{periodical.title}': {e}",
                                exc_info=True,
                            )

                    # Phase 3: Download from priority queue
                    logger.debug("Auto-download: Checking download queue")

                    # Check how many downloads are currently pending or downloading
                    from models.database import DownloadSubmission

                    pending_count = (
                        db_session.query(DownloadSubmission)
                        .filter(
                            DownloadSubmission.status.in_(
                                [
                                    DownloadSubmission.StatusEnum.PENDING,
                                    DownloadSubmission.StatusEnum.DOWNLOADING,
                                ]
                            )
                        )
                        .count()
                    )

                    remaining_slots = max(
                        0, download_manager.max_downloads - pending_count
                    )
                    logger.debug(
                        f"Auto-download: {remaining_slots} download slots available ({pending_count} in progress)"
                    )

                    if remaining_slots > 0:
                        # Get top priority issues from queue
                        download_queue = issue_discovery_service.get_download_queue(
                            db_session, limit=remaining_slots
                        )

                        if download_queue:
                            logger.info(
                                f"Auto-download: Submitting {len(download_queue)} issues for download"
                            )

                            submitted_count = 0
                            for issue in download_queue:
                                try:
                                    # Submit download using new method
                                    submission = (
                                        download_manager.submit_from_discovered_issue(
                                            issue.id, db_session
                                        )
                                    )

                                    if submission:
                                        submitted_count += 1
                                        logger.info(
                                            f"Auto-download: Submitted '{issue.title}' "
                                            f"(priority {issue.download_priority}, job_id: {submission.job_id})"
                                        )
                                    else:
                                        logger.debug(
                                            f"Auto-download: Could not submit '{issue.title}' "
                                            f"(may be at limit or already queued)"
                                        )

                                except Exception as e:
                                    logger.error(
                                        f"Auto-download: Error submitting download for '{issue.title}': {e}",
                                        exc_info=True,
                                    )

                            if submitted_count > 0:
                                logger.info(
                                    f"Auto-download: Successfully submitted {submitted_count} downloads"
                                )

                    logger.debug(
                        "Auto-download: Completed Issue Discovery & Tracking run"
                    )

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
                    interval = tasks_config.get(
                        "download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL
                    )
                    download_monitor_task.next_run_time = datetime.now() + timedelta(
                        seconds=interval
                    )

                    await download_monitor_task.run()
                except Exception as e:
                    logger.error(f"Download monitoring error: {e}", exc_info=True)

        # Define cover cleanup task wrapper
        async def cleanup_orphaned_covers_task():
            """Clean up cover files that aren't tied to any periodical and generate missing covers (runs every hour)"""
            await cover_cleanup_task.run()

        # Define OCR processor task wrapper
        async def ocr_processing_task():
            """Process queued OCR jobs with process pool (runs every hour)"""
            try:
                from datetime import datetime, timedelta

                # Update next run time before execution
                interval = tasks_config.get(
                    "ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL
                )
                ocr_processor_task.next_run_time = datetime.now() + timedelta(
                    seconds=interval
                )

                stats = await ocr_processor_task.run()
                if stats.get("processed", 0) > 0:
                    logger.info(f"OCR processor: {stats}")
            except Exception as e:
                logger.error(f"OCR processor error: {e}", exc_info=True)

        # Define folder cleanup task wrapper
        async def folder_cleanup_periodic_task():
            """Clean up empty folders and folders without importable files (runs daily)"""
            try:
                import asyncio

                # Run in thread pool since it's CPU-bound and has file I/O
                loop = asyncio.get_event_loop()
                stats = await loop.run_in_executor(None, folder_cleanup_task.run)
                if stats.get("total_deleted", 0) > 0:
                    logger.info(f"Folder cleanup: {stats}")
            except Exception as e:
                logger.error(f"Folder cleanup error: {e}", exc_info=True)

        # Schedule tasks with intervals from config
        task_scheduler.schedule_periodic(
            "auto_download",
            auto_download_task,
            tasks_config.get(
                "auto_download_interval", constants.AUTO_DOWNLOAD_INTERVAL
            ),
        )

        task_scheduler.schedule_periodic(
            "download_monitor",
            download_monitoring_task,
            tasks_config.get(
                "download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL
            ),
        )

        task_scheduler.schedule_periodic(
            "cleanup_orphaned_covers",
            cleanup_orphaned_covers_task,
            tasks_config.get(
                "cleanup_covers_interval", constants.CLEANUP_COVERS_INTERVAL
            ),
        )

        task_scheduler.schedule_periodic(
            "ocr_processor",
            ocr_processing_task,
            tasks_config.get(
                "ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL
            ),
        )

        task_scheduler.schedule_periodic(
            "folder_cleanup",
            folder_cleanup_periodic_task,
            tasks_config.get(
                "folder_cleanup_interval",
                86400,  # Default: once per day (24 hours)
            ),
        )

        # Start scheduler in background
        scheduler_task = asyncio.create_task(task_scheduler.start())

        # Initialize router dependencies
        # Set auth manager and middleware in app state for FastAPI dependency injection
        app.state.auth_manager = auth_manager
        app.state.auth_middleware = AuthMiddleware(auth_manager)
        search.set_dependencies(
            search_providers, metadata_providers, title_matcher, session_factory
        )
        periodicals.set_dependencies(
            session_factory, storage_config.get("organize_dir", "./")
        )
        tracking.set_dependencies(
            session_factory,
            search_providers,
            auto_download_task,
            storage_config,
            import_config,
        )
        downloads.set_dependencies(session_factory, download_manager, download_client)
        imports.set_dependencies(session_factory, file_importer, storage_config)
        tasks.set_dependencies(
            session_factory,
            download_monitor_task,
            file_importer,
            storage_config,
            ocr_processor_task,
            task_scheduler,
            folder_cleanup_task,
        )
        config.set_dependencies(config_loader)
        pages.set_dependencies(session_factory)
        ocr_queue.set_dependencies(session_factory)
        discovery.set_dependencies(
            session_factory,
            issue_discovery_service,
            search_scheduler,
        )

        logger.info(
            "Curator initialized successfully with auto-import and download monitoring enabled"
        )

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
        "download_client": (
            download_client.get_client_info() if download_client else None
        ),
    }


# Include all routers
# Note: tracking must come before periodicals to avoid route conflicts
# (/periodicals/tracking must match before /periodicals/{magazine_id})
app.include_router(auth.router)
app.include_router(constants_router.router)
app.include_router(search.router)
app.include_router(tracking.router)
app.include_router(periodicals.router)
app.include_router(downloads.router)
app.include_router(imports.router)
app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(pages.router)
app.include_router(ocr_queue.router)
app.include_router(discovery.router)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

if __name__ == "__main__":
    import uvicorn

    server_config = config_loader.get_server()
    uvicorn.run(
        app, host=server_config["host"], port=server_config["port"], access_log=False
    )

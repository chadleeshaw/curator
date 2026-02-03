"""
Main FastAPI application module.
"""

# pylint: disable=too-many-lines
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
from schedulers import (
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


@dataclass
class ConfigState:
    """Configuration state loaded from config file."""

    loader: ConfigLoader
    storage: Dict[str, Any] = field(default_factory=dict)
    cache: Dict[str, Any] = field(default_factory=dict)
    matching: Dict[str, Any] = field(default_factory=dict)
    pdf: Dict[str, Any] = field(default_factory=dict)
    downloads: Dict[str, Any] = field(default_factory=dict)
    tasks: Dict[str, Any] = field(default_factory=dict)
    import_: Dict[str, Any] = field(default_factory=dict)  # 'import' is reserved


@dataclass
class DatabaseState:
    """Database connection state."""

    url: str
    manager: DatabaseManager
    session_factory: Any  # sessionmaker


@dataclass
class ProviderState:
    """Search and metadata provider instances."""

    search: List[Any] = field(default_factory=list)
    metadata: List[Any] = field(default_factory=list)


@dataclass
class ServiceState:
    """Application service instances (initialized during lifespan)."""

    download_client: Optional[Any] = None
    download_clients: Dict[str, Any] = field(default_factory=dict)  # Additional clients by type
    download_manager: Optional[DownloadManager] = None
    title_matcher: Optional[TitleMatcher] = None
    file_processor: Optional[FileOrganizer] = None
    file_importer: Optional[FileImporter] = None
    provider_cache_service: Optional[Any] = None
    provider_sync_service: Optional[Any] = None
    issue_discovery_service: Optional[IssueDiscoveryService] = None
    search_scheduler: Optional[SearchScheduler] = None


@dataclass
class TaskState:
    """Background task state (initialized during lifespan)."""

    scheduler: Optional[TaskScheduler] = None
    scheduler_task: Optional[Any] = None  # asyncio.Task
    download_monitor: Optional[DownloadMonitor] = None
    cover_cleanup: Optional[CoverCleanup] = None
    ocr_processor: Optional[OCRProcessor] = None
    folder_cleanup: Optional[FolderCleanup] = None


# pylint: disable=too-many-instance-attributes,too-many-public-methods
class AppState:
    """
    Centralized application state container.

    Encapsulates all mutable application state that was previously stored in
    module-level globals. This improves:
    - Testability: State can be easily reset or mocked
    - Clarity: All state is in one place with clear initialization
    - Safety: Easier to track what's initialized and when

    State is organized into nested dataclasses by category:
    - config: Configuration loaded from file
    - db: Database connection and session factory
    - providers: Search and metadata providers
    - services: Application services (file processing, downloads, etc.)
    - tasks: Background task handlers and scheduler
    """

    def __init__(self):
        # === Config (loaded immediately) ===
        loader = ConfigLoader()
        self.config = ConfigState(
            loader=loader,
            storage=loader.get_storage(),
            cache=loader.get_cache(),
            matching=loader.get_matching(),
            pdf=loader.get_pdf(),
            downloads=loader.get_downloads(),
            tasks=loader.get_tasks(),
            import_=loader.get_import(),
        )

        # === Database (initialized immediately) ===
        db_path = self.config.storage.get("db_path", "./data/periodicals.db")
        db_url = f"sqlite:///{db_path}"
        db_manager = DatabaseManager(db_url)
        db_manager.create_tables()
        db_manager.run_migrations()
        self.db = DatabaseState(
            url=db_url,
            manager=db_manager,
            session_factory=db_manager.session_factory,
        )

        # === Auth (initialized immediately) ===
        jwt_secret = self.config.loader.get_jwt_secret()
        self.auth_manager = AuthManager(self.db.session_factory, jwt_secret)

        # === Providers (populated during lifespan) ===
        self.providers = ProviderState()

        # === Services (initialized during lifespan) ===
        self.services = ServiceState()

        # === Background tasks (created during lifespan) ===
        self.tasks = TaskState()

        # === Additional download clients (populated during lifespan) ===
        self.download_clients: Dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # Backward compatibility properties - map old flat attributes to nested ones
    # -------------------------------------------------------------------------

    @property
    def config_loader(self) -> ConfigLoader:
        """Backward compatibility: access config.loader as config_loader."""
        return self.config.loader

    @property
    def storage_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.storage as storage_config."""
        return self.config.storage

    @property
    def cache_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.cache as cache_config."""
        return self.config.cache

    @property
    def matching_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.matching as matching_config."""
        return self.config.matching

    @property
    def pdf_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.pdf as pdf_config."""
        return self.config.pdf

    @property
    def downloads_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.downloads as downloads_config."""
        return self.config.downloads

    @property
    def tasks_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.tasks as tasks_config."""
        return self.config.tasks

    @property
    def import_config(self) -> Dict[str, Any]:
        """Backward compatibility: access config.import_ as import_config."""
        return self.config.import_

    @property
    def db_url(self) -> str:
        """Backward compatibility: access db.url as db_url."""
        return self.db.url

    @property
    def db_manager(self) -> DatabaseManager:
        """Backward compatibility: access db.manager as db_manager."""
        return self.db.manager

    @property
    def session_factory(self) -> Any:
        """Backward compatibility: access db.session_factory as session_factory."""
        return self.db.session_factory

    @property
    def search_providers(self) -> List[Any]:
        """Backward compatibility: access providers.search as search_providers."""
        return self.providers.search

    @property
    def metadata_providers(self) -> List[Any]:
        """Backward compatibility: access providers.metadata as metadata_providers."""
        return self.providers.metadata

    @property
    def download_client(self) -> Optional[Any]:
        """Backward compatibility: access services.download_client."""
        return self.services.download_client

    @download_client.setter
    def download_client(self, value: Any) -> None:
        """Backward compatibility: set services.download_client."""
        self.services.download_client = value

    @property
    def download_manager(self) -> Optional[DownloadManager]:
        """Backward compatibility: access services.download_manager."""
        return self.services.download_manager

    @download_manager.setter
    def download_manager(self, value: DownloadManager) -> None:
        """Backward compatibility: set services.download_manager."""
        self.services.download_manager = value

    @property
    def title_matcher(self) -> Optional[TitleMatcher]:
        """Backward compatibility: access services.title_matcher."""
        return self.services.title_matcher

    @title_matcher.setter
    def title_matcher(self, value: TitleMatcher) -> None:
        """Backward compatibility: set services.title_matcher."""
        self.services.title_matcher = value

    @property
    def file_processor(self) -> Optional[FileOrganizer]:
        """Backward compatibility: access services.file_processor."""
        return self.services.file_processor

    @file_processor.setter
    def file_processor(self, value: FileOrganizer) -> None:
        """Backward compatibility: set services.file_processor."""
        self.services.file_processor = value

    @property
    def file_importer(self) -> Optional[FileImporter]:
        """Backward compatibility: access services.file_importer."""
        return self.services.file_importer

    @file_importer.setter
    def file_importer(self, value: FileImporter) -> None:
        """Backward compatibility: set services.file_importer."""
        self.services.file_importer = value

    @property
    def provider_cache_service(self) -> Optional[Any]:
        """Backward compatibility: access services.provider_cache_service."""
        return self.services.provider_cache_service

    @provider_cache_service.setter
    def provider_cache_service(self, value: Any) -> None:
        """Backward compatibility: set services.provider_cache_service."""
        self.services.provider_cache_service = value

    @property
    def provider_sync_service(self) -> Optional[Any]:
        """Backward compatibility: access services.provider_sync_service."""
        return self.services.provider_sync_service

    @provider_sync_service.setter
    def provider_sync_service(self, value: Any) -> None:
        """Backward compatibility: set services.provider_sync_service."""
        self.services.provider_sync_service = value

    @property
    def issue_discovery_service(self) -> Optional[IssueDiscoveryService]:
        """Backward compatibility: access services.issue_discovery_service."""
        return self.services.issue_discovery_service

    @issue_discovery_service.setter
    def issue_discovery_service(self, value: IssueDiscoveryService) -> None:
        """Backward compatibility: set services.issue_discovery_service."""
        self.services.issue_discovery_service = value

    @property
    def search_scheduler(self) -> Optional[SearchScheduler]:
        """Backward compatibility: access services.search_scheduler."""
        return self.services.search_scheduler

    @search_scheduler.setter
    def search_scheduler(self, value: SearchScheduler) -> None:
        """Backward compatibility: set services.search_scheduler."""
        self.services.search_scheduler = value

    @property
    def task_scheduler(self) -> Optional[TaskScheduler]:
        """Backward compatibility: access tasks.scheduler."""
        return self.tasks.scheduler

    @task_scheduler.setter
    def task_scheduler(self, value: TaskScheduler) -> None:
        """Backward compatibility: set tasks.scheduler."""
        self.tasks.scheduler = value

    @property
    def scheduler_task(self) -> Optional[Any]:
        """Backward compatibility: access tasks.scheduler_task."""
        return self.tasks.scheduler_task

    @scheduler_task.setter
    def scheduler_task(self, value: Any) -> None:
        """Backward compatibility: set tasks.scheduler_task."""
        self.tasks.scheduler_task = value

    @property
    def download_monitor_task(self) -> Optional[DownloadMonitor]:
        """Backward compatibility: access tasks.download_monitor."""
        return self.tasks.download_monitor

    @download_monitor_task.setter
    def download_monitor_task(self, value: DownloadMonitor) -> None:
        """Backward compatibility: set tasks.download_monitor."""
        self.tasks.download_monitor = value

    @property
    def cover_cleanup_task(self) -> Optional[CoverCleanup]:
        """Backward compatibility: access tasks.cover_cleanup."""
        return self.tasks.cover_cleanup

    @cover_cleanup_task.setter
    def cover_cleanup_task(self, value: CoverCleanup) -> None:
        """Backward compatibility: set tasks.cover_cleanup."""
        self.tasks.cover_cleanup = value

    @property
    def ocr_processor_task(self) -> Optional[OCRProcessor]:
        """Backward compatibility: access tasks.ocr_processor."""
        return self.tasks.ocr_processor

    @ocr_processor_task.setter
    def ocr_processor_task(self, value: OCRProcessor) -> None:
        """Backward compatibility: set tasks.ocr_processor."""
        self.tasks.ocr_processor = value

    @property
    def folder_cleanup_task(self) -> Optional[FolderCleanup]:
        """Backward compatibility: access tasks.folder_cleanup."""
        return self.tasks.folder_cleanup

    @folder_cleanup_task.setter
    def folder_cleanup_task(self, value: FolderCleanup) -> None:
        """Backward compatibility: set tasks.folder_cleanup."""
        self.tasks.folder_cleanup = value

    # -------------------------------------------------------------------------
    # Derived properties
    # -------------------------------------------------------------------------

    @property
    def category_prefix(self) -> str:
        """Get the category prefix from import config."""
        return self.config.import_.get("category_prefix", "_")

    @property
    def fuzzy_threshold(self) -> int:
        """Get the fuzzy matching threshold from config."""
        return self.config.matching.get("fuzzy_threshold", 80)


# Initialize application state (config and database loaded immediately)
app_state = AppState()

# Expose commonly-used items at module level for backward compatibility
# These are used by routers and other modules that import from web.app
config_loader = app_state.config_loader
session_factory = app_state.session_factory
auth_manager = app_state.auth_manager
search_providers = app_state.search_providers
metadata_providers = app_state.metadata_providers


# =============================================================================
# Initialization Helper Functions
# =============================================================================
# These functions break down the lifespan startup into focused, testable units.


def _initialize_search_providers() -> None:
    """Initialize search providers (Newsnab, RSS) from config."""
    search_provider_configs = app_state.config_loader.get_search_providers()

    for provider_config in search_provider_configs:
        try:
            provider_type = provider_config.get("type")
            if not provider_type:
                logger.warning(f"Skipping provider with no type: {provider_config.get('name')}")
                continue

            # Validate provider configuration
            if provider_type == "newsnab" and not provider_config.get("api_key"):
                logger.warning("Skipping Newsnab provider: API key not configured")
                continue
            elif provider_type == "rss" and not provider_config.get("feed_url"):
                logger.warning("Skipping RSS provider: Feed URL not configured")
                continue

            logger.debug(f"Creating search provider: {provider_config.get('name')} (type: {provider_type})")
            provider = ProviderFactory.create(provider_config)
            app_state.search_providers.append(provider)
            logger.info(f"Loaded search provider: {provider.name}")

        except Exception as e:
            logger.error(f"Failed to load search provider {provider_config.get('name')}: {e}", exc_info=True)


def _initialize_download_client() -> None:
    """Initialize download clients (primary and additional)."""
    # Initialize primary download client (optional - can fail gracefully)
    try:
        client_config = app_state.config_loader.get_download_client()
        if not client_config.get("api_key"):
            logger.warning("Download client not available: API key not configured (configure in Settings)")
            app_state.download_client = None
        else:
            app_state.download_client = ClientFactory.create(client_config)
            logger.info(f"Loaded download client: {app_state.download_client.name}")
    except Exception as e:
        logger.warning(f"Download client not available (configure in Settings): {e}")
        app_state.download_client = None

    # Initialize additional download clients (e.g., Internet Archive)
    app_state.download_clients = {}
    try:
        additional_clients = app_state.config_loader.get_download_clients()
        for client_type, client_config in additional_clients.items():
            try:
                # Ensure type is set in config
                client_config["type"] = client_config.get("type", client_type)
                client = ClientFactory.create(client_config)
                app_state.download_clients[client_type] = client
                logger.info(f"Loaded additional download client: {client.name} (type: {client_type})")
            except Exception as e:
                logger.warning(f"Failed to load download client '{client_type}': {e}")
    except Exception as e:
        logger.debug(f"No additional download clients configured: {e}")


def _initialize_cache_services() -> None:
    """Initialize provider cache services (if enabled in config)."""
    if not app_state.cache_config.get("enabled", True):
        logger.info("Provider cache disabled in configuration")
        return

    try:
        from pathlib import Path

        from services.cache import ProviderCacheService, ProviderSyncService

        cache_dir = Path(app_state.storage_config.get("cache_dir", "./local/cache"))
        cache_db_path = cache_dir / "provider_cache.db"

        app_state.provider_cache_service = ProviderCacheService(
            cache_db_path=str(cache_db_path),
            fuzzy_threshold=app_state.fuzzy_threshold,
        )
        logger.info(
            f"Provider cache initialized: {cache_db_path} "
            f"(retention: {app_state.cache_config.get('retention_days', 90)} days)"
        )

        if app_state.search_providers:
            app_state.provider_sync_service = ProviderSyncService(
                cache_service=app_state.provider_cache_service,
                search_providers=app_state.search_providers,
            )
            logger.info("Provider sync service initialized")
        else:
            logger.warning("Provider sync service not initialized: no search providers")

    except Exception as e:
        logger.warning(f"Provider cache not available: {e}", exc_info=True)
        app_state.provider_cache_service = None
        app_state.provider_sync_service = None


def _initialize_core_services() -> None:
    """Initialize core application services (file processing, downloads, etc.)."""
    # Title matcher
    app_state.title_matcher = TitleMatcher(app_state.fuzzy_threshold)

    # File organizer
    app_state.file_processor = FileOrganizer(
        app_state.storage_config.get("library_dir", "./_Magazines"),
        category_prefix=app_state.category_prefix,
    )

    # File importer
    app_state.file_importer = FileImporter(
        downloads_dir=app_state.storage_config.get("download_dir", "./downloads"),
        library_base_dir=app_state.storage_config.get("library_dir", "./_Magazines"),
        fuzzy_threshold=app_state.fuzzy_threshold,
        organization_pattern=app_state.import_config.get("organization_pattern"),
        category_prefix=app_state.category_prefix,
        enable_text_scan=app_state.import_config.get("enable_text_scan", True),
    )

    # Download manager (requires download client and search providers)
    if app_state.download_client and app_state.search_providers:
        app_state.download_manager = DownloadManager(
            search_providers=app_state.search_providers,
            download_client=app_state.download_client,
            fuzzy_threshold=app_state.fuzzy_threshold,
            max_downloads=app_state.downloads_config.get("max_concurrent", 10),
            provider_cache_service=app_state.provider_cache_service,
            download_clients=app_state.download_clients or None,  # Additional clients for routing
        )
        logger.info(f"Download manager initialized with {len(app_state.download_clients or {})} additional client(s)")
    else:
        logger.warning("Download manager not initialized: missing download client or search providers")

    # Issue Discovery services
    app_state.issue_discovery_service = IssueDiscoveryService(
        fuzzy_threshold=app_state.fuzzy_threshold,
        default_max_retries=app_state.downloads_config.get("max_retries", 1),
    )
    app_state.search_scheduler = SearchScheduler(
        max_periodicals_per_run=app_state.tasks_config.get("max_periodicals_per_search", 2),
        rapid_interval_hours=app_state.tasks_config.get("rapid_search_interval", 1),
        normal_interval_hours=app_state.tasks_config.get("normal_search_interval", 6),
        slow_interval_hours=app_state.tasks_config.get("slow_search_interval", 24),
        very_slow_interval_hours=app_state.tasks_config.get("very_slow_search_interval", 168),
    )
    logger.info("Issue discovery services initialized")


def _initialize_background_tasks() -> None:
    """Initialize background task handlers (not the scheduler itself)."""
    # Download monitor
    if app_state.download_manager:
        app_state.download_monitor_task = DownloadMonitor(
            download_manager=app_state.download_manager,
            file_importer=app_state.file_importer,
            session_factory=app_state.session_factory,
            downloads_dir=app_state.storage_config.get("download_dir", "./downloads"),
        )
        logger.info("Download monitor task initialized")

    # Cover cleanup
    app_state.cover_cleanup_task = CoverCleanup(
        session_factory=app_state.session_factory,
        library_base_dir=app_state.storage_config.get("library_dir", "./_Magazines"),
        file_importer=app_state.file_importer,
    )
    logger.info("Cover cleanup task initialized")

    # OCR processor
    app_state.ocr_processor_task = OCRProcessor(
        session_factory=app_state.session_factory,
        config_loader=app_state.config_loader,
        max_workers=app_state.tasks_config.get("ocr_max_workers", constants.OCR_MAX_WORKERS),
        batch_size=app_state.tasks_config.get("ocr_batch_size", constants.OCR_BATCH_SIZE),
    )
    logger.info("OCR processor task initialized")

    # Folder cleanup
    auto_cleanup_config = app_state.import_config.get("auto_cleanup", {})
    app_state.folder_cleanup_task = FolderCleanup(
        downloads_dir=app_state.storage_config.get("download_dir", "./local/downloads"),
        library_dir=app_state.storage_config.get("library_dir", "./_Magazines"),
        dry_run=False,
        category_prefix=app_state.category_prefix,
        enable_downloads_cleanup=auto_cleanup_config.get("enable_downloads", True),
        enable_library_cleanup=auto_cleanup_config.get("enable_library", True),
    )
    logger.info("Folder cleanup task initialized")

    # Task scheduler (started later in lifespan)
    app_state.task_scheduler = TaskScheduler()


def _schedule_periodic_tasks(
    auto_download_task,
    download_monitoring_task,
    cleanup_orphaned_covers_task,
    ocr_processing_task,
    folder_cleanup_periodic_task,
    auto_metadata_periodic_task,
    provider_cache_sync_task,
) -> None:
    """Schedule all periodic background tasks."""
    scheduler = app_state.task_scheduler
    tasks_cfg = app_state.tasks_config
    cache_cfg = app_state.cache_config

    scheduler.schedule_periodic(
        "auto_download",
        auto_download_task,
        tasks_cfg.get("auto_download_interval", constants.AUTO_DOWNLOAD_INTERVAL),
        run_immediately=False,
    )

    scheduler.schedule_periodic(
        "download_monitor",
        download_monitoring_task,
        tasks_cfg.get("download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL),
        run_immediately=False,
    )

    scheduler.schedule_periodic(
        "cleanup_orphaned_covers",
        cleanup_orphaned_covers_task,
        tasks_cfg.get("cleanup_covers_interval", constants.CLEANUP_COVERS_INTERVAL),
    )

    scheduler.schedule_periodic(
        "ocr_processor",
        ocr_processing_task,
        tasks_cfg.get("ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL),
        run_immediately=False,
    )

    scheduler.schedule_periodic(
        "folder_cleanup",
        folder_cleanup_periodic_task,
        tasks_cfg.get("folder_cleanup_interval", 86400),
    )

    scheduler.schedule_periodic(
        "auto_metadata",
        auto_metadata_periodic_task,
        tasks_cfg.get("auto_metadata_interval", constants.AUTO_METADATA_INTERVAL),
    )

    # Provider cache sync (if enabled)
    if app_state.provider_sync_service:
        sync_interval = cache_cfg.get("sync", {}).get("interval_seconds", 1800)
        scheduler.schedule_periodic(
            "provider_cache_sync",
            provider_cache_sync_task,
            sync_interval,
            run_immediately=False,
        )
        logger.info(f"Provider cache sync scheduled: every {sync_interval}s")


def _initialize_router_dependencies(app: FastAPI, auto_download_task) -> None:
    """Initialize all router dependencies with app state."""
    # Set auth manager and middleware for FastAPI dependency injection
    app.state.auth_manager = app_state.auth_manager
    app.state.auth_middleware = AuthMiddleware(app_state.auth_manager)

    search.set_dependencies(
        app_state.search_providers,
        app_state.metadata_providers,
        app_state.title_matcher,
        app_state.session_factory,
        app_state.provider_cache_service,
    )

    periodicals.set_dependencies(
        app_state.session_factory,
        app_state.storage_config.get("library_dir", "./"),
        category_prefix=app_state.category_prefix,
    )

    tracking.set_dependencies(
        app_state.session_factory,
        app_state.search_providers,
        auto_download_task,
        app_state.storage_config,
        app_state.import_config,
    )

    downloads.set_dependencies(
        app_state.session_factory,
        app_state.download_manager,
        app_state.download_client,
    )

    imports.set_dependencies(
        app_state.session_factory,
        app_state.file_importer,
        app_state.storage_config,
    )

    tasks.set_dependencies(
        app_state.session_factory,
        app_state.download_monitor_task,
        app_state.file_importer,
        app_state.storage_config,
        app_state.ocr_processor_task,
        app_state.task_scheduler,
        app_state.folder_cleanup_task,
    )

    config.set_dependencies(app_state.config_loader)
    pages.set_dependencies(app_state.session_factory)
    ocr_queue.set_dependencies(app_state.session_factory)

    discovery.set_dependencies(
        app_state.session_factory,
        app_state.issue_discovery_service,
        app_state.search_scheduler,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    try:
        _initialize_search_providers()
        _initialize_download_client()
        _initialize_cache_services()
        _initialize_core_services()
        _initialize_background_tasks()

        # Define auto-download task (uses Issue Discovery & Tracking system)
        async def auto_download_task():
            """Adaptive search and download for tracked periodicals."""
            logger.info("Starting auto-download task")

            def _run_auto_download():
                db_session = app_state.session_factory()
                try:
                    if not app_state.download_manager:
                        return

                    logger.debug("Auto-download: Starting Issue Discovery & Tracking run")

                    # Phase 1: Select periodicals to search (adaptive scheduling)
                    periodicals_to_search = app_state.search_scheduler.select_periodicals_to_search(db_session)
                    if not periodicals_to_search:
                        logger.debug("Auto-download: No periodicals need searching at this time")
                        return

                    # Phase 2: Search each selected periodical and record results
                    for periodical in periodicals_to_search:
                        try:
                            logger.debug(f"Auto-download: Searching for '{periodical.title}'")
                            search_results = app_state.download_manager.search_periodical_issues(
                                periodical.title, db_session
                            )

                            if not search_results:
                                logger.debug(f"Auto-download: No results found for '{periodical.title}'")
                                app_state.search_scheduler.update_search_stats(periodical.id, 0, db_session)
                                continue

                            logger.debug(f"Auto-download: Found {len(search_results)} results for '{periodical.title}'")

                            record_stats = app_state.issue_discovery_service.record_search_results(
                                periodical.id, search_results, db_session
                            )

                            if record_stats["new"] > 0:
                                logger.info(f"Auto-download: '{periodical.title}' - {record_stats['new']} new issues")

                            eval_stats = app_state.issue_discovery_service.evaluate_discovered_issues(
                                periodical.id, db_session
                            )
                            if eval_stats["wanted"] > 0:
                                logger.info(f"Auto-download: '{periodical.title}' - {eval_stats['wanted']} queued")

                            app_state.search_scheduler.update_search_stats(
                                periodical.id, record_stats["new"], db_session
                            )

                        except Exception as e:
                            logger.error(f"Auto-download: Error processing '{periodical.title}': {e}", exc_info=True)

                    # Phase 3: Download from priority queue
                    logger.debug("Auto-download: Checking download queue")
                    from models.database import DownloadSubmission

                    pending_count = (
                        db_session.query(DownloadSubmission)
                        .filter(
                            DownloadSubmission.status.in_(
                                [DownloadSubmission.StatusEnum.PENDING, DownloadSubmission.StatusEnum.DOWNLOADING]
                            )
                        )
                        .count()
                    )

                    remaining_slots = max(0, app_state.download_manager.max_downloads - pending_count)
                    logger.debug(f"Auto-download: {remaining_slots} slots available ({pending_count} in progress)")

                    if remaining_slots > 0:
                        download_queue = app_state.issue_discovery_service.get_download_queue(
                            db_session, limit=remaining_slots
                        )
                        if download_queue:
                            logger.info(f"Auto-download: Submitting {len(download_queue)} issues")
                            submitted_count = 0
                            for issue in download_queue:
                                try:
                                    submission = app_state.download_manager.submit_from_discovered_issue(
                                        issue.id, db_session
                                    )
                                    if submission:
                                        submitted_count += 1
                                        logger.info(
                                            f"Auto-download: Submitted '{issue.title}' "
                                            f"(priority {issue.download_priority}, job_id: {submission.job_id})"
                                        )
                                except Exception as e:
                                    logger.error(f"Auto-download: Error submitting '{issue.title}': {e}", exc_info=True)

                            if submitted_count > 0:
                                logger.info(f"Auto-download: Submitted {submitted_count} downloads")

                    logger.debug("Auto-download: Completed run")
                finally:
                    db_session.close()

            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _run_auto_download)
            except Exception as e:
                logger.error(f"Auto-download error: {e}", exc_info=True)

        # Define download monitoring task
        async def download_monitoring_task():
            """Monitor download client and scan downloads folder for files to import."""
            if app_state.download_monitor_task:
                try:
                    from datetime import datetime, timedelta

                    interval = app_state.tasks_config.get(
                        "download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL
                    )
                    app_state.download_monitor_task.next_run_time = datetime.now() + timedelta(seconds=interval)
                    await app_state.download_monitor_task.run()
                except Exception as e:
                    logger.error(f"Download monitoring error: {e}", exc_info=True)

        # Define cover cleanup task wrapper
        async def cleanup_orphaned_covers_task():
            """Clean up cover files that aren't tied to any periodical."""
            await app_state.cover_cleanup_task.run()

        # Define OCR processor task wrapper
        async def ocr_processing_task():
            """Process queued OCR jobs with process pool."""
            try:
                from datetime import datetime, timedelta

                interval = app_state.tasks_config.get("ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL)
                app_state.ocr_processor_task.next_run_time = datetime.now() + timedelta(seconds=interval)

                stats = await app_state.ocr_processor_task.run()
                if stats.get("processed", 0) > 0:
                    logger.info(f"OCR processor: {stats}")
            except Exception as e:
                logger.error(f"OCR processor error: {e}", exc_info=True)

        # Define folder cleanup task wrapper
        async def folder_cleanup_periodic_task():
            """Clean up empty folders and folders without importable files."""
            try:
                loop = asyncio.get_event_loop()
                stats = await loop.run_in_executor(None, app_state.folder_cleanup_task.run)
                if stats.get("total_deleted", 0) > 0:
                    logger.info(f"Folder cleanup: {stats}")
            except Exception as e:
                logger.error(f"Folder cleanup error: {e}", exc_info=True)

        # Define auto-metadata task wrapper
        async def auto_metadata_periodic_task():
            """Backfill derived_metadata, sync issue_date, and queue missing OCR/text scans."""
            try:
                from core.utils import run_in_thread
                from services.auto_metadata import AutoMetadataService

                def _run_auto_metadata():
                    service = AutoMetadataService(
                        app_state.db_manager,
                        library_base_dir=app_state.storage_config.get("library_dir"),
                        category_prefix=app_state.category_prefix,
                    )
                    session = app_state.session_factory()
                    try:
                        return service.run_full_scan(session)
                    finally:
                        session.close()

                stats = await run_in_thread(_run_auto_metadata)
                logger.info(
                    f"Auto-metadata: Processed {stats.get('total_periodicals', 0)} periodicals, "
                    f"fixed {stats.get('paths_fixed', 0)} paths, "
                    f"backfilled {stats.get('derived_metadata_backfilled', 0)} metadata, "
                    f"synced {stats.get('issue_date_synced', 0)} dates, "
                    f"queued {stats.get('ocr_queued', 0)} OCR, "
                    f"queued {stats.get('text_scan_queued', 0)} text scans"
                )
            except Exception as e:
                logger.error(f"Auto-metadata error: {e}", exc_info=True)

        # Define provider cache sync task wrapper
        async def provider_cache_sync_task():
            """Sync provider cache with latest releases from providers."""
            logger.info("Starting provider cache sync task")
            if app_state.provider_sync_service:
                try:
                    stats = await app_state.provider_sync_service.sync_all_providers()
                    if stats.get("total_added", 0) > 0:
                        logger.info(
                            f"Provider cache sync: {stats.get('total_added', 0)} added, "
                            f"{stats.get('total_nzbs_downloaded', 0)} NZBs, "
                            f"{stats.get('total_failed', 0)} failures"
                        )
                except Exception as e:
                    logger.error(f"Provider cache sync error: {e}", exc_info=True)

        # Schedule all periodic tasks
        _schedule_periodic_tasks(
            auto_download_task,
            download_monitoring_task,
            cleanup_orphaned_covers_task,
            ocr_processing_task,
            folder_cleanup_periodic_task,
            auto_metadata_periodic_task,
            provider_cache_sync_task,
        )

        # Start scheduler in background
        app_state.scheduler_task = asyncio.create_task(app_state.task_scheduler.start())

        # Initialize router dependencies
        _initialize_router_dependencies(app, auto_download_task)

    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

    yield

    # Shutdown
    try:
        if app_state.task_scheduler:
            app_state.task_scheduler.stop()
            logger.info("Task scheduler stopped")

        if app_state.scheduler_task:
            app_state.scheduler_task.cancel()
            try:
                await app_state.scheduler_task
            except asyncio.CancelledError:
                pass

        # Shutdown OCR processor
        if app_state.ocr_processor_task:
            app_state.ocr_processor_task.shutdown()
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
    from fastapi.responses import JSONResponse

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
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "service": "curator",
                    "database": db_status,
                },
            )
        finally:
            session.close()

        return {"status": "healthy", "service": "curator", "database": db_status}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "service": "curator", "error": str(e)},
        )


@app.get("/api/status")
async def get_status():
    """Get manager status"""
    return {
        "status": "running",
        "providers": [p.get_provider_info() for p in app_state.search_providers],
        "download_client": (app_state.download_client.get_client_info() if app_state.download_client else None),
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
    uvicorn.run(app, host=server_config["host"], port=server_config["port"], access_log=False)

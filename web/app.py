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
from core.parsers import TitleMatcher, utc_now
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
    stacks,
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
    nzb_cache_service: Optional[Any] = None
    feed_sync_service: Optional[Any] = None  # RSS feed entry sync (cache-first auto-download)
    feed_match_service: Optional[Any] = None  # Local matching against cached feed entries
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
    def nzb_cache_service(self) -> Optional[Any]:
        """Backward compatibility: access services.nzb_cache_service."""
        return self.services.nzb_cache_service

    @nzb_cache_service.setter
    def nzb_cache_service(self, value: Any) -> None:
        """Backward compatibility: set services.nzb_cache_service."""
        self.services.nzb_cache_service = value

    @property
    def feed_sync_service(self) -> Optional[Any]:
        """Backward compatibility: access services.feed_sync_service."""
        return self.services.feed_sync_service

    @feed_sync_service.setter
    def feed_sync_service(self, value: Any) -> None:
        """Backward compatibility: set services.feed_sync_service."""
        self.services.feed_sync_service = value

    @property
    def feed_match_service(self) -> Optional[Any]:
        """Backward compatibility: access services.feed_match_service."""
        return self.services.feed_match_service

    @feed_match_service.setter
    def feed_match_service(self, value: Any) -> None:
        """Backward compatibility: set services.feed_match_service."""
        self.services.feed_match_service = value

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
    """Initialize search providers (Newsnab, RSS, Internet Archive) from config."""
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
            logger.error(
                f"Failed to load search provider {provider_config.get('name')}: {e}",
                exc_info=True,
            )


def _initialize_download_client() -> None:
    """Initialize download clients (primary and additional).

    The primary download client is determined by which providers are enabled:
    - If NZB providers (newsnab/rss) are enabled: use SABnzbd/NZBGet
    - If only Internet Archive is enabled: use Internet Archive client as primary
    """
    # Initialize additional download clients first (e.g., Internet Archive)
    # We need to know what's available to determine the primary client
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

    # Check what types of search providers are enabled
    nzb_providers = [p for p in app_state.search_providers if p.type in ("newsnab", "rss")]
    ia_providers = [p for p in app_state.search_providers if p.type == "internet_archive"]
    has_only_ia = ia_providers and not nzb_providers

    # Initialize primary download client based on provider types
    if has_only_ia:
        # Only Internet Archive providers - use IA client as primary
        if "internet_archive" in app_state.download_clients:
            app_state.download_client = app_state.download_clients["internet_archive"]
            logger.info(
                f"Using Internet Archive as primary download client (only IA providers enabled): "
                f"{app_state.download_client.name}"
            )
        else:
            logger.warning("Only Internet Archive search providers enabled but no IA download client configured")
            app_state.download_client = None
    else:
        # NZB providers present - use SABnzbd/NZBGet as primary
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


def _initialize_cache_services() -> None:
    """Initialize cache services for NZB content and feed sync.

    Creates a single shared SQLAlchemy engine for the cache database, then
    passes the session factory to both services. This avoids duplicate
    connections and potential SQLite lock contention.

    - NZB cache: Only for Newsnab and RSS providers that return NZB files
    - Feed sync: Individual feed entry cache for cache-first auto-download
    - Feed match: Local matching of cached entries against tracked periodicals
    """
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from models.cache import CacheBase
    from services.cache import FeedMatchService, FeedSyncService, NzbCacheService

    cache_dir = Path(app_state.storage_config.get("cache_dir", "./local/cache"))
    cache_db_path = cache_dir / constants.CACHE_DB_FILENAME

    # Create shared engine and session factory for the cache database
    # Both FeedSyncService and NzbCacheService use the same SQLite file,
    # so a single engine avoids redundant connections and lock contention.
    import os

    os.makedirs(cache_dir, exist_ok=True)
    db_url = f"sqlite:///{cache_db_path}"
    cache_engine = create_engine(db_url, echo=False)
    cache_session_factory = sessionmaker(bind=cache_engine)
    CacheBase.metadata.create_all(cache_engine)

    # Initialize feed sync service (cache-first auto-download)
    try:
        retention_days = app_state.tasks_config.get("feed_entry_retention_days", constants.FEED_ENTRY_RETENTION_DAYS)
        app_state.feed_sync_service = FeedSyncService(
            cache_db_path=str(cache_db_path),
            retention_days=retention_days,
            session_factory=cache_session_factory,
        )
        app_state.feed_match_service = FeedMatchService()
        logger.info(f"Feed sync service initialized (retention: {retention_days} days)")
    except Exception as e:
        logger.warning(f"Feed sync service not available: {e}", exc_info=True)
        app_state.feed_sync_service = None
        app_state.feed_match_service = None

    # Initialize NZB cache service (only if NZB providers exist and cache is enabled)
    if not app_state.cache_config.get("enabled", True):
        logger.info("NZB cache disabled in configuration")
        return

    # Check if there are any NZB providers (newsnab or rss) - Internet Archive doesn't need cache
    nzb_providers = [p for p in app_state.search_providers if p.type in ("newsnab", "rss")]
    if not nzb_providers:
        logger.info("NZB cache not initialized: no NZB providers (newsnab/rss) enabled")
        return

    try:
        app_state.nzb_cache_service = NzbCacheService(
            cache_db_path=str(cache_db_path),
            max_nzb_fetches_per_hour=app_state.cache_config.get("max_nzb_fetches_per_hour", 50),
            session_factory=cache_session_factory,
        )
        logger.info(f"NZB cache service initialized: {cache_db_path}")

    except Exception as e:
        logger.warning(f"NZB cache not available: {e}", exc_info=True)
        app_state.nzb_cache_service = None


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
        session_factory=app_state.session_factory,
        parallel_workers=app_state.import_config.get("parallel_workers", 2),
    )

    # Download manager (requires download client and search providers)
    if app_state.download_client and app_state.search_providers:
        app_state.download_manager = DownloadManager(
            search_providers=app_state.search_providers,
            download_client=app_state.download_client,
            fuzzy_threshold=app_state.fuzzy_threshold,
            max_downloads=app_state.downloads_config.get("max_concurrent", 10),
            nzb_cache_service=app_state.nzb_cache_service,
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
        # Get remote_path from download client config for path remapping
        # This maps the client's path prefix to Curator's local downloads_dir
        remote_path = None
        try:
            client_cfg = app_state.config_loader.get_download_client()
            remote_path = client_cfg.get("remote_path")
        except ValueError:
            pass  # No download client configured

        app_state.download_monitor_task = DownloadMonitor(
            download_manager=app_state.download_manager,
            file_importer=app_state.file_importer,
            session_factory=app_state.session_factory,
            downloads_dir=app_state.storage_config.get("download_dir", "./downloads"),
            remote_path=remote_path,
        )
        if remote_path:
            logger.info(f"Download monitor task initialized (remote_path: {remote_path})")
        else:
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
    feed_sync_task,
    auto_download_task,
    download_monitoring_task,
    cleanup_orphaned_covers_task,
    ocr_processing_task,
    folder_cleanup_periodic_task,
    auto_metadata_periodic_task,
) -> None:
    """Schedule all periodic background tasks."""
    scheduler = app_state.task_scheduler
    tasks_cfg = app_state.tasks_config

    # Feed sync runs more frequently than auto-download (lightweight RSS polling)
    scheduler.schedule_periodic(
        "feed_sync",
        feed_sync_task,
        tasks_cfg.get("feed_sync_interval", constants.FEED_SYNC_INTERVAL),
        run_immediately=True,  # Populate cache on first run
        enabled=tasks_cfg.get("feed_sync_enabled", True),
    )

    scheduler.schedule_periodic(
        "auto_download",
        auto_download_task,
        tasks_cfg.get("auto_download_interval", constants.AUTO_DOWNLOAD_INTERVAL),
        run_immediately=False,
        enabled=tasks_cfg.get("auto_download_enabled", True),
    )

    scheduler.schedule_periodic(
        "download_monitor",
        download_monitoring_task,
        tasks_cfg.get("download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL),
        run_immediately=False,
        enabled=tasks_cfg.get("download_monitor_enabled", True),
    )

    scheduler.schedule_periodic(
        "cleanup_orphaned_covers",
        cleanup_orphaned_covers_task,
        tasks_cfg.get("cleanup_covers_interval", constants.CLEANUP_COVERS_INTERVAL),
        enabled=tasks_cfg.get("cleanup_covers_enabled", True),
    )

    scheduler.schedule_periodic(
        "ocr_processor",
        ocr_processing_task,
        tasks_cfg.get("ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL),
        run_immediately=False,
        enabled=tasks_cfg.get("ocr_processor_enabled", True),
    )

    scheduler.schedule_periodic(
        "folder_cleanup",
        folder_cleanup_periodic_task,
        tasks_cfg.get("folder_cleanup_interval", 86400),
        enabled=tasks_cfg.get("folder_cleanup_enabled", True),
    )

    scheduler.schedule_periodic(
        "auto_metadata",
        auto_metadata_periodic_task,
        tasks_cfg.get("auto_metadata_interval", constants.AUTO_METADATA_INTERVAL),
        enabled=tasks_cfg.get("auto_metadata_enabled", True),
    )


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
        app_state.feed_sync_service,
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
        app_state.config_loader,
    )

    config.set_dependencies(app_state.config_loader)
    pages.set_dependencies(app_state.session_factory)
    stacks.set_dependencies(app_state.session_factory)
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

        # Import background tasks from dedicated module
        from web.background_tasks import (
            auto_download_task,
            auto_metadata_periodic_task,
            cleanup_orphaned_covers_task,
            download_monitoring_task,
            feed_sync_task,
            folder_cleanup_periodic_task,
            ocr_processing_task,
        )

        # Create task wrappers that pass app_state to the background task functions
        async def feed_sync_wrapper():
            await feed_sync_task(app_state)

        async def auto_download_wrapper():
            await auto_download_task(app_state)

        async def download_monitoring_wrapper():
            await download_monitoring_task(app_state)

        async def cleanup_orphaned_covers_wrapper():
            await cleanup_orphaned_covers_task(app_state)

        async def ocr_processing_wrapper():
            await ocr_processing_task(app_state)

        async def folder_cleanup_wrapper():
            await folder_cleanup_periodic_task(app_state)

        async def auto_metadata_wrapper():
            await auto_metadata_periodic_task(app_state)

        # Schedule all periodic tasks
        _schedule_periodic_tasks(
            feed_sync_wrapper,
            auto_download_wrapper,
            download_monitoring_wrapper,
            cleanup_orphaned_covers_wrapper,
            ocr_processing_wrapper,
            folder_cleanup_wrapper,
            auto_metadata_wrapper,
        )

        # Start scheduler in background
        app_state.scheduler_task = asyncio.create_task(app_state.task_scheduler.start())

        # Initialize router dependencies
        _initialize_router_dependencies(app, auto_download_wrapper)

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
app.include_router(stacks.router)
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

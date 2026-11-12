"""Flat AppState attributes stay aliases of the nested state."""

from web.app import app_state


def test_config_and_database_aliases_match_the_nested_state():
    assert app_state.config_loader is app_state.config.loader
    assert app_state.storage_config is app_state.config.storage
    assert app_state.cache_config is app_state.config.cache
    assert app_state.matching_config is app_state.config.matching
    assert app_state.pdf_config is app_state.config.pdf
    assert app_state.downloads_config is app_state.config.downloads
    assert app_state.tasks_config is app_state.config.tasks
    assert app_state.import_config is app_state.config.import_
    assert app_state.db_url == app_state.db.url
    assert app_state.db_manager is app_state.db.manager
    assert app_state.session_factory is app_state.db.session_factory
    assert isinstance(app_state.category_prefix, str)
    assert isinstance(app_state.fuzzy_threshold, int)


def test_service_aliases_round_trip():
    names = [
        "download_client",
        "download_manager",
        "title_matcher",
        "file_processor",
        "file_importer",
        "nzb_cache_service",
        "feed_sync_service",
        "feed_match_service",
        "issue_discovery_service",
        "search_scheduler",
        "task_scheduler",
        "scheduler_task",
        "download_monitor_task",
        "cover_cleanup_task",
        "ocr_processor_task",
        "folder_cleanup_task",
        "file_reorganizer_task",
    ]
    saved = {name: getattr(app_state, name) for name in names}
    try:
        for name in names:
            token = object()
            setattr(app_state, name, token)
            assert getattr(app_state, name) is token
    finally:
        for name, value in saved.items():
            setattr(app_state, name, value)

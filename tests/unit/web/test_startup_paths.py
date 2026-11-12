"""Startup helpers, auto-download steps, and manual metadata edits."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.parsers import utc_now
from models.database import Base, Periodical, PeriodicalTracking, SearchResult
from web.background_tasks import (
    _cleanup_stale_search_results,
    _extract_search_aliases,
    _is_rate_limited,
    _process_cache_matches,
    _process_periodical_searches,
    auto_metadata_periodic_task,
    file_reorganizer_periodic_task,
)
from web.app import (
    _initialize_background_tasks,
    _initialize_cache_services,
    _initialize_download_client,
    _initialize_search_providers,
    app_state,
)
from web.routers.auth import get_verify_token
from web.routers.periodicals import metadata as metadata_router


@pytest.fixture
def session():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        path = handle.name
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        Path(path).unlink(missing_ok=True)


def _tracking(session, title="City Paper", aliases=None, cache_match=None):
    row = PeriodicalTracking(
        olid=title.lower().replace(" ", "-"),
        title=title,
        user_id=1,
        search_aliases=aliases,
        last_cache_match=cache_match,
    )
    session.add(row)
    session.commit()
    return row


def test_cache_matches_record_new_issues_and_stamp_the_tracking_row(session):
    tracking = _tracking(session)
    app_state = SimpleNamespace(
        tasks_config={},
        feed_sync_service=MagicMock(),
        feed_match_service=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.feed_sync_service.get_new_entries.return_value = [{"title": "City Paper January 2024"}]
    app_state.feed_match_service.match_entries_against_tracking.return_value = {
        "matches": {tracking.id: [{"title": "City Paper January 2024"}]},
        "matched_entry_ids": [1],
        "skipped_entry_ids": [2],
        "stats": {"matched": 1},
    }
    app_state.issue_discovery_service.record_search_results.return_value = {"new": 1, "updated": 0}
    app_state.issue_discovery_service.evaluate_discovered_issues.return_value = {"wanted": 1}

    found = _process_cache_matches(app_state, session)

    session.refresh(tracking)
    assert found == 1
    assert tracking.last_cache_match is not None
    app_state.feed_sync_service.mark_entries_matched.assert_called_once_with([1])
    app_state.feed_sync_service.mark_entries_skipped.assert_called_once_with([2])


def test_a_failing_cache_match_is_skipped_and_the_rest_are_marked(session):
    app_state = SimpleNamespace(
        tasks_config={},
        feed_sync_service=MagicMock(),
        feed_match_service=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.feed_sync_service.get_new_entries.return_value = [{"title": "x"}]
    app_state.feed_match_service.match_entries_against_tracking.return_value = {
        "matches": {99: [{"title": "x"}]},
        "matched_entry_ids": [],
        "skipped_entry_ids": [],
        "stats": {"matched": 0},
    }
    app_state.issue_discovery_service.record_search_results.side_effect = RuntimeError("bad row")

    assert _process_cache_matches(app_state, session) == 0


def test_rate_limited_providers_defer_the_search(session):
    tracking = _tracking(session)
    manager = MagicMock()
    manager.all_providers_rate_limited = True
    app_state = SimpleNamespace(
        tasks_config={"inter_search_delay": 0, "cache_aware_search_skip_hours": 0},
        download_manager=manager,
        search_scheduler=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.search_scheduler.select_periodicals_to_search.return_value = [tracking]

    _process_periodical_searches(app_state, session)

    manager.search_periodical_issues.assert_not_called()


def test_a_fresh_cache_match_skips_the_api_search(session):
    tracking = _tracking(session, cache_match=utc_now())
    manager = MagicMock()
    manager.all_providers_rate_limited = False
    manager.search_providers = []
    app_state = SimpleNamespace(
        tasks_config={"inter_search_delay": 0, "cache_aware_search_skip_hours": 24},
        download_manager=manager,
        search_scheduler=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.search_scheduler.select_periodicals_to_search.return_value = [tracking]

    _process_periodical_searches(app_state, session)

    manager.search_periodical_issues.assert_not_called()


def test_a_search_with_results_updates_the_scheduler(session):
    tracking = _tracking(session, aliases="CP, City")
    manager = MagicMock()
    manager.all_providers_rate_limited = False
    manager.search_service = None
    manager.search_providers = []
    manager.search_periodical_issues.return_value = [{"title": "City Paper January 2024"}]
    app_state = SimpleNamespace(
        tasks_config={"inter_search_delay": 0, "cache_aware_search_skip_hours": 0},
        download_manager=manager,
        search_scheduler=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.search_scheduler.select_periodicals_to_search.return_value = [tracking]
    app_state.issue_discovery_service.record_search_results.return_value = {"new": 1, "updated": 0}
    app_state.issue_discovery_service.evaluate_discovered_issues.return_value = {"wanted": 2}

    _process_periodical_searches(app_state, session)

    assert _extract_search_aliases(tracking) == ["CP", "City"]
    manager.search_periodical_issues.assert_called_once()
    app_state.search_scheduler.update_search_stats.assert_called_once_with(tracking.id, 2, session)


def test_an_empty_search_records_zero_wanted(session):
    tracking = _tracking(session)
    manager = MagicMock()
    manager.all_providers_rate_limited = False
    manager.search_service = SimpleNamespace(any_provider_rate_limited=False)
    manager.search_providers = []
    manager.search_periodical_issues.return_value = []
    app_state = SimpleNamespace(
        tasks_config={"inter_search_delay": 0, "cache_aware_search_skip_hours": 0},
        download_manager=manager,
        search_scheduler=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.search_scheduler.select_periodicals_to_search.return_value = [tracking]

    _process_periodical_searches(app_state, session)

    app_state.search_scheduler.update_search_stats.assert_called_once_with(tracking.id, 0, session)


def test_a_search_error_does_not_stop_the_run(session):
    tracking = _tracking(session)
    manager = MagicMock()
    manager.all_providers_rate_limited = False
    manager.search_providers = []
    manager.search_periodical_issues.side_effect = RuntimeError("indexer down")
    app_state = SimpleNamespace(
        tasks_config={"inter_search_delay": 0, "cache_aware_search_skip_hours": 0},
        download_manager=manager,
        search_scheduler=MagicMock(),
        issue_discovery_service=MagicMock(),
    )
    app_state.search_scheduler.select_periodicals_to_search.return_value = [tracking]

    _process_periodical_searches(app_state, session)

    app_state.search_scheduler.update_search_stats.assert_not_called()


def test_stale_search_results_are_deleted(session):
    session.add(
        SearchResult(
            provider="newsnab",
            query="City",
            title="Old",
            url="http://example.com/old.nzb",
            created_at=utc_now() - timedelta(days=400),
        )
    )
    session.commit()
    app_state = SimpleNamespace(tasks_config={"search_result_retention_days": 30})

    _cleanup_stale_search_results(app_state, session)

    assert session.query(SearchResult).count() == 0


def test_rate_limit_checks_the_manager_and_each_provider():
    limited = SimpleNamespace(is_rate_limited=True)
    manager = SimpleNamespace(
        all_providers_rate_limited=False,
        search_service=SimpleNamespace(any_provider_rate_limited=False),
        search_providers=[limited],
    )
    assert _is_rate_limited(manager) is True
    manager.search_providers = []
    assert _is_rate_limited(manager) is False


@pytest.mark.asyncio
async def test_metadata_and_reorganizer_tasks_call_their_workers(monkeypatch):
    service = MagicMock()
    service.run_full_scan.return_value = {
        "total_periodicals": 1,
        "paths_fixed": 0,
        "derived_metadata_backfilled": 0,
        "issue_date_synced": 0,
        "ocr_queued": 0,
        "text_scan_queued": 0,
    }
    monkeypatch.setattr("services.auto_metadata.AutoMetadataService", MagicMock(return_value=service))
    app_state = SimpleNamespace(
        db_manager=MagicMock(),
        storage_config={"library_dir": "/tmp"},
        category_prefix="_",
        session_factory=MagicMock(),
        file_reorganizer_task=MagicMock(),
    )
    app_state.file_reorganizer_task.run.return_value = {"reorganized": 1, "errors": 0}

    await auto_metadata_periodic_task(app_state)
    await file_reorganizer_periodic_task(app_state)

    service.run_full_scan.assert_called_once()
    app_state.file_reorganizer_task.run.assert_called_once()


def test_startup_helpers_load_providers_and_clients_from_config():
    providers = app_state.search_providers
    saved_providers = list(providers)
    saved_clients = dict(app_state.download_clients)
    saved_primary = app_state.download_client
    saved_feed = app_state.feed_sync_service
    saved_cache = app_state.nzb_cache_service
    saved_monitor = app_state.download_monitor_task
    saved_ocr = app_state.ocr_processor_task
    try:
        providers.clear()
        _initialize_search_providers()
        _initialize_download_client()
        _initialize_cache_services()
        _initialize_background_tasks()
        assert isinstance(app_state.search_providers, list)
        assert isinstance(app_state.download_clients, dict)
    finally:
        providers.clear()
        providers.extend(saved_providers)
        app_state.download_clients = saved_clients
        app_state.download_client = saved_primary
        app_state.feed_sync_service = saved_feed
        app_state.nzb_cache_service = saved_cache
        app_state.download_monitor_task = saved_monitor
        app_state.ocr_processor_task = saved_ocr


def test_manual_metadata_edit_sets_month_precision(session):
    magazine = Periodical(
        user_id=1,
        title="City Paper",
        issue_date=datetime(2020, 6, 14),
        file_path="/library/city.pdf",
        date_precision="day",
    )
    session.add(magazine)
    session.commit()
    magazine_id = magazine.id
    factory = sessionmaker(bind=session.get_bind())
    from web.routers.periodicals import _shared

    _shared.set_dependencies(factory, library_base_dir="/tmp/library")
    app = FastAPI()
    app.dependency_overrides[get_verify_token] = lambda: "tester"
    app.include_router(metadata_router.router)
    client = TestClient(app)

    special = client.post(f"/api/periodicals/{magazine_id}/toggle-special-edition?is_special=true")
    updated = client.put(f"/api/periodicals/{magazine_id}", json={"year": 2024, "month": "March", "issue_number": "9"})

    check = factory()
    try:
        saved = check.query(Periodical).filter_by(id=magazine_id).one()
        assert special.status_code == 200
        assert updated.status_code == 200
        assert saved.date_precision == "month"
        assert saved.issue_date.month == 3
        assert saved.derived_metadata["issue_number"]["value"] == "9"
    finally:
        check.close()

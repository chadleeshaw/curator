"""Background task guards and the calls they make into injected services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from core.parsers import utc_now
from web.background_tasks import (
    auto_download_task,
    cleanup_orphaned_covers_task,
    download_monitoring_task,
    feed_sync_task,
    folder_cleanup_periodic_task,
    ocr_processing_task,
)

pytestmark = pytest.mark.asyncio


async def test_feed_sync_is_skipped_when_the_service_is_missing():
    service = Mock()
    missing_service = SimpleNamespace(feed_sync_service=None, search_providers=[Mock()])
    missing_providers = SimpleNamespace(feed_sync_service=service, search_providers=None)
    empty_providers = SimpleNamespace(feed_sync_service=service, search_providers=[])

    await feed_sync_task(missing_service)
    await feed_sync_task(missing_providers)
    await feed_sync_task(empty_providers)

    service.sync_all_providers.assert_not_called()
    service.expire_old_entries.assert_not_called()


async def test_successful_feed_sync_expires_old_entries():
    service = Mock()
    service.sync_all_providers.return_value = {
        "total_new": 4,
        "total_updated": 2,
        "providers_synced": 1,
    }
    providers = [Mock()]
    app_state = SimpleNamespace(feed_sync_service=service, search_providers=providers)

    await feed_sync_task(app_state)

    assert service.mock_calls == [
        call.sync_all_providers(providers),
        call.expire_old_entries(),
    ]


async def test_auto_download_returns_early_without_a_download_manager():
    session = Mock()
    session_factory = Mock(return_value=session)
    feed_sync = Mock()
    discovery = Mock()
    scheduler = Mock()
    app_state = SimpleNamespace(
        session_factory=session_factory,
        download_manager=None,
        feed_sync_service=feed_sync,
        feed_match_service=Mock(),
        issue_discovery_service=discovery,
        search_scheduler=scheduler,
        tasks_config={},
    )

    await auto_download_task(app_state)

    session_factory.assert_called_once_with()
    session.close.assert_called_once_with()
    feed_sync.get_new_entries.assert_not_called()
    discovery.record_search_results.assert_not_called()
    scheduler.select_periodicals_to_search.assert_not_called()


async def test_download_monitoring_invokes_the_injected_task():
    monitor = Mock()
    monitor.run = AsyncMock(return_value=None)
    event_bus = Mock()
    event_bus.publish = AsyncMock()
    app_state = SimpleNamespace(
        download_monitor_task=monitor,
        tasks_config={"download_monitor_interval": 45},
        event_bus=event_bus,
    )
    before = utc_now()

    await download_monitoring_task(app_state)

    monitor.run.assert_awaited_once_with()
    event_bus.publish.assert_awaited_once_with("download_queue", {"trigger": "update"})
    assert monitor.next_run_time > before


async def test_ocr_processing_invokes_the_injected_task():
    processor = Mock()
    processor.run = AsyncMock(return_value={"processed": 3, "failed": 0})
    event_bus = Mock()
    event_bus.publish = AsyncMock()
    app_state = SimpleNamespace(
        ocr_processor_task=processor,
        tasks_config={"ocr_processor_interval": 30},
        event_bus=event_bus,
    )
    before = utc_now()

    await ocr_processing_task(app_state)

    processor.run.assert_awaited_once_with()
    event_bus.publish.assert_awaited_once_with("ocr_queue", {"trigger": "update"})
    assert processor.next_run_time > before


async def test_cleanup_tasks_invoke_the_injected_task_objects():
    cover_cleanup = Mock()
    cover_cleanup.run = AsyncMock(return_value={"removed": 1})
    folder_cleanup = Mock()
    folder_cleanup.run.return_value = {"total_deleted": 4}

    await cleanup_orphaned_covers_task(SimpleNamespace(cover_cleanup_task=cover_cleanup))
    await folder_cleanup_periodic_task(SimpleNamespace(folder_cleanup_task=folder_cleanup))

    cover_cleanup.run.assert_awaited_once_with()
    folder_cleanup.run.assert_called_once_with()

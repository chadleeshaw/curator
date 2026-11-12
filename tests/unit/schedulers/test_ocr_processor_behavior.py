"""Behavior tests for OCRProcessor run, failure, and shutdown paths.

``tests/unit/schedulers/test_ocr_processor.py`` covers construction and the
retry constant passed by ``_process_sync``. These tests cover the async run
gates, stat totals, error returns, and shutdown order. The OCR service is mocked.
"""

import asyncio
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from core.constants.ocr import MAX_OCR_RETRIES
from schedulers.ocr_processor import OCRProcessor


@pytest.fixture
def processor():
    session = Mock()
    proc = OCRProcessor(Mock(return_value=session), max_workers=1, batch_size=2)
    proc.ocr_service.process_queue = Mock(return_value={"processed": 0, "failed": 0, "succeeded": 0})
    proc.ocr_service.cleanup_old_jobs = Mock(return_value=0)
    yield proc, session
    proc.executor.shutdown(wait=False, cancel_futures=True)


def _run(proc):
    with patch("schedulers.ocr_processor.OCRService.is_available", return_value=True):
        return asyncio.run(proc.run())


def test_run_aggregates_stats_and_cleans_up_only_deleted_jobs(processor):
    proc, session = processor
    proc.ocr_service.process_queue.side_effect = [
        {"processed": 2, "failed": 1, "succeeded": 1},
        {"processed": 3, "failed": 4, "succeeded": 0},
    ]
    proc.ocr_service.cleanup_old_jobs.side_effect = [5, 0]

    first = _run(proc)
    second = _run(proc)

    assert first == {"processed": 2, "failed": 1, "succeeded": 1, "cleaned_up": 5}
    assert second == {"processed": 3, "failed": 4, "succeeded": 0}
    assert "cleaned_up" not in second
    assert proc.stats["total_runs"] == 2
    assert proc.stats["jobs_processed"] == 5
    assert proc.stats["jobs_failed"] == 5
    assert proc.last_status == "success"
    assert isinstance(proc.last_run_time, datetime)
    assert proc.last_run_time.tzinfo is not None
    assert isinstance(proc.stats["last_process_time"], datetime)
    assert proc.stats["last_process_time"] >= proc.last_run_time

    assert proc.ocr_service.process_queue.call_count == 2
    for call in proc.ocr_service.process_queue.call_args_list:
        assert call.kwargs["db"] is session
        assert call.kwargs["batch_size"] == 2
        assert call.kwargs["max_retries"] == MAX_OCR_RETRIES
    assert proc.ocr_service.cleanup_old_jobs.call_count == 2
    for call in proc.ocr_service.cleanup_old_jobs.call_args_list:
        assert call.args == (session,)
        assert call.kwargs == {"days": 7}
    assert session.close.call_count == 2


def test_run_with_nothing_queued_does_not_clean_old_jobs(processor):
    proc, session = processor

    result = _run(proc)

    assert result == {"processed": 0, "failed": 0, "succeeded": 0}
    assert proc.stats["total_runs"] == 1
    assert proc.stats["jobs_processed"] == 0
    assert proc.stats["jobs_failed"] == 0
    assert proc.last_status == "success"
    proc.ocr_service.cleanup_old_jobs.assert_not_called()
    session.close.assert_called_once()


def test_run_skips_when_ocr_is_unavailable_and_leaves_stats_untouched(processor):
    proc, session = processor
    config = Mock()
    config.get_import.return_value = {"enable_ocr": True}
    proc.config_loader = config

    with patch("schedulers.ocr_processor.OCRService.is_available", return_value=False):
        result = asyncio.run(proc.run())

    assert result == {"skipped": True, "reason": "OCR not available"}
    assert proc.stats["total_runs"] == 0
    assert proc.stats["jobs_processed"] == 0
    assert proc.stats["jobs_failed"] == 0
    assert proc.last_status is None
    assert proc.last_run_time is None
    config.get_import.assert_not_called()
    proc.ocr_service.process_queue.assert_not_called()
    session.close.assert_not_called()


def test_run_skips_when_config_disables_ocr(processor):
    proc, session = processor
    config = Mock()
    config.get_import.return_value = {"enable_ocr": False}
    proc.config_loader = config

    with patch("schedulers.ocr_processor.OCRService.is_available", return_value=True):
        result = asyncio.run(proc.run())

    assert result == {"skipped": True, "reason": "OCR disabled in config"}
    assert proc.stats["total_runs"] == 0
    assert proc.last_status is None
    config.get_import.assert_called_once_with()
    proc.ocr_service.process_queue.assert_not_called()
    session.close.assert_not_called()


def test_run_processes_when_enable_ocr_is_missing_from_config(processor):
    """``enable_ocr`` defaults to enabled when the import config omits it."""
    proc, session = processor
    config = Mock()
    config.get_import.return_value = {}
    proc.config_loader = config
    proc.ocr_service.process_queue.return_value = {"processed": 1, "failed": 0, "succeeded": 1}
    proc.ocr_service.cleanup_old_jobs.return_value = 2

    result = _run(proc)

    assert result["processed"] == 1
    assert result["cleaned_up"] == 2
    assert proc.stats["jobs_processed"] == 1
    assert proc.last_status == "success"
    session.close.assert_called_once()


def test_run_returns_error_when_queue_processing_raises(processor):
    proc, session = processor
    proc.ocr_service.process_queue.side_effect = RuntimeError("ocr blew up")
    proc.stats["jobs_processed"] = 4

    result = _run(proc)

    assert result == {"error": "ocr blew up"}
    assert proc.last_status == "failed"
    assert proc.stats["total_runs"] == 1
    assert proc.stats["jobs_processed"] == 4
    assert proc.stats["jobs_failed"] == 0
    assert proc.stats["last_process_time"] is None
    proc.ocr_service.cleanup_old_jobs.assert_not_called()
    session.close.assert_called_once()


def test_run_returns_error_when_availability_check_raises(processor):
    proc, session = processor

    with patch(
        "schedulers.ocr_processor.OCRService.is_available",
        side_effect=RuntimeError("probe failed"),
    ):
        result = asyncio.run(proc.run())

    assert result == {"error": "probe failed"}
    assert proc.last_status == "failed"
    assert proc.stats["total_runs"] == 0
    assert proc.last_run_time is None
    proc.ocr_service.process_queue.assert_not_called()
    session.close.assert_not_called()


def test_shutdown_stops_the_queue_service_before_the_executor():
    session = Mock()
    proc = OCRProcessor(Mock(return_value=session), max_workers=1, batch_size=2)
    order = []
    real_shutdown = proc.executor.shutdown

    def service_shutdown():
        order.append("service")

    def executor_shutdown(*args, **kwargs):
        wait = kwargs.get("wait", args[0] if args else None)
        order.append(("executor", wait))
        return real_shutdown(*args, **kwargs)

    proc.ocr_service.shutdown = service_shutdown
    proc.executor.shutdown = executor_shutdown

    proc.shutdown()

    assert order == ["service", ("executor", True)]

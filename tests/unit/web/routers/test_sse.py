"""
Test suite for Server-Sent Events router and EventBus.

Covers:
- EventBus subscribe / unsubscribe / publish behavior
- QueueFull drop semantics (slow clients)
- SSE endpoints: auth (valid token, invalid token, missing token)
- SSE endpoints: 503 when event bus not ready
- SSE endpoints: correct media type and headers
- _event_stream: events filtered by channel
- _event_stream: keepalive emitted on timeout
- _event_stream: unsubscribe called on CancelledError (client disconnect)
- _verify_token: empty token, None auth_manager, JWT token, API token
- background_tasks: download_monitoring_task always publishes
- background_tasks: ocr_processing_task publishes only when processed > 0
"""

import asyncio
import json
import unittest.mock
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Path setup handled by conftest.py

from web.app import EventBus
import web.routers.sse as sse_module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def event_bus():
    """Fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def mock_auth_manager():
    """Auth manager that accepts 'valid-token' and rejects everything else."""
    mgr = Mock()
    mgr.verify_token.side_effect = lambda t: (t == "valid-token", None)
    mgr.verify_api_token.side_effect = lambda t: (t == "valid-api-token", None)
    return mgr


@pytest.fixture
def sse_app(event_bus, mock_auth_manager):
    """Minimal FastAPI app with the SSE router and injected dependencies."""
    app = FastAPI()
    # Wire up dependencies before including the router
    sse_module.set_dependencies(event_bus, mock_auth_manager)
    app.include_router(sse_module.router)
    return app


@pytest.fixture
def sse_client(sse_app):
    """Synchronous TestClient for SSE endpoint smoke tests."""
    with TestClient(sse_app, raise_server_exceptions=True) as client:
        yield client


# =============================================================================
# EventBus unit tests
# =============================================================================


class TestEventBusSubscribe:
    """EventBus.subscribe / unsubscribe lifecycle."""

    def test_subscribe_returns_asyncio_queue(self, event_bus):
        """subscribe() returns an asyncio.Queue."""
        q = event_bus.subscribe()
        assert isinstance(q, asyncio.Queue)

    def test_subscribe_adds_to_subscribers(self, event_bus):
        """Each call to subscribe() grows the internal list."""
        assert len(event_bus._subscribers) == 0
        q1 = event_bus.subscribe()
        assert len(event_bus._subscribers) == 1
        q2 = event_bus.subscribe()
        assert len(event_bus._subscribers) == 2

    def test_each_subscriber_gets_independent_queue(self, event_bus):
        """Two subscribers receive separate queue objects."""
        q1 = event_bus.subscribe()
        q2 = event_bus.subscribe()
        assert q1 is not q2

    def test_unsubscribe_removes_queue(self, event_bus):
        """unsubscribe() removes the queue from the subscriber list."""
        q = event_bus.subscribe()
        assert len(event_bus._subscribers) == 1
        event_bus.unsubscribe(q)
        assert len(event_bus._subscribers) == 0

    def test_unsubscribe_unknown_queue_does_not_raise(self, event_bus):
        """unsubscribe() with a queue that was never subscribed must not raise."""
        orphan_q = asyncio.Queue()
        # Should be a no-op, not a ValueError
        event_bus.unsubscribe(orphan_q)

    def test_unsubscribe_only_removes_target_queue(self, event_bus):
        """Unsubscribing one queue leaves the others intact."""
        q1 = event_bus.subscribe()
        q2 = event_bus.subscribe()
        event_bus.unsubscribe(q1)
        assert q2 in event_bus._subscribers
        assert q1 not in event_bus._subscribers


class TestEventBusPublish:
    """EventBus.publish behavior."""

    @pytest.mark.asyncio
    async def test_publish_delivers_to_all_subscribers(self):
        """publish() puts the event on every subscriber's queue."""
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()

        await bus.publish("downloads", {"trigger": "update"})

        assert not q1.empty()
        assert not q2.empty()

        event1 = q1.get_nowait()
        event2 = q2.get_nowait()

        assert event1 == {"channel": "downloads", "data": {"trigger": "update"}}
        assert event2 == {"channel": "downloads", "data": {"trigger": "update"}}

    @pytest.mark.asyncio
    async def test_publish_wraps_channel_and_data(self):
        """Published item contains both 'channel' and 'data' keys."""
        bus = EventBus()
        q = bus.subscribe()

        await bus.publish("ocr_queue", {"processed": 3})

        item = q.get_nowait()
        assert item["channel"] == "ocr_queue"
        assert item["data"] == {"processed": 3}

    @pytest.mark.asyncio
    async def test_publish_drops_event_for_full_queue(self):
        """When a subscriber's queue is full, the event is silently dropped
        and other subscribers are NOT affected."""
        bus = EventBus()
        slow_q = bus.subscribe()  # will be filled to capacity
        fast_q = bus.subscribe()  # always empty — should still get events

        # Fill slow_q to maxsize (10)
        for i in range(10):
            slow_q.put_nowait({"channel": "x", "data": {"i": i}})

        # This publish should NOT raise; slow_q event is dropped, fast_q gets it
        await bus.publish("downloads", {"trigger": "update"})

        # fast_q should have received the event
        assert not fast_q.empty()
        item = fast_q.get_nowait()
        assert item["channel"] == "downloads"

        # slow_q queue size should still be exactly 10 (event was dropped, not added)
        assert slow_q.qsize() == 10

    @pytest.mark.asyncio
    async def test_publish_with_no_subscribers_is_noop(self):
        """publish() with zero subscribers must not raise."""
        bus = EventBus()
        await bus.publish("downloads", {"trigger": "update"})  # no-op

    @pytest.mark.asyncio
    async def test_publish_after_unsubscribe_does_not_deliver(self):
        """A queue that was unsubscribed no longer receives events."""
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)

        await bus.publish("downloads", {"trigger": "update"})

        assert q.empty(), "Unsubscribed queue should not receive published events"


# =============================================================================
# _verify_token unit tests (tested through the module-level helper)
# =============================================================================


class TestVerifyToken:  # pylint: disable=attribute-defined-outside-init
    """Test the _verify_token helper in isolation."""

    def setup_method(self):
        """Restore sse module state between tests."""
        self._orig_bus = sse_module._event_bus
        self._orig_auth = sse_module._auth_manager

    def teardown_method(self):
        sse_module._event_bus = self._orig_bus
        sse_module._auth_manager = self._orig_auth

    def test_returns_false_when_auth_manager_is_none(self):
        """No auth manager → always False (dependency not initialized)."""
        sse_module._auth_manager = None
        assert sse_module._verify_token("any-token") is False

    def test_returns_false_for_empty_string_token(self, mock_auth_manager):
        """Empty token string → False without calling auth manager."""
        sse_module._auth_manager = mock_auth_manager
        assert sse_module._verify_token("") is False

    def test_returns_true_for_valid_jwt_token(self, mock_auth_manager):
        """Valid JWT token accepted via verify_token."""
        sse_module._auth_manager = mock_auth_manager
        assert sse_module._verify_token("valid-token") is True

    def test_returns_true_for_valid_api_token(self, mock_auth_manager):
        """API token accepted as fallback when JWT verification fails."""
        sse_module._auth_manager = mock_auth_manager
        assert sse_module._verify_token("valid-api-token") is True

    def test_returns_false_for_invalid_token(self, mock_auth_manager):
        """Unrecognized token → False."""
        sse_module._auth_manager = mock_auth_manager
        assert sse_module._verify_token("bogus-token") is False


# =============================================================================
# SSE endpoint: authentication and service-ready checks
# =============================================================================


class TestSSEDownloadsEndpointAuth:
    """GET /api/sse/downloads — token and readiness validation."""

    def test_missing_token_returns_422(self, sse_client):
        """Omitting the required `token` query parameter returns 422."""
        response = sse_client.get("/api/sse/downloads")
        assert response.status_code == 422

    def test_invalid_token_returns_401(self, sse_client):
        """An unrecognized token returns 401 Unauthorized."""
        response = sse_client.get("/api/sse/downloads?token=bad-token")
        assert response.status_code == 401
        data = response.json()
        assert "token" in data["detail"].lower() or "invalid" in data["detail"].lower()

    def test_valid_token_does_not_return_401_or_503(self, sse_client):
        """A valid token passes authentication (no 401/503 response).

        _sse_response is patched so the streaming generator never runs,
        preventing the TestClient from blocking indefinitely.
        """
        from fastapi.responses import StreamingResponse

        async def _empty_stream():
            return
            yield  # make it an async generator

        with patch.object(
            sse_module,
            "_sse_response",
            return_value=StreamingResponse(_empty_stream(), media_type="text/event-stream"),
        ):
            response = sse_client.get("/api/sse/downloads?token=valid-token")

        assert response.status_code not in (401, 403, 503)

    def test_event_bus_not_ready_returns_503(self, mock_auth_manager):
        """When event_bus is None (dependency not yet set), return 503."""
        app = FastAPI()
        sse_module.set_dependencies(None, mock_auth_manager)
        app.include_router(sse_module.router)

        with TestClient(app) as client:
            response = client.get("/api/sse/downloads?token=valid-token")

        assert response.status_code == 503
        data = response.json()
        assert "not ready" in data["detail"].lower() or "service" in data["detail"].lower()

        # Restore
        sse_module.set_dependencies(EventBus(), mock_auth_manager)

    def test_valid_token_returns_text_event_stream(self, sse_client):
        """Successful authentication returns text/event-stream content type.

        _sse_response is patched so the streaming generator never runs,
        preventing the TestClient from blocking indefinitely.
        """
        from fastapi.responses import StreamingResponse

        async def _empty_stream():
            return
            yield

        with patch.object(
            sse_module,
            "_sse_response",
            return_value=StreamingResponse(
                _empty_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            ),
        ):
            response = sse_client.get("/api/sse/downloads?token=valid-token")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_valid_token_returns_sse_headers(self, sse_client):
        """Successful connection includes required SSE headers.

        _sse_response is patched so the streaming generator never runs,
        preventing the TestClient from blocking indefinitely.
        """
        from fastapi.responses import StreamingResponse

        async def _empty_stream():
            return
            yield

        with patch.object(
            sse_module,
            "_sse_response",
            return_value=StreamingResponse(
                _empty_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            ),
        ):
            response = sse_client.get("/api/sse/downloads?token=valid-token")

        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"


class TestSSEOCREndpointAuth:
    """GET /api/sse/ocr — mirrors download endpoint auth checks."""

    def test_missing_token_returns_422(self, sse_client):
        """Omitting the required `token` query parameter returns 422."""
        response = sse_client.get("/api/sse/ocr")
        assert response.status_code == 422

    def test_invalid_token_returns_401(self, sse_client):
        """An unrecognized token returns 401 Unauthorized."""
        response = sse_client.get("/api/sse/ocr?token=garbage")
        assert response.status_code == 401

    def test_valid_token_does_not_return_401_or_503(self, sse_client):
        """A valid token passes authentication (no 401/503 response).

        _sse_response is patched so the streaming generator never runs,
        preventing the TestClient from blocking indefinitely.
        """
        from fastapi.responses import StreamingResponse

        async def _empty_stream():
            return
            yield

        with patch.object(
            sse_module,
            "_sse_response",
            return_value=StreamingResponse(_empty_stream(), media_type="text/event-stream"),
        ):
            response = sse_client.get("/api/sse/ocr?token=valid-token")

        assert response.status_code not in (401, 403, 503)

    def test_event_bus_not_ready_returns_503(self, mock_auth_manager):
        """When event_bus is None, return 503."""
        app = FastAPI()
        sse_module.set_dependencies(None, mock_auth_manager)
        app.include_router(sse_module.router)

        with TestClient(app) as client:
            response = client.get("/api/sse/ocr?token=valid-token")

        assert response.status_code == 503

        # Restore
        sse_module.set_dependencies(EventBus(), mock_auth_manager)


# =============================================================================
# _event_stream behavior: channel filtering, keepalive, cleanup
# =============================================================================


class TestEventStream:
    """Async tests for the _event_stream generator."""

    @pytest.mark.asyncio
    async def test_only_matching_channel_events_are_yielded(self):
        """Events on a different channel are consumed but not forwarded to the client."""
        bus = EventBus()
        orig_bus = sse_module._event_bus
        sse_module._event_bus = bus

        try:
            results = []

            async def collect():
                gen = sse_module._event_stream("download_queue")
                # The generator will consume the first event (ocr, wrong channel)
                # silently and yield the second (download_queue, matching channel)
                async for chunk in gen:
                    results.append(chunk)
                    break  # stop after first yielded value

            # Start the collector task so _event_stream can subscribe first,
            # then publish events so they land in the generator's queue.
            task = asyncio.create_task(collect())
            await asyncio.sleep(0)  # yield to let _event_stream call bus.subscribe()
            await bus.publish("ocr_queue", {"trigger": "update"})  # wrong channel
            await bus.publish("download_queue", {"trigger": "update"})  # right channel

            # Run with a timeout so the test never hangs
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)

            assert len(results) == 1
            assert '"trigger": "update"' in results[0] or "update" in results[0]
            # The SSE data line must start with "data: "
            assert results[0].startswith("data: ")
        finally:
            sse_module._event_bus = orig_bus

    @pytest.mark.asyncio
    async def test_keepalive_emitted_on_timeout(self):
        """When no event arrives within SSE_KEEPALIVE_TIMEOUT seconds, a
        keepalive comment is yielded."""
        bus = EventBus()
        orig_bus = sse_module._event_bus
        orig_timeout = sse_module.SSE_KEEPALIVE_TIMEOUT
        sse_module._event_bus = bus
        # Use a very short timeout so the test is fast
        sse_module.SSE_KEEPALIVE_TIMEOUT = 0.01

        try:
            results = []

            async def collect():
                gen = sse_module._event_stream("download_queue")
                async for chunk in gen:
                    results.append(chunk)
                    break  # stop after the keepalive

            await asyncio.wait_for(collect(), timeout=2.0)

            assert len(results) == 1
            assert results[0] == ": keepalive\n\n"
        finally:
            sse_module._event_bus = orig_bus
            sse_module.SSE_KEEPALIVE_TIMEOUT = orig_timeout

    @pytest.mark.asyncio
    async def test_cancelled_error_triggers_unsubscribe(self):
        """CancelledError causes the finally block to call unsubscribe()."""
        bus = EventBus()
        orig_bus = sse_module._event_bus
        orig_timeout = sse_module.SSE_KEEPALIVE_TIMEOUT
        sse_module._event_bus = bus
        sse_module.SSE_KEEPALIVE_TIMEOUT = 0.01

        unsubscribed = []
        orig_unsub = bus.unsubscribe

        def tracking_unsubscribe(q):
            unsubscribed.append(q)
            orig_unsub(q)

        bus.unsubscribe = tracking_unsubscribe

        try:
            # Start collecting but cancel the task immediately
            async def collect():
                gen = sse_module._event_stream("download_queue")
                async for _ in gen:
                    pass

            task = asyncio.create_task(collect())
            await asyncio.sleep(0)  # let it start
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Give the generator's finally block a moment to execute
            await asyncio.sleep(0.05)

            assert len(unsubscribed) == 1, "Expected unsubscribe() to be called in finally block on CancelledError"
        finally:
            sse_module._event_bus = orig_bus
            sse_module.SSE_KEEPALIVE_TIMEOUT = orig_timeout

    @pytest.mark.asyncio
    async def test_yielded_data_is_valid_json(self):
        """Each SSE data line contains valid JSON in the 'data: ...' frame."""
        bus = EventBus()
        orig_bus = sse_module._event_bus
        sse_module._event_bus = bus

        try:
            results = []

            async def collect():
                gen = sse_module._event_stream("download_queue")
                async for chunk in gen:
                    results.append(chunk)
                    break

            # Start the collector task so _event_stream subscribes first,
            # then publish so the event lands in the generator's queue.
            task = asyncio.create_task(collect())
            await asyncio.sleep(0)  # yield to let _event_stream call bus.subscribe()
            await bus.publish("download_queue", {"trigger": "update", "count": 5})

            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)

            assert len(results) == 1
            line = results[0]
            assert line.startswith("data: ")
            payload_str = line[len("data: ") :].strip()
            payload = json.loads(payload_str)
            assert payload == {"trigger": "update", "count": 5}
        finally:
            sse_module._event_bus = orig_bus


# =============================================================================
# Background task publish behavior
# =============================================================================


class TestDownloadMonitoringTaskPublish:
    """download_monitoring_task always publishes 'download_queue'."""

    @pytest.mark.asyncio
    async def test_download_monitoring_always_publishes(self):
        """download_monitoring_task unconditionally publishes to 'download_queue'
        after a successful run, regardless of whether any downloads completed."""
        from web.background_tasks import download_monitoring_task

        mock_monitor = AsyncMock()
        mock_monitor.run = AsyncMock(return_value=None)

        bus = AsyncMock()

        app_state = MagicMock()
        app_state.download_monitor_task = mock_monitor
        app_state.event_bus = bus
        app_state.tasks_config.get.return_value = 60  # interval

        await download_monitoring_task(app_state)

        bus.publish.assert_called_once_with("download_queue", {"trigger": "update"})

    @pytest.mark.asyncio
    async def test_download_monitoring_skipped_when_no_monitor(self):
        """download_monitoring_task is a no-op when download_monitor_task is None."""
        from web.background_tasks import download_monitoring_task

        bus = AsyncMock()
        app_state = MagicMock()
        app_state.download_monitor_task = None
        app_state.event_bus = bus

        await download_monitoring_task(app_state)

        bus.publish.assert_not_called()


class TestOCRProcessingTaskPublish:
    """ocr_processing_task publishes 'ocr_queue' only when jobs processed > 0."""

    @pytest.mark.asyncio
    async def test_ocr_task_publishes_when_items_processed(self):
        """When OCR processes ≥1 job, event_bus.publish('ocr_queue') is called."""
        from web.background_tasks import ocr_processing_task

        mock_processor = MagicMock()
        mock_processor.run = AsyncMock(return_value={"processed": 2, "failed": 0})
        mock_processor.next_run_time = None

        bus = AsyncMock()

        app_state = MagicMock()
        app_state.ocr_processor_task = mock_processor
        app_state.event_bus = bus
        app_state.tasks_config.get.return_value = 60

        await ocr_processing_task(app_state)

        bus.publish.assert_called_once_with("ocr_queue", {"trigger": "update"})

    @pytest.mark.asyncio
    async def test_ocr_task_does_not_publish_when_nothing_processed(self):
        """When OCR processes 0 jobs (idle run), event_bus.publish is NOT called."""
        from web.background_tasks import ocr_processing_task

        mock_processor = MagicMock()
        mock_processor.run = AsyncMock(return_value={"processed": 0, "failed": 0})
        mock_processor.next_run_time = None

        bus = AsyncMock()

        app_state = MagicMock()
        app_state.ocr_processor_task = mock_processor
        app_state.event_bus = bus
        app_state.tasks_config.get.return_value = 60

        await ocr_processing_task(app_state)

        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_ocr_task_does_not_publish_on_exception(self):
        """If the OCR processor raises, event_bus.publish is NOT called."""
        from web.background_tasks import ocr_processing_task

        mock_processor = MagicMock()
        mock_processor.run = AsyncMock(side_effect=RuntimeError("OCR crash"))
        mock_processor.next_run_time = None

        bus = AsyncMock()

        app_state = MagicMock()
        app_state.ocr_processor_task = mock_processor
        app_state.event_bus = bus
        app_state.tasks_config.get.return_value = 60

        await ocr_processing_task(app_state)  # must not re-raise

        bus.publish.assert_not_called()

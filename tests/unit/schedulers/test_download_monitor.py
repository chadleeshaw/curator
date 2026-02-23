"""
Unit tests for DownloadMonitor notify_callback wiring.

Covers:
- notify_callback parameter is accepted and propagated to IA clients
- _attach_notify_callback sets on_progress on clients that support it
- Clients without on_progress are silently skipped
- notify_callback=None leaves clients unchanged
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from schedulers.download_monitor import DownloadMonitor


def _make_monitor(notify_callback=None, clients=None):
    """Build a DownloadMonitor with minimal mocked dependencies."""
    download_manager = MagicMock()
    if clients is not None:
        download_manager.download_clients = clients
    else:
        download_manager.download_clients = {}

    return DownloadMonitor(
        download_manager=download_manager,
        file_importer=MagicMock(),
        session_factory=MagicMock(),
        downloads_dir="/tmp/test_downloads",
        notify_callback=notify_callback,
    )


class TestDownloadMonitorNotifyCallback:
    """Tests for the notify_callback parameter on DownloadMonitor."""

    def test_notify_callback_none_leaves_clients_unchanged(self):
        """When notify_callback is None, no on_progress is set on clients."""
        ia_client = MagicMock()
        ia_client.on_progress = None
        monitor = _make_monitor(notify_callback=None, clients={"ia": ia_client})

        # on_progress must not have been assigned
        assert ia_client.on_progress is None

    def test_attach_notify_callback_sets_on_progress_on_ia_client(self):
        """_attach_notify_callback propagates the callback to clients with on_progress."""
        cb = Mock()
        ia_client = MagicMock(spec=["on_progress", "name"])
        ia_client.name = "ia"
        ia_client.on_progress = None

        monitor = _make_monitor(notify_callback=cb, clients={"ia": ia_client})

        assert ia_client.on_progress is cb

    def test_attach_notify_callback_skips_clients_without_on_progress(self):
        """Clients lacking on_progress are silently skipped without raising."""
        cb = Mock()
        # A client with no on_progress attribute
        plain_client = MagicMock(spec=["name"])
        plain_client.name = "sabnzbd"

        # Should not raise
        monitor = _make_monitor(notify_callback=cb, clients={"sabnzbd": plain_client})

    def test_attach_notify_callback_handles_multiple_clients(self):
        """All clients that expose on_progress receive the same callback."""
        cb = Mock()

        ia_client_1 = MagicMock(spec=["on_progress", "name"])
        ia_client_1.name = "ia1"
        ia_client_1.on_progress = None

        ia_client_2 = MagicMock(spec=["on_progress", "name"])
        ia_client_2.name = "ia2"
        ia_client_2.on_progress = None

        plain_client = MagicMock(spec=["name"])
        plain_client.name = "sabnzbd"

        monitor = _make_monitor(
            notify_callback=cb,
            clients={"ia1": ia_client_1, "ia2": ia_client_2, "sabnzbd": plain_client},
        )

        assert ia_client_1.on_progress is cb
        assert ia_client_2.on_progress is cb

    def test_notify_callback_can_be_called(self):
        """The callback installed on the IA client is actually callable."""
        call_log = []

        def cb():
            call_log.append(True)

        # Use a plain Mock (no spec) so pylint knows on_progress is callable after assignment.
        ia_client = MagicMock()
        ia_client.name = "ia"
        ia_client.on_progress = None

        monitor = _make_monitor(notify_callback=cb, clients={"ia": ia_client})

        # Simulate what the IA client does: call on_progress
        retrieved_cb = ia_client.on_progress
        retrieved_cb()  # pylint: disable=not-callable
        assert call_log == [True]

    def test_monitor_stats_initialised_regardless_of_callback(self):
        """DownloadMonitor stats dict is always present, with or without a callback."""
        monitor_no_cb = _make_monitor(notify_callback=None)
        monitor_with_cb = _make_monitor(notify_callback=Mock())

        for monitor in (monitor_no_cb, monitor_with_cb):
            assert "total_runs" in monitor.stats
            assert "client_downloads_processed" in monitor.stats
            assert monitor.stats["total_runs"] == 0

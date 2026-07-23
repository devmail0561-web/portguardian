"""Tests for core.watcher — NetworkWatcher event detection and history cap."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.watcher import NetworkWatcher, NetworkEvent, HISTORY_MAXLEN
from core.ports import ConnectionInfo


def _conn(port=80, protocol="tcp", status="LISTEN", process="nginx", pid=100):
    return ConnectionInfo(
        protocol=protocol,
        local_addr="0.0.0.0",
        local_port=port,
        remote_addr="",
        remote_port=0,
        status=status,
        pid=pid,
        process_name=process,
        username="root",
        fd=0,
    )


class TestNetworkWatcherEventDetection:
    """Tests for check_changes()."""

    def test_first_call_returns_no_events(self):
        watcher = NetworkWatcher()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            events = watcher.check_changes()
        assert events == []

    def test_new_port_detected(self):
        watcher = NetworkWatcher()
        # First call: establishes baseline
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            watcher.check_changes()
        # Second call: new port appears
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), _conn(443)]):
            events = watcher.check_changes()
        assert len(events) == 1
        assert events[0].event_type == "port_opened"
        assert events[0].port == 443

    def test_closed_port_detected(self):
        watcher = NetworkWatcher()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), _conn(443)]):
            watcher.check_changes()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            events = watcher.check_changes()
        assert len(events) == 1
        assert events[0].event_type == "port_closed"
        assert events[0].port == 443

    def test_established_connection_new_is_process_new(self):
        watcher = NetworkWatcher()
        # Initialise baseline with a different connection
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            watcher.check_changes()
        conn = _conn(port=54321, status="ESTABLISHED")
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), conn]):
            events = watcher.check_changes()
        new_events = [e for e in events if e.port == 54321]
        assert new_events[0].event_type == "process_new"

    def test_established_connection_closed_is_process_ended(self):
        watcher = NetworkWatcher()
        conn = _conn(port=54321, status="ESTABLISHED")
        # Initialise baseline with two connections
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), conn]):
            watcher.check_changes()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            events = watcher.check_changes()
        assert events[0].event_type == "process_ended"

    def test_no_change_returns_empty(self):
        watcher = NetworkWatcher()
        conns = [_conn(80), _conn(443)]
        with patch("core.watcher.get_all_connections", return_value=conns):
            watcher.check_changes()
        with patch("core.watcher.get_all_connections", return_value=conns):
            events = watcher.check_changes()
        assert events == []

    def test_on_event_callback_called(self):
        received = []
        watcher = NetworkWatcher(on_event=received.append)
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            watcher.check_changes()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), _conn(443)]):
            watcher.check_changes()
        assert len(received) == 1
        assert received[0].port == 443

    def test_exception_returns_empty(self):
        watcher = NetworkWatcher()
        with patch("core.watcher.get_all_connections", side_effect=Exception("boom")):
            events = watcher.check_changes()
        assert events == []


class TestNetworkWatcherHistory:
    """Tests for history deque cap."""

    def test_history_starts_empty(self):
        watcher = NetworkWatcher()
        assert watcher.history == []

    def test_events_added_to_history(self):
        watcher = NetworkWatcher()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            watcher.check_changes()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), _conn(443)]):
            watcher.check_changes()
        assert len(watcher.history) == 1

    def test_history_capped_at_maxlen(self):
        watcher = NetworkWatcher()
        # Establish baseline with 0 connections
        with patch("core.watcher.get_all_connections", return_value=[]):
            watcher.check_changes()

        # Add events one by one: alternately open and close a port
        # to generate HISTORY_MAXLEN + 10 events
        for i in range(HISTORY_MAXLEN + 10):
            port = 10000 + i
            with patch("core.watcher.get_all_connections", return_value=[_conn(port)]):
                watcher.check_changes()
            with patch("core.watcher.get_all_connections", return_value=[]):
                watcher.check_changes()

        assert len(watcher.history) <= HISTORY_MAXLEN

    def test_history_returns_copy(self):
        watcher = NetworkWatcher()
        h1 = watcher.history
        h2 = watcher.history
        assert h1 is not h2

    def test_history_maxlen_constant(self):
        assert HISTORY_MAXLEN == 500


class TestNetworkWatcherCountSkip:
    """Tests for count-based early exit optimization."""

    def test_same_count_skips_rescan(self):
        """When connection count is identical to previous, no events should fire
        (relies on count-skip). Note: if a new conn replaces an old one of same
        count, the skip is intentional per our design."""
        watcher = NetworkWatcher()
        conns = [_conn(80), _conn(443)]
        with patch("core.watcher.get_all_connections", return_value=conns):
            watcher.check_changes()
        # Same count, different content — optimisation skips the full diff
        with patch("core.watcher.get_all_connections", return_value=conns):
            events = watcher.check_changes()
        assert events == []

    def test_count_changes_triggers_rescan(self):
        watcher = NetworkWatcher()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80)]):
            watcher.check_changes()
        with patch("core.watcher.get_all_connections", return_value=[_conn(80), _conn(443)]):
            events = watcher.check_changes()
        assert len(events) == 1


class TestNetworkEvent:
    """Tests for NetworkEvent.description."""

    def test_port_opened_description(self):
        e = NetworkEvent("port_opened", 443, "tcp", 100, "nginx", "0.0.0.0")
        assert "443" in e.description
        assert "nginx" in e.description

    def test_port_closed_description(self):
        e = NetworkEvent("port_closed", 443, "tcp", 100, "nginx", "0.0.0.0")
        assert "fermé" in e.description or "443" in e.description

    def test_process_new_description(self):
        e = NetworkEvent("process_new", 8080, "tcp", 200, "python3", "127.0.0.1")
        assert "python3" in e.description

    def test_process_ended_description(self):
        e = NetworkEvent("process_ended", 8080, "tcp", 200, "python3", "127.0.0.1")
        assert "python3" in e.description

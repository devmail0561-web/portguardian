"""Tests for core.baseline — snapshot and deviation detection."""

import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.baseline import save_baseline, load_baseline, get_deviations, BaselineEntry
from core.ports import ConnectionInfo


def _conn(port=80, protocol="tcp", status="LISTEN", process="nginx", user="root"):
    return ConnectionInfo(
        protocol=protocol,
        local_addr="0.0.0.0",
        local_port=port,
        remote_addr="",
        remote_port=0,
        status=status,
        pid=100,
        process_name=process,
        username=user,
        fd=0,
    )


class TestSaveLoadBaseline:
    """Tests for save_baseline and load_baseline."""

    def test_save_creates_file(self, tmp_path):
        with patch("core.baseline.BASELINE_FILE", tmp_path / "baseline.json"):
            save_baseline([_conn(80), _conn(443)])
            assert (tmp_path / "baseline.json").exists()

    def test_load_returns_entries(self, tmp_path):
        bf = tmp_path / "baseline.json"
        with patch("core.baseline.BASELINE_FILE", bf):
            conns = [_conn(80), _conn(443)]
            save_baseline(conns)
            result = load_baseline()
            assert result is not None
            ts, entries = result
            assert len(entries) == 2
            assert isinstance(entries[0], BaselineEntry)

    def test_load_returns_none_when_no_file(self, tmp_path):
        with patch("core.baseline.BASELINE_FILE", tmp_path / "missing.json"):
            assert load_baseline() is None

    def test_timestamp_is_recent(self, tmp_path):
        bf = tmp_path / "baseline.json"
        with patch("core.baseline.BASELINE_FILE", bf):
            before = time.time()
            save_baseline([_conn()])
            result = load_baseline()
            assert result is not None
            ts, _ = result
            assert ts >= before

    def test_entries_preserve_fields(self, tmp_path):
        bf = tmp_path / "baseline.json"
        with patch("core.baseline.BASELINE_FILE", bf):
            save_baseline([_conn(port=8080, protocol="tcp6", process="python3")])
            _, entries = load_baseline()
            e = entries[0]
            assert e.local_port == 8080
            assert e.protocol == "tcp6"
            assert e.process_name == "python3"

    def test_overwrite_replaces_previous(self, tmp_path):
        bf = tmp_path / "baseline.json"
        with patch("core.baseline.BASELINE_FILE", bf):
            save_baseline([_conn(80), _conn(443), _conn(22)])
            save_baseline([_conn(80)])  # overwrite with 1 entry
            _, entries = load_baseline()
            assert len(entries) == 1

    def test_empty_connections_saved(self, tmp_path):
        bf = tmp_path / "baseline.json"
        with patch("core.baseline.BASELINE_FILE", bf):
            save_baseline([])
            result = load_baseline()
            assert result is not None
            _, entries = result
            assert entries == []


class TestGetDeviations:
    """Tests for get_deviations."""

    def _make_baseline(self, conns):
        from core.baseline import _conn_to_entry
        return [_conn_to_entry(c) for c in conns]

    def test_no_change_returns_empty(self):
        conns = [_conn(80), _conn(443)]
        baseline = self._make_baseline(conns)
        new, gone = get_deviations(conns, baseline)
        assert new == []
        assert gone == []

    def test_new_connection_detected(self):
        old = [_conn(80)]
        baseline = self._make_baseline(old)
        current = [_conn(80), _conn(443)]
        new, gone = get_deviations(current, baseline)
        assert len(new) == 1
        assert new[0].local_port == 443
        assert gone == []

    def test_gone_connection_detected(self):
        old = [_conn(80), _conn(443)]
        baseline = self._make_baseline(old)
        current = [_conn(80)]
        new, gone = get_deviations(current, baseline)
        assert new == []
        assert len(gone) == 1
        assert gone[0].local_port == 443

    def test_both_new_and_gone(self):
        old = [_conn(80), _conn(443)]
        baseline = self._make_baseline(old)
        current = [_conn(80), _conn(8080)]
        new, gone = get_deviations(current, baseline)
        assert len(new) == 1 and new[0].local_port == 8080
        assert len(gone) == 1 and gone[0].local_port == 443

    def test_process_change_counts_as_deviation(self):
        # Same port/proto/addr but different process = new entry
        old = [_conn(80, process="nginx")]
        baseline = self._make_baseline(old)
        current = [_conn(80, process="apache2")]
        new, gone = get_deviations(current, baseline)
        assert len(new) == 1
        assert len(gone) == 1

    def test_empty_baseline_all_are_new(self):
        current = [_conn(80), _conn(443)]
        new, gone = get_deviations(current, [])
        assert len(new) == 2
        assert gone == []

    def test_empty_current_all_are_gone(self):
        old = [_conn(80), _conn(443)]
        baseline = self._make_baseline(old)
        new, gone = get_deviations([], baseline)
        assert new == []
        assert len(gone) == 2

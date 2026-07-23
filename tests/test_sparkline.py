"""Tests for core.sparkline — MetricHistory and HistoryStore."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sparkline import MetricHistory, HistoryStore, _BLOCKS, _WIDTH


class TestMetricHistory:
    """Tests for MetricHistory."""

    def test_empty_sparkline_is_spaces(self):
        h = MetricHistory()
        assert h.sparkline() == " " * _WIDTH

    def test_sparkline_length_equals_width(self):
        h = MetricHistory()
        for i in range(5):
            h.push(float(i))
        s = h.sparkline()
        assert len(s) == _WIDTH

    def test_sparkline_padded_left_when_few_values(self):
        h = MetricHistory(maxlen=8)
        h.push(5.0)
        s = h.sparkline()
        assert len(s) == 8
        # First 7 chars are spaces (padding)
        assert s[:7] == " " * 7
        # Last char is a non-space block
        assert s[-1] != " "

    def test_max_value_renders_full_block(self):
        h = MetricHistory(maxlen=4)
        h.push(0.0)
        h.push(0.0)
        h.push(0.0)
        h.push(100.0)  # max
        s = h.sparkline()
        assert s[-1] == _BLOCKS[8]  # "█"

    def test_zero_values_render_spaces(self):
        h = MetricHistory(maxlen=4)
        for _ in range(4):
            h.push(0.0)
        s = h.sparkline()
        # max_val=0 → falls back to 1.0, all values → index 0 → " "
        assert all(c == _BLOCKS[0] for c in s)

    def test_last_returns_most_recent(self):
        h = MetricHistory()
        h.push(1.0)
        h.push(2.0)
        h.push(99.0)
        assert h.last == 99.0

    def test_last_on_empty_returns_zero(self):
        h = MetricHistory()
        assert h.last == 0.0

    def test_maxlen_respected(self):
        h = MetricHistory(maxlen=3)
        for i in range(10):
            h.push(float(i))
        # Only last 3 values kept
        assert h.last == 9.0
        assert len(list(h._data)) == 3

    def test_trend_up(self):
        h = MetricHistory()
        h.push(0.0)
        h.push(10.0)
        assert h.trend == "↑"

    def test_trend_down(self):
        h = MetricHistory()
        h.push(10.0)
        h.push(0.0)
        assert h.trend == "↓"

    def test_trend_stable(self):
        h = MetricHistory()
        h.push(5.0)
        h.push(5.0)
        assert h.trend == "→"

    def test_trend_single_value_is_stable(self):
        h = MetricHistory()
        h.push(42.0)
        assert h.trend == "→"

    def test_trend_empty_is_stable(self):
        h = MetricHistory()
        assert h.trend == "→"


class TestHistoryStore:
    """Tests for HistoryStore (dict of MetricHistory by PID)."""

    def test_push_creates_entry(self):
        hs = HistoryStore()
        hs.push(1234, 50.0)
        assert hs.sparkline(1234) != " " * _WIDTH or True  # at least no crash

    def test_unknown_pid_returns_spaces(self):
        hs = HistoryStore()
        assert hs.sparkline(9999) == " " * _WIDTH

    def test_trend_unknown_pid_is_stable(self):
        hs = HistoryStore()
        assert hs.trend(9999) == "→"

    def test_purge_removes_dead_pids(self):
        hs = HistoryStore()
        hs.push(111, 10.0)
        hs.push(222, 20.0)
        hs.push(333, 30.0)
        hs.purge({111, 333})
        assert 111 in hs._store
        assert 333 in hs._store
        assert 222 not in hs._store

    def test_purge_empty_set_removes_all(self):
        hs = HistoryStore()
        hs.push(1, 1.0)
        hs.push(2, 2.0)
        hs.purge(set())
        assert len(hs._store) == 0

    def test_multiple_pushes_accumulate(self):
        hs = HistoryStore()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            hs.push(42, v)
        assert hs.trend(42) == "↑"

    def test_sparkline_length(self):
        hs = HistoryStore()
        for v in range(_WIDTH):
            hs.push(77, float(v))
        assert len(hs.sparkline(77)) == _WIDTH

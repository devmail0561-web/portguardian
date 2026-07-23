"""Tests for core.bandwidth — BandwidthMonitor rate calculation."""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bandwidth import BandwidthMonitor, InterfaceStat


def _make_counters(interfaces: dict) -> dict:
    """Build a mock psutil net_io_counters result.

    interfaces: {name: (bytes_sent, bytes_recv, packets_sent, packets_recv)}
    """
    result = {}
    for name, (bs, br, ps, pr) in interfaces.items():
        m = MagicMock()
        m.bytes_sent = bs
        m.bytes_recv = br
        m.packets_sent = ps
        m.packets_recv = pr
        result[name] = m
    return result


class TestBandwidthMonitorUpdate:
    """Tests for BandwidthMonitor.update()."""

    def test_first_call_zero_rates(self):
        monitor = BandwidthMonitor()
        counters = _make_counters({"eth0": (1000, 2000, 10, 20)})
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters):
            stats = monitor.update()
        assert len(stats) == 1
        assert stats[0].name == "eth0"
        assert stats[0].sent_rate == 0.0
        assert stats[0].recv_rate == 0.0

    def test_second_call_calculates_rate(self):
        monitor = BandwidthMonitor()
        t0 = time.time()

        counters1 = _make_counters({"eth0": (0, 0, 0, 0)})
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters1):
            with patch("core.bandwidth.time.time", return_value=t0):
                monitor.update()

        # 1 second later, 1000 bytes sent, 2000 bytes received
        counters2 = _make_counters({"eth0": (1000, 2000, 10, 20)})
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters2):
            with patch("core.bandwidth.time.time", return_value=t0 + 1.0):
                stats = monitor.update()

        assert len(stats) == 1
        assert abs(stats[0].sent_rate - 1000.0) < 1.0
        assert abs(stats[0].recv_rate - 2000.0) < 1.0

    def test_loopback_excluded(self):
        monitor = BandwidthMonitor()
        counters = _make_counters({
            "lo": (5000, 5000, 50, 50),
            "eth0": (1000, 2000, 10, 20),
        })
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters):
            stats = monitor.update()
        names = [s.name for s in stats]
        assert "lo" not in names
        assert "eth0" in names

    def test_multiple_interfaces(self):
        monitor = BandwidthMonitor()
        counters = _make_counters({
            "eth0": (1000, 2000, 10, 20),
            "wlan0": (500, 1000, 5, 10),
        })
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters):
            stats = monitor.update()
        assert len(stats) == 2

    def test_sorted_by_total_rate_descending(self):
        monitor = BandwidthMonitor()
        t0 = time.time()

        counters1 = _make_counters({
            "slow": (0, 0, 0, 0),
            "fast": (0, 0, 0, 0),
        })
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters1):
            with patch("core.bandwidth.time.time", return_value=t0):
                monitor.update()

        counters2 = _make_counters({
            "slow": (100, 100, 1, 1),
            "fast": (5000, 5000, 50, 50),
        })
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters2):
            with patch("core.bandwidth.time.time", return_value=t0 + 1.0):
                stats = monitor.update()

        assert stats[0].name == "fast"

    def test_rates_non_negative(self):
        monitor = BandwidthMonitor()
        t0 = time.time()

        # Counter went backwards (e.g. counter reset) — rate must be >= 0
        counters1 = _make_counters({"eth0": (5000, 5000, 50, 50)})
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters1):
            with patch("core.bandwidth.time.time", return_value=t0):
                monitor.update()

        counters2 = _make_counters({"eth0": (100, 100, 1, 1)})
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters2):
            with patch("core.bandwidth.time.time", return_value=t0 + 1.0):
                stats = monitor.update()

        assert stats[0].sent_rate >= 0.0
        assert stats[0].recv_rate >= 0.0

    def test_psutil_exception_returns_empty(self):
        monitor = BandwidthMonitor()
        with patch("core.bandwidth.psutil.net_io_counters", side_effect=Exception("boom")):
            stats = monitor.update()
        assert stats == []

    def test_stat_fields_populated(self):
        monitor = BandwidthMonitor()
        counters = _make_counters({"eth0": (9999, 8888, 100, 200)})
        with patch("core.bandwidth.psutil.net_io_counters", return_value=counters):
            stats = monitor.update()
        s = stats[0]
        assert s.bytes_sent == 9999
        assert s.bytes_recv == 8888
        assert s.packets_sent == 100
        assert s.packets_recv == 200


class TestInterfaceStat:
    """Tests for InterfaceStat dataclass."""

    def test_fields(self):
        s = InterfaceStat(
            name="eth0",
            bytes_sent=1000,
            bytes_recv=2000,
            sent_rate=10.0,
            recv_rate=20.0,
            packets_sent=5,
            packets_recv=10,
        )
        assert s.name == "eth0"
        assert s.sent_rate == 10.0
        assert s.recv_rate == 20.0

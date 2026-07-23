"""Tests for core.search module - search/filter functionality."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ports import ConnectionInfo
from core.search import filter_connections


def _make_test_connections():
    """Create a diverse set of connections for search testing."""
    return [
        ConnectionInfo(
            protocol="tcp",
            local_addr="0.0.0.0",
            local_port=80,
            remote_addr="",
            remote_port=0,
            status="LISTEN",
            pid=1000,
            process_name="nginx",
            username="root",
            fd=3,
        ),
        ConnectionInfo(
            protocol="tcp",
            local_addr="0.0.0.0",
            local_port=443,
            remote_addr="",
            remote_port=0,
            status="LISTEN",
            pid=1000,
            process_name="nginx",
            username="root",
            fd=4,
        ),
        ConnectionInfo(
            protocol="tcp",
            local_addr="192.168.1.10",
            local_port=54321,
            remote_addr="8.8.8.8",
            remote_port=443,
            status="ESTABLISHED",
            pid=2000,
            process_name="chrome",
            username="user1",
            fd=7,
        ),
        ConnectionInfo(
            protocol="udp",
            local_addr="0.0.0.0",
            local_port=53,
            remote_addr="",
            remote_port=0,
            status="NONE",
            pid=500,
            process_name="dnsmasq",
            username="nobody",
            fd=4,
        ),
        ConnectionInfo(
            protocol="tcp6",
            local_addr="::1",
            local_port=8080,
            remote_addr="",
            remote_port=0,
            status="LISTEN",
            pid=3000,
            process_name="python3",
            username="developer",
            fd=5,
        ),
        ConnectionInfo(
            protocol="tcp",
            local_addr="10.0.0.1",
            local_port=22,
            remote_addr="10.0.0.50",
            remote_port=49000,
            status="ESTABLISHED",
            pid=800,
            process_name="sshd",
            username="root",
            fd=6,
        ),
    ]


class TestFilterByPort:
    """Test filtering connections by port number."""

    def test_filter_by_exact_port(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "80")
        # Should match port 80 and 8080 (contains "80")
        ports = {r.local_port for r in results}
        assert 80 in ports
        assert 8080 in ports

    def test_filter_by_specific_port(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "443")
        # Should match local_port 443 (search does not check remote_port)
        assert len(results) >= 1
        assert any(r.local_port == 443 for r in results)

    def test_filter_by_unique_port(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "54321")
        assert len(results) == 1
        assert results[0].process_name == "chrome"


class TestFilterByProcessName:
    """Test filtering connections by process name."""

    def test_filter_by_full_name(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "nginx")
        assert len(results) == 2
        assert all(r.process_name == "nginx" for r in results)

    def test_filter_by_partial_name(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "ngi")
        assert len(results) == 2
        assert all(r.process_name == "nginx" for r in results)

    def test_filter_case_insensitive(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "NGINX")
        assert len(results) == 2

    def test_filter_python_process(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "python")
        assert len(results) == 1
        assert results[0].process_name == "python3"


class TestFilterByUsername:
    """Test filtering connections by username."""

    def test_filter_by_root(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "root")
        assert len(results) == 3  # nginx (2) + sshd (1)
        assert all(r.username == "root" for r in results)

    def test_filter_by_nobody(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "nobody")
        assert len(results) == 1
        assert results[0].process_name == "dnsmasq"

    def test_filter_by_partial_username(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "develop")
        assert len(results) == 1
        assert results[0].username == "developer"


class TestFilterByProtocol:
    """Test filtering connections by protocol."""

    def test_filter_udp(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "udp")
        assert len(results) == 1
        assert results[0].protocol == "udp"

    def test_filter_tcp6(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "tcp6")
        assert len(results) == 1
        assert results[0].protocol == "tcp6"

    def test_filter_tcp_matches_tcp_and_tcp6(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "tcp")
        # "tcp" is contained in both "tcp" and "tcp6"
        protocols = {r.protocol for r in results}
        assert "tcp" in protocols
        assert "tcp6" in protocols


class TestFilterByStatus:
    """Test filtering connections by connection status."""

    def test_filter_listen(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "listen")
        assert all(r.status == "LISTEN" for r in results)
        assert len(results) == 3

    def test_filter_established(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "established")
        assert all(r.status == "ESTABLISHED" for r in results)
        assert len(results) == 2

    def test_filter_none_status(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "none")
        assert len(results) >= 1


class TestFilterByAddress:
    """Test filtering connections by IP address."""

    def test_filter_by_local_addr(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "192.168")
        assert len(results) == 1
        assert results[0].local_addr == "192.168.1.10"

    def test_filter_by_remote_addr(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "8.8.8.8")
        assert len(results) == 1
        assert results[0].remote_addr == "8.8.8.8"

    def test_filter_ipv6_address(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "::1")
        assert len(results) == 1
        assert results[0].local_addr == "::1"

    def test_filter_subnet(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "10.0.0")
        assert len(results) == 1
        assert results[0].process_name == "sshd"


class TestFilterByPid:
    """Test filtering connections by PID."""

    def test_filter_by_pid(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "1000")
        assert len(results) == 2
        assert all(r.pid == 1000 for r in results)

    def test_filter_by_unique_pid(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "3000")
        assert len(results) == 1
        assert results[0].pid == 3000


class TestFilterEdgeCases:
    """Test edge cases for filter_connections."""

    def test_empty_query_returns_all(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "")
        assert len(results) == len(conns)

    def test_whitespace_query_returns_all(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "   ")
        assert len(results) == len(conns)

    def test_no_match_returns_empty(self):
        conns = _make_test_connections()
        results = filter_connections(conns, "zzz_nonexistent_xyz")
        assert results == []

    def test_empty_connections_list(self):
        results = filter_connections([], "nginx")
        assert results == []

    def test_none_pid_connection(self):
        conns = [
            ConnectionInfo(
                protocol="tcp",
                local_addr="0.0.0.0",
                local_port=9999,
                remote_addr="",
                remote_port=0,
                status="LISTEN",
                pid=None,
                process_name="",
                username="",
                fd=0,
            ),
        ]
        # Should not crash when PID is None
        results = filter_connections(conns, "9999")
        assert len(results) == 1

    def test_filter_does_not_modify_original(self):
        conns = _make_test_connections()
        original_len = len(conns)
        filter_connections(conns, "nginx")
        assert len(conns) == original_len

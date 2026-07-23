"""Tests for core.ports module - port detection via mocked psutil."""

import sys
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock
from collections import namedtuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ports import (
    ConnectionInfo,
    get_all_connections,
    get_listening_ports,
    get_connections_by_pid,
    _resolve_protocol,
    _get_process_info,
)


# Named tuples mimicking psutil's connection objects
Addr = namedtuple("Addr", ["ip", "port"])


def _make_sconn(
    family=socket.AF_INET,
    type_=socket.SOCK_STREAM,
    laddr=None,
    raddr=None,
    status="LISTEN",
    pid=1234,
    fd=5,
):
    """Create a mock psutil connection object."""
    conn = MagicMock()
    conn.family = family
    conn.type = type_
    conn.laddr = laddr or Addr(ip="127.0.0.1", port=8080)
    conn.raddr = raddr or ()
    conn.status = status
    conn.pid = pid
    conn.fd = fd
    return conn


class TestResolveProtocol:
    """Tests for _resolve_protocol helper."""

    def test_tcp_ipv4(self):
        assert _resolve_protocol(socket.AF_INET, socket.SOCK_STREAM) == "tcp"

    def test_udp_ipv4(self):
        assert _resolve_protocol(socket.AF_INET, socket.SOCK_DGRAM) == "udp"

    def test_tcp_ipv6(self):
        assert _resolve_protocol(socket.AF_INET6, socket.SOCK_STREAM) == "tcp6"

    def test_udp_ipv6(self):
        assert _resolve_protocol(socket.AF_INET6, socket.SOCK_DGRAM) == "udp6"

    def test_unix(self):
        assert _resolve_protocol(socket.AF_UNIX, socket.SOCK_STREAM) == "unix"


class TestGetProcessInfo:
    """Tests for _get_process_info helper."""

    @patch("core.ports.psutil.Process")
    def test_valid_pid(self, mock_process_cls):
        proc = MagicMock()
        proc.name.return_value = "python3"
        proc.username.return_value = "testuser"
        mock_process_cls.return_value = proc

        name, user = _get_process_info(1000)
        assert name == "python3"
        assert user == "testuser"

    def test_none_pid(self):
        name, user = _get_process_info(None)
        assert name == ""
        assert user == ""

    @patch("core.ports.psutil.Process")
    def test_no_such_process(self, mock_process_cls):
        import psutil

        mock_process_cls.side_effect = psutil.NoSuchProcess(9999)
        name, user = _get_process_info(9999)
        assert name == ""
        assert user == ""

    @patch("core.ports.psutil.Process")
    def test_access_denied(self, mock_process_cls):
        import psutil

        mock_process_cls.side_effect = psutil.AccessDenied(1)
        name, user = _get_process_info(1)
        assert name == ""
        assert user == ""


class TestGetAllConnections:
    """Tests for get_all_connections."""

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_basic_tcp_connection(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("nginx", "root")
        conn = _make_sconn(
            laddr=Addr(ip="0.0.0.0", port=80),
            raddr=(),
            status="LISTEN",
            pid=100,
        )
        mock_net_conns.return_value = [conn]

        results = get_all_connections(kinds=["inet4"])
        assert len(results) == 1
        assert results[0].protocol == "tcp"
        assert results[0].local_addr == "0.0.0.0"
        assert results[0].local_port == 80
        assert results[0].status == "LISTEN"
        assert results[0].pid == 100
        assert results[0].process_name == "nginx"
        assert results[0].username == "root"

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_established_connection_with_remote(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("chrome", "user1")
        conn = _make_sconn(
            laddr=Addr(ip="192.168.1.10", port=54321),
            raddr=Addr(ip="8.8.8.8", port=443),
            status="ESTABLISHED",
            pid=2000,
        )
        mock_net_conns.return_value = [conn]

        results = get_all_connections(kinds=["inet4"])
        assert len(results) == 1
        assert results[0].remote_addr == "8.8.8.8"
        assert results[0].remote_port == 443
        assert results[0].status == "ESTABLISHED"

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_deduplication(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("sshd", "root")
        conn = _make_sconn(
            laddr=Addr(ip="0.0.0.0", port=22),
            status="LISTEN",
            pid=500,
        )
        # Same connection returned twice
        mock_net_conns.return_value = [conn, conn]

        results = get_all_connections(kinds=["inet4"])
        assert len(results) == 1

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_state_filter(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("proc", "user")
        listen_conn = _make_sconn(
            laddr=Addr(ip="0.0.0.0", port=80),
            status="LISTEN",
            pid=100,
        )
        established_conn = _make_sconn(
            laddr=Addr(ip="0.0.0.0", port=80),
            raddr=Addr(ip="10.0.0.1", port=5000),
            status="ESTABLISHED",
            pid=101,
        )
        mock_net_conns.return_value = [listen_conn, established_conn]

        results = get_all_connections(kinds=["inet4"], states=["LISTEN"])
        assert len(results) == 1
        assert results[0].status == "LISTEN"

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_udp_connection(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("dns", "root")
        conn = _make_sconn(
            family=socket.AF_INET,
            type_=socket.SOCK_DGRAM,
            laddr=Addr(ip="0.0.0.0", port=53),
            raddr=(),
            status="NONE",
            pid=300,
        )
        mock_net_conns.return_value = [conn]

        results = get_all_connections(kinds=["udp4"])
        assert len(results) == 1
        assert results[0].protocol == "udp"

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_ipv6_connection(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("httpd", "www")
        conn = _make_sconn(
            family=socket.AF_INET6,
            type_=socket.SOCK_STREAM,
            laddr=Addr(ip="::1", port=8443),
            raddr=(),
            status="LISTEN",
            pid=400,
        )
        mock_net_conns.return_value = [conn]

        results = get_all_connections(kinds=["inet6"])
        assert len(results) == 1
        assert results[0].protocol == "tcp6"
        assert results[0].local_addr == "::1"

    @patch("core.ports.psutil.net_connections")
    def test_access_denied_handling(self, mock_net_conns):
        import psutil

        mock_net_conns.side_effect = psutil.AccessDenied(0)
        results = get_all_connections(kinds=["inet4"])
        assert results == []

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_fd_minus_one_becomes_zero(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("proc", "user")
        conn = _make_sconn(fd=-1)
        mock_net_conns.return_value = [conn]

        results = get_all_connections(kinds=["inet4"])
        assert results[0].fd == 0

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_sorting_by_port(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("proc", "user")
        conn_high = _make_sconn(laddr=Addr(ip="0.0.0.0", port=9000), pid=1)
        conn_low = _make_sconn(laddr=Addr(ip="0.0.0.0", port=22), pid=2)
        mock_net_conns.return_value = [conn_high, conn_low]

        results = get_all_connections(kinds=["inet4"])
        assert results[0].local_port == 22
        assert results[1].local_port == 9000

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_none_pid_connection(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("", "")
        conn = _make_sconn(pid=None)
        mock_net_conns.return_value = [conn]

        results = get_all_connections(kinds=["inet4"])
        assert len(results) == 1
        assert results[0].pid is None


class TestGetListeningPorts:
    """Tests for get_listening_ports convenience function."""

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_only_listen_returned(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("svc", "root")
        listen = _make_sconn(laddr=Addr(ip="0.0.0.0", port=443), status="LISTEN", pid=10)
        estab = _make_sconn(
            laddr=Addr(ip="0.0.0.0", port=443),
            raddr=Addr(ip="1.2.3.4", port=50000),
            status="ESTABLISHED",
            pid=11,
        )
        mock_net_conns.return_value = [listen, estab]

        results = get_listening_ports()
        assert all(r.status == "LISTEN" for r in results)


class TestGetConnectionsByPid:
    """Tests for get_connections_by_pid."""

    @patch("core.ports._get_process_info")
    @patch("core.ports.psutil.net_connections")
    def test_filters_by_pid(self, mock_net_conns, mock_proc_info):
        mock_proc_info.return_value = ("proc", "user")
        conn1 = _make_sconn(laddr=Addr(ip="0.0.0.0", port=80), pid=100)
        conn2 = _make_sconn(laddr=Addr(ip="0.0.0.0", port=443), pid=200)
        mock_net_conns.return_value = [conn1, conn2]

        results = get_connections_by_pid(100)
        assert len(results) == 1
        assert results[0].pid == 100


class TestConnectionInfoProperties:
    """Tests for ConnectionInfo dataclass properties."""

    def test_local_endpoint_ipv4(self):
        conn = ConnectionInfo(
            protocol="tcp", local_addr="127.0.0.1", local_port=8080,
            remote_addr="", remote_port=0, status="LISTEN",
            pid=1, process_name="test", username="user", fd=0,
        )
        assert conn.local_endpoint == "127.0.0.1:8080"

    def test_local_endpoint_ipv6(self):
        conn = ConnectionInfo(
            protocol="tcp6", local_addr="::1", local_port=443,
            remote_addr="", remote_port=0, status="LISTEN",
            pid=1, process_name="test", username="user", fd=0,
        )
        assert conn.local_endpoint == "[::1]:443"

    def test_remote_endpoint_empty(self):
        conn = ConnectionInfo(
            protocol="tcp", local_addr="0.0.0.0", local_port=80,
            remote_addr="", remote_port=0, status="LISTEN",
            pid=1, process_name="test", username="user", fd=0,
        )
        assert conn.remote_endpoint == ""

    def test_remote_endpoint_ipv4(self):
        conn = ConnectionInfo(
            protocol="tcp", local_addr="0.0.0.0", local_port=80,
            remote_addr="10.0.0.1", remote_port=5000, status="ESTABLISHED",
            pid=1, process_name="test", username="user", fd=0,
        )
        assert conn.remote_endpoint == "10.0.0.1:5000"

    def test_remote_endpoint_ipv6(self):
        conn = ConnectionInfo(
            protocol="tcp6", local_addr="::1", local_port=80,
            remote_addr="fe80::1", remote_port=9090, status="ESTABLISHED",
            pid=1, process_name="test", username="user", fd=0,
        )
        assert conn.remote_endpoint == "[fe80::1]:9090"

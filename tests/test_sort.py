"""Tests for core.search.sort_connections - sorting by various columns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ports import ConnectionInfo
from core.search import sort_connections


def _make_sortable_connections():
    """Create connections with varied values for sorting tests."""
    return [
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
            fd=3,
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
            status="ESTABLISHED",
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
            username="admin",
            fd=6,
        ),
    ]


class TestSortByPort:
    """Test sorting connections by port number."""

    def test_sort_ascending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Port", reverse=False)
        ports = [c.local_port for c in result]
        assert ports == sorted(ports)

    def test_sort_descending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Port", reverse=True)
        ports = [c.local_port for c in result]
        assert ports == sorted(ports, reverse=True)

    def test_sort_preserves_all_entries(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Port")
        assert len(result) == len(conns)

    def test_sort_first_entry(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Port", reverse=False)
        assert result[0].local_port == 22

    def test_sort_last_entry(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Port", reverse=False)
        assert result[-1].local_port == 8080


class TestSortByPid:
    """Test sorting connections by PID."""

    def test_sort_ascending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "PID", reverse=False)
        pids = [c.pid for c in result]
        assert pids == sorted(pids)

    def test_sort_descending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "PID", reverse=True)
        pids = [c.pid for c in result]
        assert pids == sorted(pids, reverse=True)

    def test_none_pid_treated_as_zero(self):
        conns = [
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=80,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=None, process_name="unknown", username="", fd=0,
            ),
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=443,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=100, process_name="nginx", username="root", fd=0,
            ),
        ]
        result = sort_connections(conns, "PID", reverse=False)
        # None pid should sort as 0, so first
        assert result[0].pid is None
        assert result[1].pid == 100


class TestSortByCpu:
    """Test sorting connections by CPU percentage."""

    def test_sort_by_cpu_ascending(self):
        conns = _make_sortable_connections()
        cpu_map = {1000: 5.0, 500: 0.5, 3000: 25.0, 800: 2.0}
        result = sort_connections(conns, "CPU%", reverse=False, cpu_map=cpu_map)
        cpus = [cpu_map.get(c.pid, 0.0) for c in result]
        assert cpus == sorted(cpus)

    def test_sort_by_cpu_descending(self):
        conns = _make_sortable_connections()
        cpu_map = {1000: 5.0, 500: 0.5, 3000: 25.0, 800: 2.0}
        result = sort_connections(conns, "CPU%", reverse=True, cpu_map=cpu_map)
        cpus = [cpu_map.get(c.pid, 0.0) for c in result]
        assert cpus == sorted(cpus, reverse=True)

    def test_sort_by_cpu_highest_first(self):
        conns = _make_sortable_connections()
        cpu_map = {1000: 5.0, 500: 0.5, 3000: 25.0, 800: 2.0}
        result = sort_connections(conns, "CPU%", reverse=True, cpu_map=cpu_map)
        assert result[0].pid == 3000  # 25.0% is highest

    def test_sort_by_cpu_missing_pid_defaults_zero(self):
        conns = _make_sortable_connections()
        cpu_map = {1000: 5.0}  # Only one PID in the map
        result = sort_connections(conns, "CPU%", reverse=False, cpu_map=cpu_map)
        # PID 1000 with 5.0 should be last in ascending order
        assert result[-1].pid == 1000

    def test_sort_by_cpu_empty_map(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "CPU%", cpu_map={})
        # All CPU values are 0.0, so order is stable (Python sort is stable)
        assert len(result) == len(conns)


class TestSortByRam:
    """Test sorting connections by RAM percentage."""

    def test_sort_by_ram_ascending(self):
        conns = _make_sortable_connections()
        memory_map = {1000: 3.5, 500: 0.2, 3000: 12.0, 800: 1.0}
        result = sort_connections(conns, "RAM", reverse=False, memory_map=memory_map)
        mems = [memory_map.get(c.pid, 0.0) for c in result]
        assert mems == sorted(mems)

    def test_sort_by_ram_descending(self):
        conns = _make_sortable_connections()
        memory_map = {1000: 3.5, 500: 0.2, 3000: 12.0, 800: 1.0}
        result = sort_connections(conns, "RAM", reverse=True, memory_map=memory_map)
        mems = [memory_map.get(c.pid, 0.0) for c in result]
        assert mems == sorted(mems, reverse=True)

    def test_sort_by_ram_highest_first(self):
        conns = _make_sortable_connections()
        memory_map = {1000: 3.5, 500: 0.2, 3000: 12.0, 800: 1.0}
        result = sort_connections(conns, "RAM", reverse=True, memory_map=memory_map)
        assert result[0].pid == 3000  # 12.0% is highest

    def test_sort_by_ram_none_map_defaults_empty(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "RAM", memory_map=None)
        # Should not crash; all values default to 0.0
        assert len(result) == len(conns)


class TestSortByProcessName:
    """Test sorting connections by process name."""

    def test_sort_ascending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Processus", reverse=False)
        names = [c.process_name.lower() for c in result]
        assert names == sorted(names)

    def test_sort_descending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Processus", reverse=True)
        names = [c.process_name.lower() for c in result]
        assert names == sorted(names, reverse=True)

    def test_first_process_alphabetically(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Processus", reverse=False)
        assert result[0].process_name == "dnsmasq"

    def test_case_insensitive_sort(self):
        conns = [
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=80,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=1, process_name="Zebra", username="root", fd=0,
            ),
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=81,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=2, process_name="apple", username="root", fd=0,
            ),
        ]
        result = sort_connections(conns, "Processus", reverse=False)
        # "apple" < "zebra" case-insensitively
        assert result[0].process_name == "apple"
        assert result[1].process_name == "Zebra"


class TestSortByUsername:
    """Test sorting connections by username."""

    def test_sort_ascending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Utilisateur", reverse=False)
        users = [c.username.lower() for c in result]
        assert users == sorted(users)

    def test_sort_descending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Utilisateur", reverse=True)
        users = [c.username.lower() for c in result]
        assert users == sorted(users, reverse=True)

    def test_first_user_alphabetically(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Utilisateur", reverse=False)
        assert result[0].username == "admin"


class TestSortByStatus:
    """Test sorting connections by connection status."""

    def test_sort_ascending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "État", reverse=False)
        statuses = [c.status for c in result]
        assert statuses == sorted(statuses)

    def test_sort_descending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "État", reverse=True)
        statuses = [c.status for c in result]
        assert statuses == sorted(statuses, reverse=True)


class TestSortByProtocol:
    """Test sorting connections by protocol."""

    def test_sort_ascending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Proto", reverse=False)
        protos = [c.protocol for c in result]
        assert protos == sorted(protos)

    def test_sort_descending(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Proto", reverse=True)
        protos = [c.protocol for c in result]
        assert protos == sorted(protos, reverse=True)

    def test_first_protocol_alphabetically(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Proto", reverse=False)
        assert result[0].protocol == "tcp"


class TestSortUnknownKey:
    """Test sort with unknown/invalid key falls back to Port."""

    def test_unknown_key_uses_port_default(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "NonExistentColumn", reverse=False)
        ports = [c.local_port for c in result]
        assert ports == sorted(ports)


class TestSortEdgeCases:
    """Test edge cases for sort_connections."""

    def test_empty_list(self):
        result = sort_connections([], "Port")
        assert result == []

    def test_single_element(self):
        conns = [
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=80,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=1, process_name="nginx", username="root", fd=0,
            ),
        ]
        result = sort_connections(conns, "Port")
        assert len(result) == 1
        assert result[0].local_port == 80

    def test_sort_does_not_modify_original(self):
        conns = _make_sortable_connections()
        original_order = [c.local_port for c in conns]
        sort_connections(conns, "Port", reverse=True)
        current_order = [c.local_port for c in conns]
        assert current_order == original_order

    def test_sort_returns_new_list(self):
        conns = _make_sortable_connections()
        result = sort_connections(conns, "Port")
        assert result is not conns

    def test_sort_stability(self):
        """When sort keys are equal, original order should be preserved."""
        conns = [
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=80,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=1, process_name="first", username="root", fd=0,
            ),
            ConnectionInfo(
                protocol="tcp", local_addr="0.0.0.0", local_port=80,
                remote_addr="", remote_port=0, status="LISTEN",
                pid=2, process_name="second", username="root", fd=0,
            ),
        ]
        result = sort_connections(conns, "Port", reverse=False)
        assert result[0].process_name == "first"
        assert result[1].process_name == "second"

"""Tests for core.process module - process detail collection."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil
from core.process import (
    get_process_detail,
    get_process_cpu_memory,
    ProcessDetail,
    _safe_call,
)


class TestGetProcessDetailOwnPid:
    """Test get_process_detail against the current test process."""

    def test_returns_process_detail_for_own_pid(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert isinstance(detail, ProcessDetail)
        assert detail.pid == pid

    def test_own_pid_has_valid_name(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.name != ""

    def test_own_pid_has_username(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.username != ""

    def test_own_pid_has_ppid(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.ppid == os.getppid()

    def test_own_pid_has_cmdline(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        # Our process should have some command line
        assert detail.cmdline != ""

    def test_own_pid_has_positive_num_threads(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.num_threads >= 1

    def test_own_pid_has_positive_memory(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.memory_rss > 0
        assert detail.memory_vms > 0

    def test_own_pid_has_valid_create_time(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.create_time > 0
        assert detail.create_time < time.time()

    def test_own_pid_uptime_positive(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.uptime >= 0

    def test_own_pid_status_is_running(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        assert detail.status in ("running", "sleeping", "disk-sleep", "idle")

    def test_own_pid_cwd_matches(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        # cwd should be a valid path
        if detail.cwd:
            assert Path(detail.cwd).exists()


class TestGetProcessDetailInvalidPid:
    """Test get_process_detail with invalid PIDs."""

    def test_nonexistent_pid_returns_none(self):
        # Use a very high PID unlikely to exist
        result = get_process_detail(4_000_000)
        assert result is None

    def test_negative_pid_raises_value_error(self):
        # psutil raises ValueError for negative PIDs
        import pytest
        with pytest.raises(ValueError):
            get_process_detail(-1)


class TestGetProcessDetailMocked:
    """Test get_process_detail with mocked psutil."""

    @patch("core.process.psutil.Process")
    def test_no_such_process(self, mock_process_cls):
        mock_process_cls.side_effect = psutil.NoSuchProcess(99999)
        result = get_process_detail(99999)
        assert result is None

    @patch("core.process.psutil.Process")
    def test_zombie_process(self, mock_process_cls):
        mock_process_cls.side_effect = psutil.ZombieProcess(99999)
        result = get_process_detail(99999)
        assert result is None

    @patch("core.process.psutil.Process")
    def test_access_denied_during_oneshot(self, mock_process_cls):
        proc = MagicMock()
        mock_process_cls.return_value = proc
        proc.oneshot.side_effect = psutil.AccessDenied(1)
        result = get_process_detail(1)
        assert result is None


class TestGetProcessCpuMemory:
    """Tests for get_process_cpu_memory."""

    def test_own_pid_returns_tuple(self):
        pid = os.getpid()
        cpu, mem = get_process_cpu_memory(pid)
        assert isinstance(cpu, float)
        assert isinstance(mem, float)
        # Memory percent should be positive for a running process
        assert mem >= 0.0

    def test_nonexistent_pid_returns_zeros(self):
        cpu, mem = get_process_cpu_memory(4_000_000)
        assert cpu == 0.0
        assert mem == 0.0

    @patch("core.process.psutil.Process")
    def test_access_denied_returns_zeros(self, mock_process_cls):
        mock_process_cls.side_effect = psutil.AccessDenied(1)
        cpu, mem = get_process_cpu_memory(1)
        assert cpu == 0.0
        assert mem == 0.0

    @patch("core.process.psutil.Process")
    def test_normal_values(self, mock_process_cls):
        proc = MagicMock()
        proc.cpu_percent.return_value = 25.5
        proc.memory_percent.return_value = 3.2
        mock_process_cls.return_value = proc

        cpu, mem = get_process_cpu_memory(1234)
        assert cpu == 25.5
        assert mem == 3.2


class TestSafeCall:
    """Tests for _safe_call helper."""

    def test_successful_call(self):
        result = _safe_call(lambda: 42, 0)
        assert result == 42

    def test_access_denied_returns_default(self):
        def raise_access_denied():
            raise psutil.AccessDenied(1)

        result = _safe_call(raise_access_denied, "default")
        assert result == "default"

    def test_os_error_returns_default(self):
        def raise_os_error():
            raise OSError("test")

        result = _safe_call(raise_os_error, -1)
        assert result == -1


class TestProcessDetailProperties:
    """Tests for ProcessDetail property methods."""

    def test_memory_rss_human(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        human = detail.memory_rss_human
        assert any(unit in human for unit in ("B", "KB", "MB", "GB"))

    def test_memory_vms_human(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        human = detail.memory_vms_human
        assert any(unit in human for unit in ("B", "KB", "MB", "GB"))

    def test_uptime_human(self):
        pid = os.getpid()
        detail = get_process_detail(pid)
        assert detail is not None
        human = detail.uptime_human
        # Should contain time units
        assert any(unit in human for unit in ("s", "m", "h", "j"))

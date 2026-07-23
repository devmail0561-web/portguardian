"""Tests for main.py CLI mode (--once, --list-listen, --format, --output)."""

import csv
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


SAMPLE_CONNS = [
    _conn(80, process="nginx"),
    _conn(443, process="nginx"),
    _conn(22, process="sshd"),
    _conn(8080, status="ESTABLISHED", process="python3"),
]

LISTEN_CONNS = [c for c in SAMPLE_CONNS if c.status == "LISTEN"]


class TestCliOnce:
    """Tests for --once mode (text output on stdout)."""

    def _run_cli(self, argv, conns=None):
        import io
        from main import _run_cli
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--list-listen", action="store_true")
        parser.add_argument("--format", choices=["json", "csv", "txt"], default=None)
        parser.add_argument("--output", default=None)
        args = parser.parse_args(argv)

        if conns is None:
            conns = SAMPLE_CONNS

        captured = io.StringIO()
        with patch("core.ports.get_all_connections", return_value=conns):
            with patch("core.ports.get_listening_ports", return_value=LISTEN_CONNS):
                with patch("sys.stdout", captured):
                    _run_cli(args)
        return captured.getvalue()

    def test_once_outputs_connections(self):
        out = self._run_cli(["--once"])
        assert "nginx" in out
        assert "sshd" in out

    def test_once_outputs_all_ports(self):
        out = self._run_cli(["--once"])
        assert "80" in out
        assert "443" in out
        assert "22" in out

    def test_list_listen_only_listen_connections(self):
        out = self._run_cli(["--list-listen"])
        # ESTABLISHED should not appear
        assert "ESTABLISHED" not in out
        assert "80" in out

    def test_once_json_format_stdout(self):
        out = self._run_cli(["--once", "--format", "json"])
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == len(SAMPLE_CONNS)

    def test_once_json_has_required_fields(self):
        out = self._run_cli(["--once", "--format", "json"])
        data = json.loads(out)
        entry = data[0]
        for field in ("protocol", "local_addr", "local_port", "status", "pid", "process_name"):
            assert field in entry

    def test_once_csv_format_stdout(self):
        out = self._run_cli(["--once", "--format", "csv"])
        reader = csv.DictReader(out.splitlines())
        rows = list(reader)
        assert len(rows) == len(SAMPLE_CONNS)

    def test_once_csv_has_header(self):
        out = self._run_cli(["--once", "--format", "csv"])
        first_line = out.splitlines()[0]
        assert "protocol" in first_line
        assert "local_port" in first_line

    def test_once_txt_format_stdout(self):
        out = self._run_cli(["--once", "--format", "txt"])
        assert "nginx" in out
        assert "tcp" in out


class TestCliOutput:
    """Tests for --output FILE writing."""

    def _run_with_output(self, argv, tmp_path, conns=None):
        from main import _run_cli
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--list-listen", action="store_true")
        parser.add_argument("--format", choices=["json", "csv", "txt"], default=None)
        parser.add_argument("--output", default=None)
        args = parser.parse_args(argv)

        if conns is None:
            conns = SAMPLE_CONNS

        with patch("core.ports.get_all_connections", return_value=conns):
            with patch("core.ports.get_listening_ports", return_value=LISTEN_CONNS):
                _run_cli(args)

    def test_output_json_file_created(self, tmp_path):
        outfile = str(tmp_path / "out.json")
        self._run_with_output(["--once", "--format", "json", "--output", outfile], tmp_path)
        assert Path(outfile).exists()

    def test_output_json_valid(self, tmp_path):
        outfile = tmp_path / "out.json"
        self._run_with_output(["--once", "--format", "json", "--output", str(outfile)], tmp_path)
        data = json.loads(outfile.read_text())
        assert isinstance(data, list)
        assert len(data) == len(SAMPLE_CONNS)

    def test_output_csv_file_created(self, tmp_path):
        outfile = str(tmp_path / "out.csv")
        self._run_with_output(["--once", "--format", "csv", "--output", outfile], tmp_path)
        assert Path(outfile).exists()

    def test_output_csv_has_correct_rows(self, tmp_path):
        outfile = tmp_path / "out.csv"
        self._run_with_output(["--once", "--format", "csv", "--output", str(outfile)], tmp_path)
        reader = csv.DictReader(outfile.read_text().splitlines())
        rows = list(reader)
        assert len(rows) == len(SAMPLE_CONNS)

    def test_output_txt_file_created(self, tmp_path):
        outfile = str(tmp_path / "out.txt")
        self._run_with_output(["--once", "--format", "txt", "--output", outfile], tmp_path)
        assert Path(outfile).exists()

    def test_output_txt_contains_process_names(self, tmp_path):
        outfile = tmp_path / "out.txt"
        self._run_with_output(["--once", "--format", "txt", "--output", str(outfile)], tmp_path)
        content = outfile.read_text()
        assert "nginx" in content
        assert "sshd" in content

    def test_output_creates_parent_dirs(self, tmp_path):
        outfile = str(tmp_path / "subdir" / "deep" / "out.json")
        self._run_with_output(["--once", "--format", "json", "--output", outfile], tmp_path)
        assert Path(outfile).exists()

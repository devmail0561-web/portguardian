"""Tests for core.exporter module - CSV/JSON/TXT export."""

import csv
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ports import ConnectionInfo
from core.exporter import (
    export_connections,
    export_csv,
    export_json,
    export_txt,
    _connection_to_dict,
    _generate_filename,
)


def _make_connections():
    """Create a list of sample ConnectionInfo objects for testing."""
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
    ]


class TestConnectionToDict:
    """Tests for _connection_to_dict helper."""

    def test_all_fields_present(self):
        conn = _make_connections()[0]
        d = _connection_to_dict(conn)
        assert d["protocol"] == "tcp"
        assert d["local_addr"] == "0.0.0.0"
        assert d["local_port"] == 80
        assert d["remote_addr"] == ""
        assert d["remote_port"] == 0
        assert d["status"] == "LISTEN"
        assert d["pid"] == 1000
        assert d["process_name"] == "nginx"
        assert d["username"] == "root"

    def test_fd_not_in_dict(self):
        """fd field should not be exported."""
        conn = _make_connections()[0]
        d = _connection_to_dict(conn)
        assert "fd" not in d

    def test_extra_fields_present(self):
        """cpu_percent, memory_percent, service, uptime should be exported."""
        conn = _make_connections()[0]
        cpu_map = {1000: 12.5}
        memory_map = {1000: 3.2}
        service_map = {1000: "nginx.service"}
        uptime_map = {1000: "2h"}
        d = _connection_to_dict(conn, cpu_map, memory_map, service_map, uptime_map)
        assert d["cpu_percent"] == 12.5
        assert d["memory_percent"] == 3.2
        assert d["service"] == "nginx.service"
        assert d["uptime"] == "2h"

    def test_extra_fields_default_when_missing(self):
        """Extra fields default to 0/empty when maps are None or PID absent."""
        conn = _make_connections()[0]
        d = _connection_to_dict(conn)
        assert d["cpu_percent"] == 0.0
        assert d["memory_percent"] == 0.0
        assert d["service"] == ""
        assert d["uptime"] == ""


class TestGenerateFilename:
    """Tests for _generate_filename."""

    def test_csv_extension(self, tmp_path):
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            path = _generate_filename("csv")
            assert path.suffix == ".csv"
            assert "portguardian_" in path.name

    def test_json_extension(self, tmp_path):
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            path = _generate_filename("json")
            assert path.suffix == ".json"

    def test_txt_extension(self, tmp_path):
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            path = _generate_filename("txt")
            assert path.suffix == ".txt"

    def test_creates_directory(self, tmp_path):
        export_dir = tmp_path / "new_subdir"
        with patch("core.exporter.EXPORT_DIR", export_dir):
            _generate_filename("csv")
            assert export_dir.exists()


class TestExportCsv:
    """Tests for export_csv."""

    def test_exports_csv_file(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_csv(connections)
            assert result is not None
            assert result.exists()
            assert result.suffix == ".csv"

    def test_csv_content_has_header(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_csv(connections)
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames
                assert "protocol" in fields
                assert "local_addr" in fields
                assert "local_port" in fields
                assert "pid" in fields
                assert "process_name" in fields
                assert "cpu_percent" in fields
                assert "memory_percent" in fields
                assert "service" in fields
                assert "uptime" in fields

    def test_csv_row_count(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_csv(connections)
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 3

    def test_csv_data_values(self, tmp_path):
        connections = _make_connections()[:1]
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_csv(connections)
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                row = next(reader)
                assert row["protocol"] == "tcp"
                assert row["local_port"] == "80"
                assert row["process_name"] == "nginx"

    def test_csv_empty_list(self, tmp_path):
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_csv([])
            assert result is not None
            assert result.exists()
            with open(result, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 0


class TestExportJson:
    """Tests for export_json."""

    def test_exports_json_file(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_json(connections)
            assert result is not None
            assert result.exists()
            assert result.suffix == ".json"

    def test_json_is_valid(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_json(connections)
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert isinstance(data, list)

    def test_json_entry_count(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_json(connections)
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert len(data) == 3

    def test_json_data_values(self, tmp_path):
        connections = _make_connections()[:1]
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_json(connections)
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                data = json.load(f)
                entry = data[0]
                assert entry["protocol"] == "tcp"
                assert entry["local_addr"] == "0.0.0.0"
                assert entry["local_port"] == 80
                assert entry["pid"] == 1000
                assert entry["process_name"] == "nginx"
                assert "cpu_percent" in entry
                assert "memory_percent" in entry
                assert "service" in entry
                assert "uptime" in entry

    def test_json_empty_list(self, tmp_path):
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_json([])
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data == []


class TestExportTxt:
    """Tests for export_txt."""

    def test_exports_txt_file(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_txt(connections)
            assert result is not None
            assert result.exists()
            assert result.suffix == ".txt"

    def test_txt_has_header_line(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_txt(connections)
            assert result is not None
            content = result.read_text(encoding="utf-8")
            assert "Proto" in content
            assert "Port" in content

    def test_txt_has_separator(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_txt(connections)
            assert result is not None
            content = result.read_text(encoding="utf-8")
            lines = content.splitlines()
            # Second line should be the separator
            assert "---" in lines[1]

    def test_txt_line_count(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_txt(connections)
            assert result is not None
            content = result.read_text(encoding="utf-8")
            lines = content.splitlines()
            # header + separator + 3 data lines
            assert len(lines) == 5

    def test_txt_contains_process_data(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_txt(connections)
            assert result is not None
            content = result.read_text(encoding="utf-8")
            assert "nginx" in content
            assert "chrome" in content
            assert "dnsmasq" in content

    def test_txt_empty_list(self, tmp_path):
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_txt([])
            assert result is not None
            content = result.read_text(encoding="utf-8")
            lines = content.splitlines()
            # Only header + separator
            assert len(lines) == 2


class TestExportConnections:
    """Tests for the export_connections dispatcher."""

    def test_csv_format(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_connections(connections, "csv")
            assert result is not None
            assert result.suffix == ".csv"

    def test_json_format(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_connections(connections, "json")
            assert result is not None
            assert result.suffix == ".json"

    def test_txt_format(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_connections(connections, "txt")
            assert result is not None
            assert result.suffix == ".txt"

    def test_unknown_format_returns_none(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_connections(connections, "xml")
            assert result is None

    def test_empty_format_returns_none(self, tmp_path):
        connections = _make_connections()
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_connections(connections, "")
            assert result is None


class TestExportUnicodeHandling:
    """Tests for proper Unicode handling in exports."""

    def test_csv_handles_unicode_process_name(self, tmp_path):
        conn = ConnectionInfo(
            protocol="tcp",
            local_addr="0.0.0.0",
            local_port=8080,
            remote_addr="",
            remote_port=0,
            status="LISTEN",
            pid=100,
            process_name="serveur-donnees",
            username="utilisateur",
            fd=0,
        )
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_csv([conn])
            assert result is not None
            content = result.read_text(encoding="utf-8")
            assert "serveur-donnees" in content

    def test_json_handles_unicode(self, tmp_path):
        conn = ConnectionInfo(
            protocol="tcp",
            local_addr="0.0.0.0",
            local_port=8080,
            remote_addr="",
            remote_port=0,
            status="LISTEN",
            pid=100,
            process_name="serveur-donnees",
            username="utilisateur",
            fd=0,
        )
        with patch("core.exporter.EXPORT_DIR", tmp_path):
            result = export_json([conn])
            assert result is not None
            with open(result, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data[0]["process_name"] == "serveur-donnees"
                assert data[0]["username"] == "utilisateur"

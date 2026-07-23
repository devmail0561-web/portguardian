"""Tests for core.firewall - port spec parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.firewall import parse_port_spec


class TestParsePortSpec:

    def test_single_port(self):
        assert parse_port_spec("80") == [(80, 80)]

    def test_multiple_ports(self):
        assert parse_port_spec("80,443") == [(80, 80), (443, 443)]

    def test_range(self):
        assert parse_port_spec("8000-8100") == [(8000, 8100)]

    def test_mixed(self):
        assert parse_port_spec("80,443,8000-8010") == [(80, 80), (443, 443), (8000, 8010)]

    def test_spaces_ignored(self):
        assert parse_port_spec("80, 443") == [(80, 80), (443, 443)]

    def test_reversed_range_normalized(self):
        assert parse_port_spec("8100-8000") == [(8000, 8100)]

    def test_port_1(self):
        assert parse_port_spec("1") == [(1, 1)]

    def test_port_65535(self):
        assert parse_port_spec("65535") == [(65535, 65535)]

    def test_port_zero_raises(self):
        with pytest.raises(ValueError):
            parse_port_spec("0")

    def test_port_above_max_raises(self):
        with pytest.raises(ValueError):
            parse_port_spec("65536")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_port_spec("")

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            parse_port_spec("http")

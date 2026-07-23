"""Tests for core.filters — FilterStore CRUD and persistence."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.filters import FilterStore, SavedFilter


class TestFilterStore:
    """Tests for FilterStore."""

    def _store(self, tmp_path):
        filters_file = tmp_path / "filters.json"
        with patch("core.filters.FILTERS_FILE", filters_file):
            yield FilterStore()

    def test_empty_on_no_file(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "missing.json"):
            fs = FilterStore()
            assert fs.filters == []

    def test_add_single_filter(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            fs.add("web", "nginx")
            assert len(fs.filters) == 1
            assert fs.filters[0].name == "web"
            assert fs.filters[0].query == "nginx"

    def test_add_persists_to_disk(self, tmp_path):
        f = tmp_path / "f.json"
        with patch("core.filters.FILTERS_FILE", f):
            fs = FilterStore()
            fs.add("web", "nginx")
        with patch("core.filters.FILTERS_FILE", f):
            fs2 = FilterStore()
            assert len(fs2.filters) == 1
            assert fs2.filters[0].name == "web"

    def test_add_replaces_same_name(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            fs.add("web", "nginx")
            fs.add("web", "apache")
            assert len(fs.filters) == 1
            assert fs.filters[0].query == "apache"

    def test_remove_existing(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            fs.add("web", "nginx")
            result = fs.remove("web")
            assert result is True
            assert fs.filters == []

    def test_remove_nonexistent_returns_false(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            assert fs.remove("ghost") is False

    def test_get_by_name(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            fs.add("ssh", "22")
            f = fs.get("ssh")
            assert f is not None
            assert f.query == "22"

    def test_get_unknown_returns_none(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            assert fs.get("unknown") is None

    def test_get_by_index(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            fs.add("a", "query-a")
            fs.add("b", "query-b")
            assert fs.get_by_index(0).name == "a"
            assert fs.get_by_index(1).name == "b"

    def test_get_by_index_out_of_bounds(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            assert fs.get_by_index(0) is None
            assert fs.get_by_index(-1) is None

    def test_multiple_filters_ordered(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            for name in ["c", "a", "b"]:
                fs.add(name, f"q-{name}")
            names = [f.name for f in fs.filters]
            assert names == ["c", "a", "b"]

    def test_filters_property_returns_copy(self, tmp_path):
        with patch("core.filters.FILTERS_FILE", tmp_path / "f.json"):
            fs = FilterStore()
            fs.add("x", "q")
            copy = fs.filters
            copy.clear()
            assert len(fs.filters) == 1


class TestSavedFilter:
    def test_to_dict(self):
        f = SavedFilter(name="web", query="nginx")
        d = f.to_dict()
        assert d == {"name": "web", "query": "nginx"}

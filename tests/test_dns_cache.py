"""Tests for core.dns_cache — hostname resolution and TTL caching."""

import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.dns_cache as dns_cache
from core.dns_cache import get_hostname, clear_cache, _do_resolve


class TestGetHostname:
    """Tests for get_hostname (synchronous cache lookup)."""

    def setup_method(self):
        clear_cache()

    def test_unknown_ip_returns_none(self):
        assert get_hostname("1.2.3.4") is None

    def test_empty_string_returns_none(self):
        assert get_hostname("") is None

    def test_star_returns_none(self):
        assert get_hostname("*") is None

    def test_cached_entry_returned(self):
        dns_cache._cache["10.0.0.1"] = ("myhost.local", time.time())
        assert get_hostname("10.0.0.1") == "myhost.local"

    def test_expired_entry_returns_none(self):
        dns_cache._cache["10.0.0.2"] = ("old.host", time.time() - dns_cache._TTL - 1)
        assert get_hostname("10.0.0.2") is None

    def test_empty_hostname_returns_none(self):
        dns_cache._cache["10.0.0.3"] = ("", time.time())
        assert get_hostname("10.0.0.3") is None


class TestDoResolve:
    """Tests for _do_resolve (synchronous DNS lookup wrapper)."""

    def test_returns_hostname_on_success(self):
        with patch("core.dns_cache.socket.gethostbyaddr", return_value=("myhost.local", [], ["127.0.0.1"])):
            assert _do_resolve("127.0.0.1") == "myhost.local"

    def test_returns_empty_on_failure(self):
        import socket
        with patch("core.dns_cache.socket.gethostbyaddr", side_effect=socket.herror()):
            assert _do_resolve("192.0.2.1") == ""

    def test_returns_empty_on_gaierror(self):
        import socket
        with patch("core.dns_cache.socket.gethostbyaddr", side_effect=socket.gaierror()):
            assert _do_resolve("192.0.2.2") == ""


class TestResolveAsync:
    """Tests for resolve_async (async resolution with cache)."""

    def setup_method(self):
        clear_cache()

    def test_resolves_and_caches(self):
        import asyncio
        with patch("core.dns_cache._do_resolve", return_value="resolved.host"):
            result = asyncio.run(dns_cache.resolve_async("8.8.8.8"))
        assert result == "resolved.host"
        assert get_hostname("8.8.8.8") == "resolved.host"

    def test_empty_ip_returns_none(self):
        import asyncio
        result = asyncio.run(dns_cache.resolve_async(""))
        assert result is None

    def test_failed_resolution_cached_as_empty(self):
        import asyncio
        with patch("core.dns_cache._do_resolve", return_value=""):
            asyncio.run(dns_cache.resolve_async("192.0.2.99"))
        assert get_hostname("192.0.2.99") is None  # empty string → None

    def test_cached_result_returned_without_re_resolve(self):
        import asyncio
        dns_cache._cache["1.2.3.4"] = ("cached.host", time.time())
        calls = []
        with patch("core.dns_cache._do_resolve", side_effect=lambda ip: calls.append(ip) or "new"):
            result = asyncio.run(dns_cache.resolve_async("1.2.3.4"))
        assert result == "cached.host"
        assert len(calls) == 0  # no actual resolution

    def test_pending_skips_double_resolve(self):
        import asyncio
        dns_cache._pending.add("5.5.5.5")
        result = asyncio.run(dns_cache.resolve_async("5.5.5.5"))
        assert result is None
        dns_cache._pending.discard("5.5.5.5")


class TestClearCache:
    """Tests for clear_cache."""

    def test_clears_cache_and_pending(self):
        dns_cache._cache["1.1.1.1"] = ("one.one", time.time())
        dns_cache._pending.add("2.2.2.2")
        clear_cache()
        assert dns_cache._cache == {}
        assert dns_cache._pending == set()

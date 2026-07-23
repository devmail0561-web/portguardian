"""Cache de résolution DNS inverse asynchrone."""

import asyncio
import socket
import time
from typing import Optional

from core.logs import logger

_TTL = 300  # secondes
_cache: dict[str, tuple[str, float]] = {}
_pending: set[str] = set()


def get_hostname(ip: str) -> Optional[str]:
    """Retourne le nom d'hôte depuis le cache (None si pas encore résolu)."""
    if not ip or ip in ("", "*"):
        return None
    entry = _cache.get(ip)
    if entry:
        hostname, ts = entry
        if time.time() - ts < _TTL:
            return hostname or None
    return None


async def resolve_async(ip: str) -> Optional[str]:
    """Résout une IP en arrière-plan et stocke le résultat dans le cache."""
    if not ip or ip in ("", "*"):
        return None
    if ip in _pending:
        return None
    entry = _cache.get(ip)
    if entry:
        hostname, ts = entry
        if time.time() - ts < _TTL:
            return hostname or None

    _pending.add(ip)
    try:
        try:
            result = await asyncio.to_thread(_do_resolve, ip)
        except Exception:
            result = ""
        _cache[ip] = (result, time.time())
        return result or None
    finally:
        _pending.discard(ip)


def _do_resolve(ip: str) -> str:
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


async def resolve_batch(ips: list[str]) -> None:
    """Résout un lot d'IPs inconnues en parallèle (fire-and-forget)."""
    unknown = [
        ip for ip in set(ips)
        if ip and ip not in _pending and (
            ip not in _cache or time.time() - _cache[ip][1] >= _TTL
        )
    ]
    if unknown:
        await asyncio.gather(*[resolve_async(ip) for ip in unknown], return_exceptions=True)


def clear_cache() -> None:
    _cache.clear()
    _pending.clear()

"""Suivi de la bande passante par interface réseau via psutil."""

import time
from dataclasses import dataclass

import psutil

from core.logs import logger


@dataclass
class InterfaceStat:
    name: str
    bytes_sent: int
    bytes_recv: int
    sent_rate: float    # octets/s
    recv_rate: float    # octets/s
    packets_sent: int
    packets_recv: int


class BandwidthMonitor:
    """Calcule les débits réseau par interface entre deux mesures."""

    def __init__(self) -> None:
        self._prev: dict[str, tuple[int, int, float]] = {}  # name → (sent, recv, ts)

    def update(self) -> list[InterfaceStat]:
        """Lit les compteurs actuels et retourne les débits calculés."""
        try:
            counters = psutil.net_io_counters(pernic=True)
        except Exception:
            logger.exception("Erreur lors de la lecture des compteurs réseau")
            return []

        now = time.time()
        stats: list[InterfaceStat] = []

        for name, c in counters.items():
            if name == "lo":
                continue
            prev = self._prev.get(name)
            if prev:
                prev_sent, prev_recv, prev_ts = prev
                dt = now - prev_ts
                if dt > 0:
                    sent_rate = (c.bytes_sent - prev_sent) / dt
                    recv_rate = (c.bytes_recv - prev_recv) / dt
                else:
                    sent_rate = recv_rate = 0.0
            else:
                sent_rate = recv_rate = 0.0

            self._prev[name] = (c.bytes_sent, c.bytes_recv, now)
            stats.append(InterfaceStat(
                name=name,
                bytes_sent=c.bytes_sent,
                bytes_recv=c.bytes_recv,
                sent_rate=max(0.0, sent_rate),
                recv_rate=max(0.0, recv_rate),
                packets_sent=c.packets_sent,
                packets_recv=c.packets_recv,
            ))

        return sorted(stats, key=lambda s: s.recv_rate + s.sent_rate, reverse=True)

"""Historique circulaire et rendu sparkline ASCII pour les métriques."""

from collections import deque

_BLOCKS = " ▁▂▃▄▅▆▇█"
_WIDTH = 8  # nb de points dans un sparkline


class MetricHistory:
    """Stocke l'historique des N dernières valeurs d'une métrique."""

    def __init__(self, maxlen: int = _WIDTH) -> None:
        self._data: deque[float] = deque(maxlen=maxlen)

    def push(self, value: float) -> None:
        self._data.append(value)

    def sparkline(self) -> str:
        """Retourne une chaîne de blocs Unicode représentant l'historique."""
        data = list(self._data)
        if not data:
            return " " * _WIDTH
        max_val = max(data) or 1.0
        chars = [_BLOCKS[min(int(v / max_val * 8), 8)] for v in data]
        # Compléter à gauche si moins de _WIDTH points
        return "".join(chars).rjust(_WIDTH)

    @property
    def last(self) -> float:
        return self._data[-1] if self._data else 0.0

    @property
    def trend(self) -> str:
        """→ si stable, ↑ si hausse, ↓ si baisse."""
        data = list(self._data)
        if len(data) < 2:
            return "→"
        delta = data[-1] - data[-2]
        if delta > 0.5:
            return "↑"
        if delta < -0.5:
            return "↓"
        return "→"


class HistoryStore:
    """Dictionnaire de MetricHistory indexé par PID."""

    def __init__(self, maxlen: int = _WIDTH) -> None:
        self._maxlen = maxlen
        self._store: dict[int, MetricHistory] = {}

    def push(self, pid: int, value: float) -> None:
        if pid not in self._store:
            self._store[pid] = MetricHistory(self._maxlen)
        self._store[pid].push(value)

    def sparkline(self, pid: int) -> str:
        h = self._store.get(pid)
        return h.sparkline() if h else " " * _WIDTH

    def trend(self, pid: int) -> str:
        h = self._store.get(pid)
        return h.trend if h else "→"

    def purge(self, live_pids: set[int]) -> None:
        dead = [p for p in self._store if p not in live_pids]
        for p in dead:
            del self._store[p]

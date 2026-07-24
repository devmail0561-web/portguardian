"""Simple in-memory sliding-window rate limiter."""

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self._window

        with self._lock:
            if key not in self._requests:
                self._requests[key] = deque()

            dq = self._requests[key]
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= self._max:
                return False

            dq.append(now)
            return True

    def cleanup(self) -> None:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            empty_keys = []
            for key, dq in self._requests.items():
                while dq and dq[0] < cutoff:
                    dq.popleft()
                if not dq:
                    empty_keys.append(key)
            for key in empty_keys:
                del self._requests[key]


action_limiter = RateLimiter(max_requests=10, window_seconds=60)

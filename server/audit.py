"""Action audit logging — in-memory ring buffer + JSON-lines file."""

import json
import threading
import time
from collections import deque
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "portguardian" / "logs"

_lock = threading.Lock()
_ring: deque[dict] = deque(maxlen=1000)
_loaded = False


def _load_from_disk() -> None:
    """Charge les dernières entrées du fichier audit au démarrage."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    path = LOG_DIR / "audit.jsonl"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[-1000:]:
            line = line.strip()
            if line:
                try:
                    _ring.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass


def log_action(
    action: str,
    params: dict,
    result: str,
    success: bool,
    user: str = "unknown",
) -> None:
    _load_from_disk()
    entry = {
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "user": user,
        "action": action,
        "params": params,
        "result": result,
        "success": success,
    }

    with _lock:
        _ring.append(entry)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def get_recent_audit(limit: int = 50) -> list[dict]:
    _load_from_disk()
    with _lock:
        entries = list(_ring)
    return list(reversed(entries[-limit:]))

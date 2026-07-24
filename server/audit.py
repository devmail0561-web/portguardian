"""Action audit logging — ring buffer, rotation automatique, archivage gzip."""

import gzip
import json
import threading
import time
from collections import deque
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "portguardian" / "logs"

MAX_ACTIVE_ENTRIES = 500   # entrées dans le fichier actif avant rotation
MAX_ARCHIVES       = 10    # archives .jsonl.gz conservées

_lock    = threading.Lock()
_ring: deque[dict] = deque(maxlen=1000)
_loaded  = False


# ── chargement ────────────────────────────────────────────────────────────────

def _load_from_disk() -> None:
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


# ── rotation ──────────────────────────────────────────────────────────────────

def _rotate_if_needed() -> None:
    """Archive le fichier actif si trop grand, puis nettoie les vieilles archives."""
    path = LOG_DIR / "audit.jsonl"
    if not path.exists():
        return
    try:
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return
    if len(lines) < MAX_ACTIVE_ENTRIES:
        return

    # Archiver dans audit.YYYY-MM-DD_HHMMSS.jsonl.gz
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    archive_path = LOG_DIR / f"audit.{stamp}.jsonl.gz"
    try:
        with gzip.open(archive_path, "wt", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        path.write_text("", encoding="utf-8")  # vider le fichier actif
    except OSError:
        return

    # Supprimer les archives excédentaires (garder les plus récentes)
    archives = sorted(LOG_DIR.glob("audit.*.jsonl.gz"))
    for old in archives[:-MAX_ARCHIVES]:
        try:
            old.unlink()
        except OSError:
            pass


# ── API publique ──────────────────────────────────────────────────────────────

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
        _rotate_if_needed()
    except OSError:
        pass


def get_recent_audit(limit: int = 50) -> list[dict]:
    _load_from_disk()
    with _lock:
        entries = list(_ring)
    return list(reversed(entries[-limit:]))


def list_archives() -> list[dict]:
    """Retourne les archives disponibles (nom, taille, date)."""
    archives = []
    for p in sorted(LOG_DIR.glob("audit.*.jsonl.gz"), reverse=True):
        stat = p.stat()
        archives.append({
            "name": p.name,
            "size_bytes": stat.st_size,
            "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
        })
    return archives


def read_archive(name: str) -> list[dict]:
    """Lit et retourne les entrées d'une archive gzip."""
    path = LOG_DIR / name
    if not path.exists() or not name.startswith("audit.") or not name.endswith(".jsonl.gz"):
        return []
    entries = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return entries


def generate_report(entries: list[dict]) -> dict:
    """Génère un rapport de synthèse à partir d'une liste d'entrées."""
    if not entries:
        return {"total": 0, "success": 0, "failure": 0, "by_action": {}, "by_user": {}, "period": {}}

    by_action: dict[str, dict] = {}
    by_user: dict[str, int] = {}
    successes = 0

    for e in entries:
        action = e.get("action", "unknown")
        user = e.get("user", "unknown")
        ok = e.get("success", False)
        if ok:
            successes += 1
        by_action.setdefault(action, {"total": 0, "success": 0, "failure": 0})
        by_action[action]["total"] += 1
        if ok:
            by_action[action]["success"] += 1
        else:
            by_action[action]["failure"] += 1
        by_user[user] = by_user.get(user, 0) + 1

    timestamps = [e.get("timestamp", 0) for e in entries if e.get("timestamp")]
    period = {}
    if timestamps:
        period = {
            "from": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(min(timestamps))),
            "to":   time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(max(timestamps))),
        }

    return {
        "total": len(entries),
        "success": successes,
        "failure": len(entries) - successes,
        "by_action": dict(sorted(by_action.items(), key=lambda x: -x[1]["total"])),
        "by_user": dict(sorted(by_user.items(), key=lambda x: -x[1])),
        "period": period,
    }

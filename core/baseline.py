"""Snapshot baseline et détection de déviations."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import BASELINE_FILE
from core.logs import logger
from core.ports import ConnectionInfo


@dataclass
class BaselineEntry:
    protocol: str
    local_addr: str
    local_port: int
    status: str
    process_name: str
    username: str


def _conn_to_entry(conn: ConnectionInfo) -> BaselineEntry:
    return BaselineEntry(
        protocol=conn.protocol,
        local_addr=conn.local_addr,
        local_port=conn.local_port,
        status=conn.status,
        process_name=conn.process_name,
        username=conn.username,
    )


def _entry_key(e: BaselineEntry) -> tuple:
    return (e.protocol, e.local_addr, e.local_port, e.status, e.process_name)


def save_baseline(connections: list[ConnectionInfo]) -> None:
    """Sauvegarde l'état actuel comme baseline."""
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    entries = [_conn_to_entry(c).__dict__ for c in connections]
    data = {"timestamp": time.time(), "entries": entries}
    BASELINE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Baseline sauvegardée (%d entrées)", len(entries))


def load_baseline() -> Optional[tuple[float, list[BaselineEntry]]]:
    """Charge la baseline. Retourne (timestamp, entries) ou None."""
    if not BASELINE_FILE.exists():
        return None
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        entries = [BaselineEntry(**e) for e in data["entries"]]
        return data["timestamp"], entries
    except Exception:
        logger.exception("Erreur lors du chargement de la baseline")
        return None


def get_deviations(
    connections: list[ConnectionInfo],
    baseline: list[BaselineEntry],
) -> tuple[list[ConnectionInfo], list[BaselineEntry]]:
    """Retourne (nouvelles, disparues) par rapport à la baseline.

    - nouvelles : connexions présentes maintenant mais absentes de la baseline
    - disparues : entrées de la baseline absentes des connexions actuelles
    """
    baseline_keys = {_entry_key(e) for e in baseline}
    current_keys = {_entry_key(_conn_to_entry(c)) for c in connections}

    new_conns = [c for c in connections if _entry_key(_conn_to_entry(c)) not in baseline_keys]
    gone = [e for e in baseline if _entry_key(e) not in current_keys]
    return new_conns, gone

"""Surveillance des changements réseau (nouveaux ports, processus terminés)."""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from core.logs import logger
from core.ports import get_all_connections, ConnectionInfo
from config import WATCHER_INTERVAL

HISTORY_MAXLEN = 500


@dataclass
class NetworkEvent:
    """Événement détecté par le watcher."""

    event_type: str  # "port_opened", "port_closed", "process_new", "process_ended"
    port: int
    protocol: str
    pid: Optional[int]
    process_name: str
    address: str

    @property
    def description(self) -> str:
        if self.event_type == "port_opened":
            return f"Nouveau port ouvert: {self.protocol}:{self.port} ({self.process_name}, PID {self.pid})"
        elif self.event_type == "port_closed":
            return f"Port fermé: {self.protocol}:{self.port} ({self.process_name})"
        elif self.event_type == "process_new":
            return f"Nouveau processus: {self.process_name} (PID {self.pid}) sur port {self.port}"
        elif self.event_type == "process_ended":
            return f"Processus terminé: {self.process_name} (PID {self.pid})"
        return f"{self.event_type}: port {self.port}"


class NetworkWatcher:
    """Surveille les changements dans les connexions réseau."""

    def __init__(self, on_event: Optional[Callable[[NetworkEvent], None]] = None) -> None:
        self._previous_state: dict[tuple, ConnectionInfo] = {}
        self._on_event = on_event
        self._running = False
        self._history: deque[NetworkEvent] = deque(maxlen=HISTORY_MAXLEN)
        self._prev_count: int = -1

    @property
    def history(self) -> list[NetworkEvent]:
        """Historique des événements détectés."""
        return list(self._history)

    def _make_key(self, conn: ConnectionInfo) -> tuple:
        """Crée une clé unique pour une connexion."""
        return (conn.protocol, conn.local_addr, conn.local_port, conn.pid)

    def check_changes(self) -> list[NetworkEvent]:
        """Compare l'état actuel avec le précédent et retourne les changements."""
        events: list[NetworkEvent] = []

        try:
            current_connections = get_all_connections()
        except Exception:
            logger.exception("Erreur lors de la collecte pour le watcher")
            return events

        current_count = len(current_connections)
        if self._previous_state and current_count == self._prev_count:
            return events
        self._prev_count = current_count

        current_state: dict[tuple, ConnectionInfo] = {}
        for conn in current_connections:
            key = self._make_key(conn)
            current_state[key] = conn

        if not self._previous_state:
            self._previous_state = current_state
            return events

        # Nouveaux ports/processus
        for key, conn in current_state.items():
            if key not in self._previous_state:
                event_type = "port_opened" if conn.status == "LISTEN" else "process_new"

                event = NetworkEvent(
                    event_type=event_type,
                    port=conn.local_port,
                    protocol=conn.protocol,
                    pid=conn.pid,
                    process_name=conn.process_name,
                    address=conn.local_addr,
                )
                events.append(event)

        # Ports/processus fermés
        for key, conn in self._previous_state.items():
            if key not in current_state:
                event_type = "port_closed" if conn.status == "LISTEN" else "process_ended"
                event = NetworkEvent(
                    event_type=event_type,
                    port=conn.local_port,
                    protocol=conn.protocol,
                    pid=conn.pid,
                    process_name=conn.process_name,
                    address=conn.local_addr,
                )
                events.append(event)

        self._previous_state = current_state

        for event in events:
            self._history.append(event)
            logger.info("Watcher: %s", event.description)
            if self._on_event:
                self._on_event(event)

        return events

    async def run(self) -> None:
        """Boucle de surveillance asynchrone."""
        self._running = True
        logger.info("Watcher démarré (intervalle: %.1fs)", WATCHER_INTERVAL)

        while self._running:
            await asyncio.to_thread(self.check_changes)
            await asyncio.sleep(WATCHER_INTERVAL)

    def stop(self) -> None:
        """Arrête la boucle de surveillance."""
        self._running = False
        logger.info("Watcher arrêté")

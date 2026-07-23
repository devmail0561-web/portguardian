"""Agent daemon qui collecte et pousse les données périodiquement."""

import asyncio
import json
import logging
import platform
import time
from pathlib import Path

from core.ports import get_all_connections, get_listening_ports
from core.bandwidth import BandwidthMonitor
from daemon.notifier import Notifier
from daemon.config import DaemonConfig

logger = logging.getLogger("portguardian.daemon")


class Agent:
    """Agent de collecte qui tourne en arrière-plan."""

    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.notifier = Notifier(config)
        self.bw_monitor = BandwidthMonitor()
        self._previous_ports: set[tuple[str, str, int, str]] = set()
        self._running = False
        self._hostname = config.hostname or platform.node()

    def _collect_snapshot(self) -> dict:
        connections = get_all_connections()
        listening = get_listening_ports()
        bw_stats = self.bw_monitor.update()

        return {
            "hostname": self._hostname,
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "connections_total": len(connections),
            "listening_total": len(listening),
            "connections": [
                {
                    "protocol": c.protocol,
                    "local_addr": c.local_addr,
                    "local_port": c.local_port,
                    "remote_addr": c.remote_addr,
                    "remote_port": c.remote_port,
                    "status": c.status,
                    "pid": c.pid,
                    "process_name": c.process_name,
                }
                for c in connections
            ],
            "listening": [
                {
                    "protocol": c.protocol,
                    "local_addr": c.local_addr,
                    "local_port": c.local_port,
                    "pid": c.pid,
                    "process_name": c.process_name,
                }
                for c in listening
            ],
            "bandwidth": [
                {
                    "interface": s.name,
                    "sent_rate": s.sent_rate,
                    "recv_rate": s.recv_rate,
                    "bytes_sent": s.bytes_sent,
                    "bytes_recv": s.bytes_recv,
                }
                for s in bw_stats
            ],
        }

    def _detect_changes(self, snapshot: dict) -> list[dict]:
        """Détecte les ports ouverts/fermés depuis le dernier scan."""
        current_ports = set()
        for c in snapshot["listening"]:
            key = (c["protocol"], c["local_addr"], c["local_port"], c["process_name"])
            current_ports.add(key)

        events = []

        if self._previous_ports:
            new_ports = current_ports - self._previous_ports
            closed_ports = self._previous_ports - current_ports

            for proto, addr, port, proc in new_ports:
                events.append({
                    "type": "port_opened",
                    "severity": "warning",
                    "message": f"Nouveau port en écoute: {proto} {addr}:{port} ({proc})",
                    "details": {"protocol": proto, "address": addr, "port": port, "process": proc},
                })

            for proto, addr, port, proc in closed_ports:
                events.append({
                    "type": "port_closed",
                    "severity": "info",
                    "message": f"Port fermé: {proto} {addr}:{port} ({proc})",
                    "details": {"protocol": proto, "address": addr, "port": port, "process": proc},
                })

        self._previous_ports = current_ports
        return events

    async def _push_to_server(self, snapshot: dict) -> bool:
        """Envoie le snapshot au serveur central."""
        if not self.config.server_url:
            return False

        import urllib.request
        import urllib.error

        url = f"{self.config.server_url.rstrip('/')}/api/report"
        data = json.dumps(snapshot).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            response = await asyncio.to_thread(
                urllib.request.urlopen, req, timeout=10
            )
            if response.status == 200:
                logger.debug("Snapshot envoyé au serveur central")
                return True
            else:
                logger.warning("Serveur central a répondu %d", response.status)
                return False
        except urllib.error.URLError as e:
            logger.error("Impossible de joindre le serveur central: %s", e)
            return False
        except Exception as e:
            logger.error("Erreur push: %s", e)
            return False

    async def _save_local(self, snapshot: dict) -> None:
        """Sauvegarde locale du snapshot pour historique."""
        data_dir = Path(self.config.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        latest = data_dir / "latest.json"
        latest.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

        if self.config.keep_history:
            history_dir = data_dir / "history"
            history_dir.mkdir(exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            history_file = history_dir / f"snapshot_{ts}.json"
            history_file.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

            self._cleanup_history(history_dir)

    def _cleanup_history(self, history_dir: Path) -> None:
        """Garde uniquement les N derniers snapshots."""
        files = sorted(history_dir.glob("snapshot_*.json"))
        max_files = self.config.max_history_files
        if len(files) > max_files:
            for f in files[:-max_files]:
                f.unlink()

    async def run_once(self) -> dict:
        """Exécute un cycle de collecte."""
        snapshot = await asyncio.to_thread(self._collect_snapshot)
        events = self._detect_changes(snapshot)
        snapshot["events"] = events

        await self._save_local(snapshot)

        if self.config.server_url:
            await self._push_to_server(snapshot)

        if events and self.config.notifications_enabled:
            for event in events:
                await self.notifier.send(event)

        return snapshot

    async def run(self) -> None:
        """Boucle principale du daemon."""
        self._running = True
        logger.info(
            "Agent démarré — intervalle=%ds, serveur=%s, notifications=%s",
            self.config.interval,
            self.config.server_url or "aucun",
            self.config.notifications_enabled,
        )

        while self._running:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Erreur dans le cycle de collecte")
            await asyncio.sleep(self.config.interval)

    def stop(self) -> None:
        self._running = False

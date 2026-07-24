"""Agent daemon — collecte complète, push avec retry/queue, pull de commandes."""

import asyncio
import json
import logging
import platform
import socket
import time
from pathlib import Path

import psutil

from core.ports import get_all_connections, get_listening_ports
from core.bandwidth import BandwidthMonitor
from core.services import get_service_for_pid
from daemon.notifier import Notifier
from daemon.config import DaemonConfig

logger = logging.getLogger("portguardian.daemon")

MAX_QUEUE_SIZE = 100
BACKOFF_BASE = 5
BACKOFF_MAX = 300


def _resolve_ip(ip: str) -> str:
    """Résolution DNS inverse (timeout court)."""
    if not ip or ip.startswith("127.") or ip == "::1" or ip == "0.0.0.0":
        return ""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


def _get_process_metrics(pids: set[int]) -> dict[int, dict]:
    """Collecte CPU, mémoire, I/O pour un ensemble de PIDs."""
    metrics: dict[int, dict] = {}
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                cpu = proc.cpu_percent(interval=None)
                mem = proc.memory_info()
                try:
                    io = proc.io_counters()
                    io_read = io.read_bytes
                    io_write = io.write_bytes
                except (psutil.AccessDenied, AttributeError):
                    io_read = io_write = 0

                create_time = proc.create_time()
                uptime = time.time() - create_time

                metrics[pid] = {
                    "cpu_percent": round(cpu, 1),
                    "memory_rss": mem.rss,
                    "memory_percent": round(proc.memory_percent(), 1),
                    "io_read_bytes": io_read,
                    "io_write_bytes": io_write,
                    "uptime_seconds": int(uptime),
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return metrics


class Agent:
    """Agent de collecte complet avec retry, queue locale, et pull de commandes."""

    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.notifier = Notifier(config)
        self.bw_monitor = BandwidthMonitor()
        self._previous_ports: set[tuple[str, str, int, str]] = set()
        self._running = False
        self._hostname = config.hostname or platform.node()
        self._queue: list[dict] = []
        self._consecutive_failures = 0
        self._dns_cache: dict[str, str] = {}
        self._proc_cache: dict[int, psutil.Process] = {}
        self._service_cache: dict[int, str] = {}

    def _resolve_batch(self, ips: list[str]) -> dict[str, str]:
        """Résolution DNS batch avec cache."""
        result: dict[str, str] = {}
        for ip in ips:
            if ip in self._dns_cache:
                result[ip] = self._dns_cache[ip]
            else:
                hostname = _resolve_ip(ip)
                self._dns_cache[ip] = hostname
                if hostname:
                    result[ip] = hostname
        return result

    def _get_service_for_pid(self, pid: int) -> str:
        """Détection service systemd avec cache."""
        if pid in self._service_cache:
            return self._service_cache[pid]
        svc = get_service_for_pid(pid) or ""
        self._service_cache[pid] = svc
        return svc

    def _collect_process_cpu_prewarm(self, pids: set[int]) -> None:
        """Pré-chauffe le cache CPU psutil pour obtenir des valeurs non-nulles."""
        dead = set(self._proc_cache.keys()) - pids
        for pid in dead:
            del self._proc_cache[pid]
            self._service_cache.pop(pid, None)

        for pid in pids:
            if pid not in self._proc_cache:
                try:
                    p = psutil.Process(pid)
                    p.cpu_percent(interval=None)
                    self._proc_cache[pid] = p
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

    def _collect_snapshot(self) -> dict:
        connections = get_all_connections()
        listening = get_listening_ports()
        bw_stats = self.bw_monitor.update()

        all_pids = {c.pid for c in connections if c.pid}
        self._collect_process_cpu_prewarm(all_pids)
        process_metrics = _get_process_metrics(all_pids)

        # Services pour les processus en écoute
        listen_pids = {c.pid for c in listening if c.pid}
        services: dict[int, str] = {}
        for pid in listen_pids:
            svc = self._get_service_for_pid(pid)
            if svc:
                services[pid] = svc

        # DNS inverse sur les IPs distantes
        remote_ips = list({c.remote_addr for c in connections if c.remote_addr and c.remote_addr not in ("0.0.0.0", "::1", "127.0.0.1", "")})
        dns_map = self._resolve_batch(remote_ips)

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
                    "dns_hostname": dns_map.get(c.remote_addr, ""),
                    "service": services.get(c.pid, ""),
                    **(process_metrics.get(c.pid, {})),
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
                    "service": services.get(c.pid, ""),
                    **(process_metrics.get(c.pid, {})),
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
                    "packets_sent": s.packets_sent,
                    "packets_recv": s.packets_recv,
                }
                for s in bw_stats
            ],
            "process_summary": [
                {
                    "pid": pid,
                    "name": next((c.process_name for c in connections if c.pid == pid), ""),
                    "service": services.get(pid, ""),
                    "connections_count": sum(1 for c in connections if c.pid == pid),
                    **metrics,
                }
                for pid, metrics in process_metrics.items()
            ],
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "boot_time": psutil.boot_time(),
            },
            **self._collect_firewall(),
        }

    def _collect_firewall(self) -> dict:
        """Collecte les règles firewall locales de la machine."""
        try:
            from core.firewall import list_blocked_ports, get_backend
            rules = list_blocked_ports()
            backend = get_backend()
            return {"firewall": {"backend": backend, "rules": rules}}
        except Exception:
            return {"firewall": {"backend": "", "rules": [], "error": "acces refuse (sudo requis?)"}}

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
        """Envoie le snapshot au serveur avec retry et backoff exponentiel."""
        if not self.config.server_url:
            return False

        import urllib.request
        import urllib.error
        import ssl

        url = f"{self.config.server_url.rstrip('/')}/api/report"
        data = json.dumps(snapshot).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        ctx = None
        if url.startswith("https://"):
            ctx = ssl.create_default_context()

        try:
            response = await asyncio.to_thread(
                urllib.request.urlopen, req, timeout=15, context=ctx
            )
            if response.status == 200:
                self._consecutive_failures = 0
                logger.debug("Snapshot envoyé au serveur central")
                return True
            else:
                logger.warning("Serveur central a répondu %d", response.status)
                self._consecutive_failures += 1
                return False
        except (urllib.error.URLError, OSError) as e:
            self._consecutive_failures += 1
            logger.error("Impossible de joindre le serveur (%d echecs): %s",
                         self._consecutive_failures, e)
            return False

    async def _flush_queue(self) -> None:
        """Tente de renvoyer les snapshots en queue."""
        if not self._queue or not self.config.server_url:
            return

        import urllib.request
        import urllib.error
        import ssl

        url = f"{self.config.server_url.rstrip('/')}/api/report"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        ctx = None
        if url.startswith("https://"):
            ctx = ssl.create_default_context()

        sent = 0
        while self._queue:
            snapshot = self._queue[0]
            data = json.dumps(snapshot).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                response = await asyncio.to_thread(
                    urllib.request.urlopen, req, timeout=15, context=ctx
                )
                if response.status == 200:
                    self._queue.pop(0)
                    sent += 1
                else:
                    break
            except (urllib.error.URLError, OSError):
                break

        if sent:
            logger.info("Queue: %d snapshot(s) renvoyé(s), %d restant(s)", sent, len(self._queue))

    def _enqueue(self, snapshot: dict) -> None:
        """Ajoute un snapshot à la queue locale."""
        self._queue.append(snapshot)
        if len(self._queue) > MAX_QUEUE_SIZE:
            self._queue.pop(0)
            logger.warning("Queue pleine — snapshot le plus ancien supprimé")

    async def _pull_commands(self) -> None:
        """Interroge le serveur pour des commandes en attente."""
        if not self.config.server_url:
            return

        import urllib.request
        import urllib.error

        url = f"{self.config.server_url.rstrip('/')}/api/commands/{self._hostname}"
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            response = await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
            if response.status == 200:
                commands = json.loads(response.read().decode("utf-8"))
                for cmd in commands:
                    await self._execute_command(cmd)
        except (urllib.error.URLError, OSError):
            pass
        except Exception:
            logger.exception("Erreur lors du pull de commandes")

    async def _execute_command(self, cmd: dict) -> None:
        """Exécute une commande reçue du serveur."""
        import os
        import signal as sig

        action = cmd.get("action", "")
        params = cmd.get("params", {})
        logger.info("Commande reçue: %s %s", action, params)

        try:
            if action == "kill":
                pid = params.get("pid")
                signal_name = params.get("signal", "SIGTERM")
                signal_map = {"SIGTERM": sig.SIGTERM, "SIGKILL": sig.SIGKILL,
                              "SIGSTOP": sig.SIGSTOP, "SIGCONT": sig.SIGCONT}
                if pid and pid > 1 and signal_name in signal_map:
                    os.kill(pid, signal_map[signal_name])
                    logger.info("Signal %s envoyé à PID %d", signal_name, pid)

            elif action == "block-port":
                from core.firewall import block_ports
                spec = params.get("spec", "")
                proto = params.get("protocol", "tcp")
                direction = params.get("direction", "in")
                if spec:
                    ok, msg = block_ports(spec, proto, direction)
                    logger.info("Block port %s: %s", spec, msg)

            elif action == "unblock-port":
                from core.firewall import unblock_ports
                spec = params.get("spec", "")
                proto = params.get("protocol", "tcp")
                direction = params.get("direction", "in")
                if spec:
                    ok, msg = unblock_ports(spec, proto, direction)
                    logger.info("Unblock port %s: %s", spec, msg)

            elif action == "block-ip":
                from core.firewall import block_ip
                spec = params.get("spec", "")
                direction = params.get("direction", "in")
                if spec:
                    ok, msg = block_ip(spec, direction)
                    logger.info("Block IP %s: %s", spec, msg)

            elif action == "unblock-ip":
                from core.firewall import unblock_ip
                spec = params.get("spec", "")
                direction = params.get("direction", "in")
                if spec:
                    ok, msg = unblock_ip(spec, direction)
                    logger.info("Unblock IP %s: %s", spec, msg)

            elif action == "service":
                from core.services import service_action
                name = params.get("name", "")
                act = params.get("action", "")
                if name and act:
                    ok, msg = service_action(name, act)
                    logger.info("Service %s %s: %s", name, act, msg)

            else:
                logger.warning("Commande inconnue: %s", action)

        except Exception:
            logger.exception("Erreur lors de l'exécution de la commande %s", action)

    async def _send_heartbeat(self) -> None:
        """Envoie un heartbeat léger au serveur."""
        if not self.config.server_url:
            return

        import urllib.request
        import urllib.error

        url = f"{self.config.server_url.rstrip('/')}/api/heartbeat"
        data = json.dumps({
            "hostname": self._hostname,
            "timestamp": time.time(),
            "queue_size": len(self._queue),
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=5)
        except (urllib.error.URLError, OSError):
            pass

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
        """Rotation : par nombre de fichiers ET par taille totale (max 100 MB)."""
        files = sorted(history_dir.glob("snapshot_*.json"))
        max_files = self.config.max_history_files
        max_size_bytes = 100 * 1024 * 1024

        if len(files) > max_files:
            for f in files[:-max_files]:
                f.unlink()
            files = sorted(history_dir.glob("snapshot_*.json"))

        total_size = sum(f.stat().st_size for f in files)
        while total_size > max_size_bytes and len(files) > 1:
            removed = files.pop(0)
            total_size -= removed.stat().st_size
            removed.unlink()

    async def run_once(self) -> dict:
        """Exécute un cycle de collecte complet."""
        snapshot = await asyncio.to_thread(self._collect_snapshot)
        events = self._detect_changes(snapshot)
        snapshot["events"] = events

        await self._save_local(snapshot)

        if self.config.server_url:
            # D'abord tenter de vider la queue
            if self._consecutive_failures == 0 and self._queue:
                await self._flush_queue()

            success = await self._push_to_server(snapshot)
            if not success:
                self._enqueue(snapshot)

        if events and self.config.notifications_enabled:
            for event in events:
                await self.notifier.send(event)

        return snapshot

    def _backoff_delay(self) -> float:
        """Calcul du délai de backoff exponentiel."""
        if self._consecutive_failures == 0:
            return 0
        delay = min(BACKOFF_BASE * (2 ** (self._consecutive_failures - 1)), BACKOFF_MAX)
        return delay

    async def run(self) -> None:
        """Boucle principale du daemon."""
        self._running = True
        logger.info(
            "Agent démarré — intervalle=%ds, serveur=%s, notifications=%s, hostname=%s",
            self.config.interval,
            self.config.server_url or "aucun",
            self.config.notifications_enabled,
            self._hostname,
        )

        # Premier appel cpu_percent pour initialiser les compteurs
        psutil.cpu_percent(interval=None)

        heartbeat_counter = 0

        while self._running:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Erreur dans le cycle de collecte")

            # Pull commandes du serveur
            try:
                await self._pull_commands()
            except Exception:
                logger.exception("Erreur lors du pull de commandes")

            # Heartbeat toutes les 5 itérations
            heartbeat_counter += 1
            if heartbeat_counter >= 5:
                heartbeat_counter = 0
                await self._send_heartbeat()

            # Intervalle avec backoff si le serveur est injoignable
            delay = self.config.interval + self._backoff_delay()
            if delay > self.config.interval:
                logger.debug("Backoff: attente %ds (base=%ds)", delay, self.config.interval)
            await asyncio.sleep(delay)

    def stop(self) -> None:
        self._running = False

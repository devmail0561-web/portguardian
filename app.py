"""Application principale PortGuardian (Textual)."""

import asyncio
import signal
import time

import psutil
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

from textual.events import DeliveryFailed

from config import REFRESH_INTERVAL, EXPORT_DIR, SCREENSHOTS_DIR
from core.alerts import AlertEngine
from core.bandwidth import BandwidthMonitor
from core.baseline import save_baseline, load_baseline, get_deviations, BaselineEntry
from core.dns_cache import resolve_batch, get_hostname
from core.filters import FilterStore
from core.logs import logger
from core.permissions import check_permissions, suggest_elevation
from core.ports import get_all_connections, ConnectionInfo
from core.process import get_process_detail, get_process_cpu_memory
from core.search import filter_connections
from core.services import get_service_for_pid, service_action, get_service_logs
from core.sparkline import HistoryStore
from core.watcher import NetworkWatcher, NetworkEvent
from ui.alerts_screen import AlertsScreen
from ui.dashboard import Dashboard
from ui.header import SystemHeader
from ui.history_screen import HistoryScreen
from ui.stats_screen import StatsScreen
from ui.tables import ConnectionsTable
from ui.details import ProcessDetailsPanel
from ui.dialogs import (
    ConfirmDialog, SearchDialog, SortDialog, ExportDialog, ServiceDialog,
    BlockPortDialog, LogScreen,
)
from core.firewall import block_ports, unblock_ports, is_firewall_available


_proc_cache: dict[int, psutil.Process] = {}


def _collect_process_metrics(
    pids: set[int],
) -> tuple[dict[int, float], dict[int, float], dict[int, str]]:
    global _proc_cache
    cpu_map: dict[int, float] = {}
    memory_map: dict[int, float] = {}
    uptime_map: dict[int, str] = {}
    now = time.time()

    dead_pids = set(_proc_cache.keys()) - pids
    for pid in dead_pids:
        del _proc_cache[pid]

    for pid in pids:
        try:
            if pid not in _proc_cache:
                _proc_cache[pid] = psutil.Process(pid)
                _proc_cache[pid].cpu_percent(interval=None)
            proc = _proc_cache[pid]
            with proc.oneshot():
                cpu_map[pid] = proc.cpu_percent(interval=None)
                memory_map[pid] = proc.memory_percent()
                uptime_secs = now - proc.create_time()
                if uptime_secs > 86400:
                    uptime_map[pid] = f"{int(uptime_secs // 86400)}j"
                elif uptime_secs > 3600:
                    uptime_map[pid] = f"{int(uptime_secs // 3600)}h"
                else:
                    uptime_map[pid] = f"{int(uptime_secs // 60)}m"
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            _proc_cache.pop(pid, None)
            cpu_map[pid] = 0.0
            memory_map[pid] = 0.0
            uptime_map[pid] = "-"
    return cpu_map, memory_map, uptime_map


class PortGuardianApp(App):
    """Application TUI pour la surveillance des ports réseau."""

    TITLE = "PortGuardian"
    SUB_TITLE = "Surveillance des ports, processus et services"

    BINDINGS = [
        ("q", "quit", "Quitter"),
        ("r", "refresh", "Rafraîchir"),
        ("slash", "search", "Rechercher"),
        ("s", "sort", "Trier"),
        ("e", "export", "Exporter"),
        ("k", "signal_term", "SIGTERM"),
        ("K", "signal_kill", "SIGKILL"),
        ("p", "suspend", "Pause"),
        ("c", "resume", "Reprendre"),
        ("S", "service_menu", "Service"),
        ("b", "block_ports", "Bloquer ports"),
        ("h", "history", "Historique"),
        ("t", "stats", "Stats"),
        ("A", "alerts", "Alertes"),
        ("B", "baseline", "Baseline"),
        ("f", "saved_filters", "Filtres"),
        ("escape", "clear_search", "Effacer filtre"),
        ("ctrl+p", "screenshot", "Screenshot"),
    ]

    CSS = """
Screen {
    layout: vertical;
}

Button {
    height: 1;
    min-width: 10;
    padding: 0 2;
    margin: 0 1;
    text-align: center;
    content-align: center middle;
    border: none;
}

Button:hover {
    text-style: bold;
}

#permission-warning {
    height: auto;
    padding: 0 2;
    background: $warning-darken-2;
    color: $text;
    text-align: center;
    border-bottom: solid $warning;
    text-style: bold;
}

#system-header {
    height: 1;
    background: $boost;
    padding: 0 1;
    border-bottom: solid $primary-darken-3;
}

#process-details {
    border-top: solid $primary-darken-2;
}
"""

    def __init__(self) -> None:
        super().__init__()
        self._has_root = False
        self._search_filter: str = ""
        self._all_connections: list[ConnectionInfo] = []
        self._cpu_map: dict[int, float] = {}
        self._memory_map: dict[int, float] = {}
        self._service_map: dict[int, str] = {}
        self._uptime_map: dict[int, str] = {}
        self._dns_map: dict[str, str] = {}
        self._watcher = NetworkWatcher(on_event=self._on_network_event)
        self._alert_engine = AlertEngine()
        self._bw_monitor = BandwidthMonitor()
        self._bw_stats = []
        self._cpu_history = HistoryStore()
        self._baseline: list[BaselineEntry] | None = None
        self._baseline_ts: float = 0.0
        self._filter_store = FilterStore()
        self._active_alerts: list = []
        self._load_baseline_on_start()

    def _load_baseline_on_start(self) -> None:
        result = load_baseline()
        if result:
            self._baseline_ts, self._baseline = result

    def compose(self) -> ComposeResult:
        yield Header()
        if not check_permissions():
            yield Static(suggest_elevation(), id="permission-warning")
        yield Dashboard()

    def on_mount(self) -> None:
        logger.info("Démarrage de PortGuardian")
        self._has_root = check_permissions()
        self.set_interval(REFRESH_INTERVAL, self._auto_refresh)
        self._trigger_refresh()
        self.run_worker(self._watcher.run, exclusive=True, group="watcher")

    def _on_network_event(self, event: NetworkEvent) -> None:
        self.call_from_thread(self._notify_event, event)

    def _notify_event(self, event: NetworkEvent) -> None:
        severity = "information"
        if event.event_type == "port_closed":
            severity = "warning"
        self.notify(event.description, severity=severity, timeout=5)

    def _trigger_refresh(self) -> None:
        self.run_worker(self._refresh_data, exclusive=True, group="refresh")

    async def _refresh_data(self) -> None:
        connections = await asyncio.to_thread(get_all_connections)
        self._all_connections = connections

        pids = {c.pid for c in connections if c.pid}
        cpu_map, memory_map, uptime_map = await asyncio.to_thread(
            _collect_process_metrics, pids
        )
        self._cpu_map = cpu_map
        self._memory_map = memory_map
        self._uptime_map = uptime_map

        # Sparklines CPU
        for pid, cpu in cpu_map.items():
            self._cpu_history.push(pid, cpu)
        self._cpu_history.purge(pids)

        # Service map (LISTEN uniquement, avec cache)
        live_pids = {c.pid for c in connections if c.pid}
        self._service_map = {k: v for k, v in self._service_map.items() if k in live_pids}
        listen_pids = {c.pid for c in connections if c.pid and c.status == "LISTEN"}
        for pid in listen_pids - set(self._service_map.keys()):
            svc = await asyncio.to_thread(get_service_for_pid, pid)
            if svc:
                self._service_map[pid] = svc

        # Bande passante
        self._bw_stats = await asyncio.to_thread(self._bw_monitor.update)

        # DNS inverse (fire-and-forget sur les IPs distantes)
        remote_ips = [c.remote_addr for c in connections if c.remote_addr]
        await resolve_batch(remote_ips)
        for ip in remote_ips:
            h = get_hostname(ip)
            if h:
                self._dns_map[ip] = h

        # Évaluation des alertes
        self._active_alerts = self._alert_engine.evaluate(connections)
        if self._active_alerts:
            critical = [a for a in self._active_alerts if a.severity == "critical"]
            if critical:
                self.notify(
                    f"⚠ {len(critical)} alerte(s) critiques — appuyez sur A",
                    severity="error",
                    timeout=6,
                )

        filtered = filter_connections(connections, self._search_filter)
        self._update_ui(filtered)

    def _update_ui(self, connections: list[ConnectionInfo]) -> None:
        try:
            # Sparklines pour l'affichage
            sparkline_map = {pid: self._cpu_history.sparkline(pid) for pid in {c.pid or 0 for c in connections}}

            # Clés baseline pour surlignage
            baseline_keys: set[tuple] = set()
            if self._baseline:
                baseline_keys = {
                    (e.protocol, e.local_addr, e.local_port, e.process_name)
                    for e in self._baseline
                }

            table = self.query_one("#connections-table", ConnectionsTable)
            table.update_data(
                connections,
                cpu_map=self._cpu_map,
                memory_map=self._memory_map,
                service_map=self._service_map,
                uptime_map=self._uptime_map,
                sparkline_map=sparkline_map,
                dns_map=self._dns_map,
                baseline_keys=baseline_keys if self._baseline else None,
            )

            header = self.query_one("#system-header", SystemHeader)
            listening = [c for c in self._all_connections if c.status == "LISTEN"]
            header.update_stats(len(self._all_connections), len(listening))
        except Exception:
            logger.exception("Erreur lors de la mise à jour de l'UI")

    def _auto_refresh(self) -> None:
        self._trigger_refresh()

    # --- Événements table ---

    def on_connections_table_row_selected(
        self, event: ConnectionsTable.RowSelected
    ) -> None:
        conn = event.connection
        if conn.pid:
            self.run_worker(
                self._load_process_detail(conn.pid),
                exclusive=True,
                group="details",
            )

    async def _load_process_detail(self, pid: int) -> None:
        detail = await asyncio.to_thread(get_process_detail, pid)
        panel = self.query_one("#process-details", ProcessDetailsPanel)
        panel.show_process(detail)

    # --- Screenshots ---

    def action_screenshot(self) -> None:
        """Sauvegarde un screenshot SVG dans le répertoire screenshots/."""
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = self.save_screenshot(path=str(SCREENSHOTS_DIR))
        self.notify(f"Screenshot: {path}", timeout=5)
        logger.info("Screenshot sauvegardé: %s", path)

    def on_delivery_failed(self, event: DeliveryFailed) -> None:
        """Fallback si deliver_screenshot échoue (permissions root)."""
        if event.name == "screenshot":
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            path = self.save_screenshot(path=str(SCREENSHOTS_DIR))
            self.notify(f"Screenshot: {path}", timeout=5)
            logger.info("Screenshot (fallback) sauvegardé: %s", path)

    # --- Actions ---

    def action_quit(self) -> None:
        logger.info("Arrêt de PortGuardian")
        self.exit()

    def action_refresh(self) -> None:
        self._trigger_refresh()

    def action_search(self) -> None:
        def on_result(result: str | None) -> None:
            if result is not None:
                self._search_filter = result
                self._trigger_refresh()
                if result:
                    self.notify(f"Filtre: '{result}'", timeout=3)
                else:
                    self.notify("Filtre effacé", timeout=2)

        self.push_screen(SearchDialog(), on_result)

    def action_clear_search(self) -> None:
        panel = self.query_one("#process-details", ProcessDetailsPanel)
        if panel._detail is not None:
            panel.clear_details()
            return
        if self._search_filter:
            self._search_filter = ""
            self._trigger_refresh()
            self.notify("Filtre effacé", timeout=2)

    def action_sort(self) -> None:
        def on_result(result: tuple[str, bool] | None) -> None:
            if result:
                col, reverse = result
                table = self.query_one("#connections-table", ConnectionsTable)
                table.set_sort(col, reverse)
                self._trigger_refresh()
                direction = "↓" if reverse else "↑"
                self.notify(f"Tri: {col} {direction}", timeout=2)

        self.push_screen(SortDialog(), on_result)

    def action_export(self) -> None:
        def on_result(result: str | None) -> None:
            if result:
                self._do_export(result)

        self.push_screen(ExportDialog(), on_result)

    def _do_export(self, fmt: str) -> None:
        from core.exporter import export_connections
        filepath = export_connections(
            self._all_connections, fmt,
            cpu_map=self._cpu_map,
            memory_map=self._memory_map,
            service_map=self._service_map,
            uptime_map=self._uptime_map,
        )
        if filepath:
            self.notify(f"Exporté: {filepath}", timeout=5)
            logger.info("Export %s vers %s", fmt, filepath)
        else:
            self.notify("Erreur lors de l'export", severity="error", timeout=5)

    def action_signal_term(self) -> None:
        self._send_signal_to_selected("SIGTERM", signal.SIGTERM)

    def action_signal_kill(self) -> None:
        self._send_signal_to_selected("SIGKILL", signal.SIGKILL)

    def action_suspend(self) -> None:
        self._send_signal_to_selected("SIGSTOP", signal.SIGSTOP)

    def action_resume(self) -> None:
        self._send_signal_to_selected("SIGCONT", signal.SIGCONT)

    def _send_signal_to_selected(self, sig_name: str, sig: signal.Signals) -> None:
        table = self.query_one("#connections-table", ConnectionsTable)
        conn = table.get_selected_connection()
        if not conn or not conn.pid:
            self.notify("Aucun processus sélectionné", severity="warning", timeout=3)
            return

        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                try:
                    import os
                    os.kill(conn.pid, sig)
                    self.notify(
                        f"{sig_name} envoyé à PID {conn.pid} ({conn.process_name})",
                        timeout=3,
                    )
                    logger.info("%s envoyé à PID %d", sig_name, conn.pid)
                    self._trigger_refresh()
                except ProcessLookupError:
                    self.notify("Processus introuvable", severity="error", timeout=3)
                except PermissionError:
                    self.notify("Permission refusée", severity="error", timeout=3)
                except Exception:
                    logger.exception("Erreur lors de l'envoi de %s à %d", sig_name, conn.pid)
                    self.notify("Erreur lors de l'envoi du signal", severity="error", timeout=3)

        self.push_screen(
            ConfirmDialog(
                f"Envoyer {sig_name}",
                f"Envoyer {sig_name} au processus [bold]{conn.process_name}[/bold] (PID {conn.pid}) ?",
            ),
            on_confirm,
        )

    def action_service_menu(self) -> None:
        table = self.query_one("#connections-table", ConnectionsTable)
        conn = table.get_selected_connection()
        if not conn or not conn.pid:
            self.notify("Aucun processus sélectionné", severity="warning", timeout=3)
            return

        svc_name = self._service_map.get(conn.pid) or get_service_for_pid(conn.pid)
        if not svc_name:
            self.notify("Aucun service systemd associé", severity="warning", timeout=3)
            return

        def on_action(action: str | None) -> None:
            if not action:
                return
            if action == "logs":
                logs = get_service_logs(svc_name, lines=50)
                self.push_screen(LogScreen(svc_name, logs))
                return
            success, msg = service_action(svc_name, action)
            severity = "information" if success else "error"
            self.notify(f"{svc_name}: {msg[:200]}", severity=severity, timeout=5)
            if success:
                self._trigger_refresh()

        self.push_screen(ServiceDialog(svc_name), on_action)

    def action_block_ports(self) -> None:
        if not is_firewall_available():
            self.notify("Aucun backend firewall disponible (iptables/nft/ufw/firewalld)", severity="error", timeout=4)
            return

        table = self.query_one("#connections-table", ConnectionsTable)
        conn = table.get_selected_connection()
        prefill = str(conn.local_port) if conn and conn.local_port else ""

        def on_result(result: dict | None) -> None:
            if not result:
                return
            spec = result.get("spec", "").strip()
            if not spec:
                self.notify("Aucun port saisi", severity="warning", timeout=3)
                return
            action = result["action"]
            protocol = result["protocol"]
            direction = result["direction"]

            if action == "block":
                ok, msg = block_ports(spec, protocol, direction)
            else:
                ok, msg = unblock_ports(spec, protocol, direction)

            severity = "information" if ok else "error"
            verb = "Bloqué" if action == "block" else "Débloqué"
            self.notify(
                f"{verb} [{spec}] proto={protocol} dir={direction}: {msg}",
                severity=severity,
                timeout=6,
            )
            logger.info("%s ports %s proto=%s dir=%s: %s", verb, spec, protocol, direction, msg)
            if ok:
                self._trigger_refresh()

        self.push_screen(BlockPortDialog(prefill=prefill), on_result)

    def action_history(self) -> None:
        """Affiche l'historique des événements réseau."""
        def on_result(result) -> None:
            if result == "clear":
                self._watcher._history.clear()

        self.push_screen(HistoryScreen(self._watcher.history), on_result)

    def action_stats(self) -> None:
        """Affiche les statistiques globales."""
        self.push_screen(StatsScreen(
            connections=self._all_connections,
            cpu_map=self._cpu_map,
            memory_map=self._memory_map,
            service_map=self._service_map,
            bw_stats=self._bw_stats,
        ))

    def action_alerts(self) -> None:
        """Affiche les alertes actives et les règles."""
        self.push_screen(AlertsScreen(self._active_alerts, self._alert_engine))

    def action_baseline(self) -> None:
        """Sauvegarde la baseline ou affiche les déviations si elle existe."""
        if self._baseline is None:
            save_baseline(self._all_connections)
            result = load_baseline()
            if result:
                self._baseline_ts, self._baseline = result
            self.notify(
                f"Baseline sauvegardée ({len(self._all_connections)} entrées)",
                timeout=4,
            )
            self._trigger_refresh()
        else:
            new_conns, gone = get_deviations(self._all_connections, self._baseline)
            msg_parts = []
            if new_conns:
                msg_parts.append(f"{len(new_conns)} nouveau(x)")
            if gone:
                msg_parts.append(f"{len(gone)} disparu(s)")
            if msg_parts:
                self.notify(
                    f"Déviations baseline : {', '.join(msg_parts)} — entrées en vert dans la table",
                    severity="warning",
                    timeout=6,
                )
            else:
                self.notify("Aucune déviation par rapport à la baseline", timeout=3)

    def action_saved_filters(self) -> None:
        """Affiche les filtres sauvegardés et permet d'en appliquer un."""
        filters = self._filter_store.filters
        if not filters:
            # Proposer de sauvegarder le filtre courant
            if self._search_filter:
                def on_name(name: str | None) -> None:
                    if name:
                        self._filter_store.add(name, self._search_filter)
                        self.notify(f"Filtre '{name}' sauvegardé", timeout=3)

                from ui.dialogs import SearchDialog as _SD

                class _NameDialog(_SD):
                    pass

                self.push_screen(_NameDialog(), on_name)
            else:
                self.notify("Aucun filtre sauvegardé — cherchez d'abord avec /", timeout=3)
            return

        # Construire le message avec les filtres disponibles
        lines = ["Filtres sauvegardés :"]
        for i, f in enumerate(filters):
            lines.append(f"  [{i + 1}] {f.name}  →  '{f.query}'")
        self.notify("\n".join(lines), timeout=8)

        # Appliquer le premier filtre si un seul, sinon notifier
        if len(filters) == 1:
            self._search_filter = filters[0].query
            self._trigger_refresh()
            self.notify(f"Filtre '{filters[0].name}' appliqué", timeout=3)

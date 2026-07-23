"""Tableau principal des connexions réseau."""

from textual.widgets import DataTable
from textual.message import Message

from core.ports import ConnectionInfo
from utils.formatter import (
    format_port, format_address, format_pid,
    format_process_name, format_username, format_cpu, format_memory,
)
from utils.colors import STATE_COLORS, PROTOCOL_COLORS
from rich.text import Text


COLUMNS = [
    ("Port", 7),
    ("Proto", 5),
    ("État", 12),
    ("Adresse", 18),
    ("Distant", 22),
    ("PID", 8),
    ("Processus", 18),
    ("Utilisateur", 12),
    ("CPU%", 6),
    ("RAM", 9),
    ("Trend", 10),
    ("Service", 20),
    ("Uptime", 12),
]


def _color_cpu(pct: float) -> Text:
    if pct >= 50:
        return Text(f"{pct:.1f}%", style="bold red")
    if pct >= 20:
        return Text(f"{pct:.1f}%", style="yellow")
    if pct > 0.1:
        return Text(f"{pct:.1f}%", style="green")
    return Text("0.0%", style="dim")


def _color_mem(pct: float) -> Text:
    if pct >= 50:
        return Text(f"{pct:.1f}%", style="bold red")
    if pct >= 20:
        return Text(f"{pct:.1f}%", style="yellow")
    if pct > 0:
        return Text(f"{pct:.1f}%", style="cyan")
    return Text("-", style="dim")


class ConnectionsTable(DataTable):
    """Table interactive des connexions réseau."""

    DEFAULT_CSS = """
    ConnectionsTable {
        height: 1fr;
    }
    """

    class RowSelected(Message):
        """Émis quand une ligne est sélectionnée."""
        def __init__(self, connection: ConnectionInfo) -> None:
            super().__init__()
            self.connection = connection

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._connections: list[ConnectionInfo] = []
        self._sort_key: str = "Port"
        self._sort_reverse: bool = False
        self._cpu_map: dict[int, float] = {}
        self._memory_map: dict[int, float] = {}
        self._service_map: dict[int, str] = {}
        self._uptime_map: dict[int, str] = {}
        self._sparkline_map: dict[int, str] = {}
        self._dns_map: dict[str, str] = {}
        self._baseline_pids: set[tuple] = set()  # clés (proto, addr, port, proc)

    def on_mount(self) -> None:
        """Configure les colonnes au montage."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        for label, width in COLUMNS:
            self.add_column(label, key=label, width=width)

    def update_data(
        self,
        connections: list[ConnectionInfo],
        cpu_map: dict[int, float] | None = None,
        memory_map: dict[int, float] | None = None,
        service_map: dict[int, str] | None = None,
        uptime_map: dict[int, str] | None = None,
        sparkline_map: dict[int, str] | None = None,
        dns_map: dict[str, str] | None = None,
        baseline_keys: set[tuple] | None = None,
    ) -> None:
        """Met à jour le contenu de la table."""
        self._connections = connections
        self._cpu_map = cpu_map or {}
        self._memory_map = memory_map or {}
        self._service_map = service_map or {}
        self._uptime_map = uptime_map or {}
        self._sparkline_map = sparkline_map or {}
        self._dns_map = dns_map or {}
        self._baseline_keys = baseline_keys or set()
        self._apply_sort()

        saved_row = self.cursor_row
        self.clear()
        for conn in self._connections:
            pid_val = conn.pid or 0
            cpu = self._cpu_map.get(pid_val, 0.0)
            mem = self._memory_map.get(pid_val, 0.0)
            service = self._service_map.get(pid_val, "-")
            uptime = self._uptime_map.get(pid_val, "-")
            spark = self._sparkline_map.get(pid_val, "")

            state_color = STATE_COLORS.get(conn.status, "white")
            proto_color = PROTOCOL_COLORS.get(conn.protocol, "white")

            # Affichage distant : hostname si résolu, sinon IP
            remote_display = ""
            if conn.remote_addr:
                hostname = self._dns_map.get(conn.remote_addr)
                if hostname:
                    remote_display = f"{hostname}:{conn.remote_port}"
                else:
                    remote_display = conn.remote_endpoint

            # Surlignage baseline : nouveau si absent de la baseline
            conn_key = (conn.protocol, conn.local_addr, conn.local_port, conn.process_name)
            is_new = bool(self._baseline_keys) and conn_key not in self._baseline_keys
            addr_style = "bold green" if is_new else "dim"

            row = [
                Text(format_port(conn.local_port), style="bold white"),
                Text(conn.protocol, style=proto_color),
                Text(conn.status, style=state_color),
                Text(format_address(conn.local_addr), style=addr_style),
                Text(remote_display, style="dim"),
                Text(format_pid(conn.pid), style="cyan"),
                Text(format_process_name(conn.process_name), style="white"),
                Text(format_username(conn.username), style="dim cyan"),
                _color_cpu(cpu),
                _color_mem(mem),
                Text(spark, style="dim cyan"),
                Text(format_process_name(service, 18), style="dim"),
                Text(uptime, style="dim"),
            ]
            self.add_row(*row, key=str(id(conn)))

        if saved_row < len(self._connections):
            self.move_cursor(row=saved_row)

    def _apply_sort(self) -> None:
        """Applique le tri courant aux connexions."""
        sort_funcs = {
            "Port": lambda c: c.local_port,
            "Proto": lambda c: c.protocol,
            "État": lambda c: c.status,
            "Adresse": lambda c: c.local_addr,
            "Distant": lambda c: c.remote_addr,
            "PID": lambda c: c.pid or 0,
            "Processus": lambda c: c.process_name.lower(),
            "Utilisateur": lambda c: c.username.lower(),
            "CPU%": lambda c: self._cpu_map.get(c.pid or 0, 0.0),
            "RAM": lambda c: self._memory_map.get(c.pid or 0, 0.0),
            "Trend": lambda c: self._sparkline_map.get(c.pid or 0, ""),
            "Service": lambda c: self._service_map.get(c.pid or 0, "").lower(),
            "Uptime": lambda c: self._uptime_map.get(c.pid or 0, ""),
        }
        func = sort_funcs.get(self._sort_key, lambda c: c.local_port)
        self._connections.sort(key=func, reverse=self._sort_reverse)

    def set_sort(self, column: str, reverse: bool = False) -> None:
        """Définit la colonne et le sens du tri."""
        self._sort_key = column
        self._sort_reverse = reverse

    def get_selected_connection(self) -> ConnectionInfo | None:
        """Retourne la connexion de la ligne sélectionnée."""
        row_idx = self.cursor_row
        if 0 <= row_idx < len(self._connections):
            return self._connections[row_idx]
        return None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Propagation de l'événement de sélection."""
        conn = self.get_selected_connection()
        if conn:
            self.post_message(self.RowSelected(conn))

"""Écran de statistiques globales."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from core.ports import ConnectionInfo
from core.bandwidth import InterfaceStat
from utils.helpers import format_bytes


def _bar(value: float, max_val: float, width: int = 20) -> str:
    if max_val <= 0:
        return "░" * width
    filled = int(value / max_val * width)
    return "█" * filled + "░" * (width - filled)


def _render_stats(
    connections: list[ConnectionInfo],
    cpu_map: dict[int, float],
    memory_map: dict[int, float],
    service_map: dict[int, str],
    bw_stats: list[InterfaceStat],
) -> str:
    lines: list[str] = []

    # --- Vue d'ensemble ---
    total = len(connections)
    listen = sum(1 for c in connections if c.status == "LISTEN")
    established = sum(1 for c in connections if c.status == "ESTABLISHED")
    by_proto: dict[str, int] = {}
    for c in connections:
        by_proto[c.protocol] = by_proto.get(c.protocol, 0) + 1

    lines.append("[bold cyan]── Vue d'ensemble ─────────────────────────────────────[/]")
    lines.append(
        f"  Total connexions  [bold white]{total}[/]    "
        f"LISTEN [bold green]{listen}[/]    "
        f"ESTABLISHED [bold yellow]{established}[/]"
    )
    proto_str = "  ".join(f"[dim]{p}[/] [white]{n}[/]" for p, n in sorted(by_proto.items()))
    lines.append(f"  Protocoles : {proto_str}")
    lines.append("")

    # --- Top 5 CPU ---
    lines.append("[bold cyan]── Top 5 processus par CPU ─────────────────────────────[/]")
    pid_cpu = sorted(
        ((pid, v) for pid, v in cpu_map.items() if v > 0),
        key=lambda x: x[1], reverse=True
    )[:5]
    if pid_cpu:
        max_cpu = max(v for _, v in pid_cpu) or 1.0
        for pid, cpu in pid_cpu:
            proc = next((c.process_name for c in connections if c.pid == pid), f"PID {pid}")
            bar = _bar(cpu, max_cpu)
            lines.append(f"  [cyan]{proc[:20]:<20}[/] [{bar}] [bold]{cpu:.1f}%[/]")
    else:
        lines.append("  [dim]Aucune donnée CPU (premier cycle)[/dim]")
    lines.append("")

    # --- Top 5 RAM ---
    lines.append("[bold cyan]── Top 5 processus par RAM ─────────────────────────────[/]")
    pid_mem = sorted(
        ((pid, v) for pid, v in memory_map.items() if v > 0),
        key=lambda x: x[1], reverse=True
    )[:5]
    if pid_mem:
        max_mem = max(v for _, v in pid_mem) or 1.0
        for pid, mem in pid_mem:
            proc = next((c.process_name for c in connections if c.pid == pid), f"PID {pid}")
            bar = _bar(mem, max_mem)
            lines.append(f"  [magenta]{proc[:20]:<20}[/] [{bar}] [bold]{mem:.1f}%[/]")
    else:
        lines.append("  [dim]Aucune donnée RAM[/dim]")
    lines.append("")

    # --- Top processus par nb connexions ---
    lines.append("[bold cyan]── Top processus par connexions ────────────────────────[/]")
    proc_count: dict[str, int] = {}
    for c in connections:
        key = f"{c.process_name or '?'} (PID {c.pid})"
        proc_count[key] = proc_count.get(key, 0) + 1
    top_procs = sorted(proc_count.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_procs:
        max_n = max(n for _, n in top_procs) or 1
        for name, n in top_procs:
            bar = _bar(n, max_n)
            lines.append(f"  [white]{name[:30]:<30}[/] [{bar}] [bold]{n}[/]")
    lines.append("")

    # --- Bande passante ---
    if bw_stats:
        lines.append("[bold cyan]── Bande passante par interface ────────────────────────[/]")
        for s in bw_stats[:6]:
            recv_str = f"↓ {format_bytes(int(s.recv_rate))}/s"
            sent_str = f"↑ {format_bytes(int(s.sent_rate))}/s"
            lines.append(
                f"  [bold white]{s.name:<12}[/]  "
                f"[green]{recv_str:<18}[/]  [yellow]{sent_str}[/]"
            )
    else:
        lines.append("[bold cyan]── Bande passante ──────────────────────────────────────[/]")
        lines.append("  [dim]Aucune interface active[/dim]")

    return "\n".join(lines)


class StatsScreen(Screen):
    """Vue tableau de bord des statistiques globales."""

    BINDINGS = [
        ("escape", "close", "Fermer"),
        ("q", "close", "Fermer"),
    ]

    DEFAULT_CSS = """
    StatsScreen {
        align: center middle;
    }

    #stats-outer {
        width: 88%;
        height: 88%;
        border: round $success;
        background: $boost;
    }

    #stats-title {
        text-align: center;
        text-style: bold;
        color: $success;
        height: 3;
        padding: 1 0;
        border-bottom: solid $success-darken-2;
    }

    #stats-scroll {
        height: 1fr;
        padding: 1 2;
    }

    #stats-footer {
        height: 3;
        align: center middle;
        border-top: solid $success-darken-2;
    }
    """

    def __init__(
        self,
        connections: list[ConnectionInfo],
        cpu_map: dict[int, float],
        memory_map: dict[int, float],
        service_map: dict[int, str],
        bw_stats: list[InterfaceStat],
    ) -> None:
        super().__init__()
        self._content = _render_stats(connections, cpu_map, memory_map, service_map, bw_stats)

    def compose(self) -> ComposeResult:
        with Vertical(id="stats-outer"):
            yield Label("Statistiques globales", id="stats-title")
            with ScrollableContainer(id="stats-scroll"):
                yield Static(self._content)
            with Horizontal(id="stats-footer"):
                yield Button("Fermer  [Esc]", variant="success", id="btn-stats-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()

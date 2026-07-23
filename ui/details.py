"""Panneau de détails du processus sélectionné."""

import datetime

from textual.widgets import Static

from config import MAX_OPEN_FILES_DISPLAY, MAX_ENV_VARS_DISPLAY
from core.process import ProcessDetail
from utils.helpers import format_bytes, format_duration
from utils.colors import STATE_COLORS


_STATUS_STYLES = {
    "running":    "bold green",
    "sleeping":   "dim",
    "idle":       "dim",
    "disk-sleep": "yellow",
    "stopped":    "bold yellow",
    "zombie":     "bold red",
    "dead":       "red",
}

_SEP_WIDTH = 60


class ProcessDetailsPanel(Static):
    """Panneau affichant les détails complets d'un processus."""

    DEFAULT_CSS = """
    ProcessDetailsPanel {
        height: auto;
        max-height: 22;
        padding: 0 1;
        border-top: solid $primary;
        overflow-y: auto;
        background: $boost;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._detail: ProcessDetail | None = None

    def show_process(self, detail: ProcessDetail | None) -> None:
        """Met à jour l'affichage avec les détails d'un processus."""
        self._detail = detail
        if detail is None:
            self.update("[dim]Sélectionnez un processus pour voir les détails[/dim]")
            return

        status_style = _STATUS_STYLES.get(detail.status, "white")

        lines = [
            # Titre
            f"[bold white]{detail.name}[/]  "
            f"[dim]PID:[/] [bold yellow]{detail.pid}[/]  "
            f"[dim]PPID:[/] [dim]{detail.ppid}[/]",

            # Identité
            f"  [dim]Utilisateur:[/] [cyan]{detail.username}[/]  "
            f"[dim]Groupe:[/] [cyan]{detail.group}[/]  "
            f"[dim]Status:[/] [{status_style}]{detail.status}[/]  "
            f"[dim]Nice:[/] {detail.nice}",

            # Ressources
            f"  [dim]CPU:[/] {_color_pct(detail.cpu_percent)}  "
            f"[dim]RSS:[/] [magenta]{format_bytes(detail.memory_rss)}[/]  "
            f"[dim]VMS:[/] [dim magenta]{format_bytes(detail.memory_vms)}[/]  "
            f"[dim]Mém:[/] {_color_pct(detail.memory_percent)}  "
            f"[dim]Threads:[/] [white]{detail.num_threads}[/]",

            # Temps
            f"  [dim]Uptime:[/] [white]{detail.uptime_human}[/]  "
            f"[dim]Démarré:[/] [dim]{_format_create_time(detail.create_time)}[/]",

            # Chemins
            f"  [dim]Exe:[/]  [dim]{detail.exe_path or 'N/A'}[/]",
            f"  [dim]CWD:[/]  [dim]{detail.cwd or 'N/A'}[/]",
            f"  [dim]Cmd:[/]  [dim italic]{_truncate(detail.cmdline, 120)}[/]",
        ]

        # Connexions réseau
        lines.append(_section("Connexions", len(detail.connections) if detail.connections else None))
        if detail.connections:
            for c in detail.connections:
                lines.append(f"  [dim]{c}[/]")
        else:
            lines.append("  [dim]aucune[/]")

        # Fichiers ouverts
        shown_files = detail.open_files[:MAX_OPEN_FILES_DISPLAY]
        total_files = len(detail.open_files)
        label = f"Fichiers ouverts ({total_files}"
        if total_files > MAX_OPEN_FILES_DISPLAY:
            label += f", {MAX_OPEN_FILES_DISPLAY} affichés"
        label += ")"
        lines.append(_section(label))
        if shown_files:
            for f in shown_files:
                lines.append(f"  [dim]{f}[/]")
        else:
            lines.append("  [dim]aucun[/]")

        # Variables d'environnement
        shown_env = list(detail.environ.items())[:MAX_ENV_VARS_DISPLAY]
        total_env = len(detail.environ)
        label = f"Environnement ({total_env}"
        if total_env > MAX_ENV_VARS_DISPLAY:
            label += f", {MAX_ENV_VARS_DISPLAY} affichées"
        label += ")"
        lines.append(_section(label))
        if shown_env:
            for k, v in shown_env:
                lines.append(f"  [cyan]{k}[/]=[dim]{_truncate(v, 80)}[/]")
        else:
            lines.append("  [dim]aucune[/]")

        self.update("\n".join(lines))

    def clear_details(self) -> None:
        """Efface les détails affichés."""
        self._detail = None
        self.update("[dim]Sélectionnez un processus pour voir les détails[/dim]")


def _section(title: str, count: int | None = None) -> str:
    """Retourne un séparateur de section stylé."""
    label = f" {title} "
    dashes = "─" * max(0, _SEP_WIDTH - len(label) - 3)
    return f"[bold dim cyan]───{label}{dashes}[/]"


def _color_pct(pct: float) -> str:
    if pct >= 50:
        return f"[bold red]{pct:.1f}%[/]"
    if pct >= 20:
        return f"[yellow]{pct:.1f}%[/]"
    if pct > 0.1:
        return f"[green]{pct:.1f}%[/]"
    return "[dim]0.0%[/]"


def _format_create_time(ts: float) -> str:
    if ts <= 0:
        return "N/A"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _truncate(text: str, max_len: int = 100) -> str:
    if not text:
        return "N/A"
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."

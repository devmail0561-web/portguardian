"""En-tête avec statistiques système résumées."""

import psutil
from textual.reactive import reactive
from textual.widgets import Static

from utils.helpers import format_bytes


class SystemHeader(Static):
    """Barre d'en-tête affichant les statistiques système."""

    DEFAULT_CSS = """
SystemHeader {
    height: 1;
    background: $boost;
    padding: 0 1;
    color: $text-muted;
}
"""

    cpu_percent = reactive(0.0)
    memory_percent = reactive(0.0)
    memory_used = reactive(0)
    connections_count = reactive(0)
    listening_count = reactive(0)

    def render(self) -> str:
        mem_str = format_bytes(self.memory_used)

        if self.cpu_percent >= 80:
            cpu_style = "bold red"
        elif self.cpu_percent >= 50:
            cpu_style = "yellow"
        else:
            cpu_style = "bold green"

        if self.memory_percent >= 80:
            mem_style = "bold red"
        elif self.memory_percent >= 50:
            mem_style = "yellow"
        else:
            mem_style = "bold cyan"

        return (
            f" [dim]CPU[/]  [{cpu_style}]{self.cpu_percent:.1f}%[/]"
            f"  [dim]│[/]  [dim]RAM[/]  [{mem_style}]{self.memory_percent:.1f}%[/] [dim]({mem_str})[/]"
            f"  [dim]│[/]  [dim]Connexions[/]  [bold white]{self.connections_count}[/]"
            f"  [dim]│[/]  [dim]LISTEN[/]  [bold green]{self.listening_count}[/]"
        )

    def update_stats(self, connections_count: int, listening_count: int) -> None:
        """Met à jour les statistiques affichées."""
        self.cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        self.memory_percent = mem.percent
        self.memory_used = mem.used
        self.connections_count = connections_count
        self.listening_count = listening_count

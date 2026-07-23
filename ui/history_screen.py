"""Écran d'historique des événements réseau détectés par le watcher."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from core.watcher import NetworkEvent

_SEVERITY_STYLE = {
    "port_opened": "bold green",
    "port_closed": "bold yellow",
    "process_new": "cyan",
    "process_ended": "dim",
}

_ICONS = {
    "port_opened": "▲",
    "port_closed": "▼",
    "process_new": "+",
    "process_ended": "×",
}


def _format_event(event: NetworkEvent, index: int) -> str:
    style = _SEVERITY_STYLE.get(event.event_type, "white")
    icon = _ICONS.get(event.event_type, "•")
    etype = event.event_type.replace("_", " ").upper()
    return (
        f"[dim]{index + 1:>4}[/]  [{style}]{icon} {etype:<16}[/]  "
        f"[bold white]{event.protocol}:{event.port}[/]  "
        f"[cyan]{event.process_name or '?'}[/] "
        f"[dim](PID {event.pid})[/]  "
        f"[dim]{event.address}[/]"
    )


class HistoryScreen(Screen):
    """Affiche l'historique des événements réseau."""

    BINDINGS = [
        ("escape", "close", "Fermer"),
        ("q", "close", "Fermer"),
        ("c", "clear", "Vider"),
    ]

    DEFAULT_CSS = """
    HistoryScreen {
        align: center middle;
    }

    #hist-outer {
        width: 92%;
        height: 85%;
        border: round $primary;
        background: $boost;
    }

    #hist-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        height: 3;
        padding: 1 0;
        border-bottom: solid $primary-darken-3;
    }

    #hist-legend {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        background: $panel;
    }

    #hist-scroll {
        height: 1fr;
        padding: 0 1;
    }

    #hist-footer {
        height: 3;
        align: center middle;
        border-top: solid $primary-darken-3;
    }

    #hist-footer Button {
        margin: 0 1;
        min-width: 14;
    }
    """

    def __init__(self, events: list[NetworkEvent]) -> None:
        super().__init__()
        self._events = list(reversed(events))  # plus récent en premier

    def compose(self) -> ComposeResult:
        with Vertical(id="hist-outer"):
            yield Label(
                f"Historique des événements réseau  [dim]({len(self._events)} entrées)[/dim]",
                id="hist-title",
            )
            yield Static(
                "[dim]▲ PORT OUVERT  ▼ PORT FERMÉ  + PROCESSUS NEW  × PROCESSUS FIN[/dim]",
                id="hist-legend",
            )
            with ScrollableContainer(id="hist-scroll"):
                if self._events:
                    content = "\n".join(
                        _format_event(e, i) for i, e in enumerate(self._events)
                    )
                else:
                    content = "[dim]Aucun événement enregistré.[/dim]"
                yield Static(content, id="hist-content")
            with Horizontal(id="hist-footer"):
                yield Button("Vider  [c]", variant="warning", id="btn-hist-clear")
                yield Button("Fermer  [Esc]", variant="primary", id="btn-hist-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-hist-clear":
            self.action_clear()
        else:
            self.dismiss()

    def action_close(self) -> None:
        self.dismiss()

    def action_clear(self) -> None:
        self._events = []
        try:
            self.query_one("#hist-content", Static).update("[dim]Historique vidé.[/dim]")
            self.query_one("#hist-title", Label).update(
                "Historique des événements réseau  [dim](0 entrées)[/dim]"
            )
        except Exception:
            pass
        self.dismiss("clear")

"""Dashboard principal assemblant tous les composants UI."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ui.header import SystemHeader
from ui.tables import ConnectionsTable
from ui.details import ProcessDetailsPanel
from ui.footer import KeyBindingsFooter


class Dashboard(Vertical):
    """Conteneur principal du dashboard."""

    DEFAULT_CSS = """
    Dashboard {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield SystemHeader(id="system-header")
        yield ConnectionsTable(id="connections-table")
        yield ProcessDetailsPanel(id="process-details")
        yield KeyBindingsFooter(id="key-bindings")

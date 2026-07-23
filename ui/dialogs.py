"""Boîtes de dialogue (confirmation, recherche, tri, export, blocage)."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, RadioSet, RadioButton


class ConfirmDialog(ModalScreen[bool]):
    """Dialogue de confirmation avant action destructive."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }

    #confirm-dialog-box {
        width: 62;
        height: auto;
        padding: 1 2;
        border: round $error;
        background: $boost;
    }

    #confirm-title {
        text-align: center;
        text-style: bold;
        color: $error;
        padding: 0 0 1 0;
    }

    #confirm-message {
        margin-bottom: 1;
        padding: 0 1;
    }

    #confirm-buttons {
        align: center middle;
        height: 3;
    }

    #confirm-buttons Button {
        margin: 0 2;
        min-width: 14;
    }
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog-box"):
            yield Label(self._title, id="confirm-title")
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirmer", variant="error", id="btn-confirm")
                yield Button("Annuler", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class SearchDialog(ModalScreen[str | None]):
    """Dialogue de recherche."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    SearchDialog {
        align: center middle;
    }

    #search-box {
        width: 62;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $boost;
    }

    #search-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }

    #search-input {
        margin-bottom: 1;
    }

    #search-buttons {
        align: center middle;
        height: 3;
    }

    #search-buttons Button {
        margin: 0 2;
        min-width: 14;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="search-box"):
            yield Label("Rechercher (port, PID, nom, user, protocole)", id="search-title")
            yield Input(placeholder="Tapez votre recherche...", id="search-input")
            with Horizontal(id="search-buttons"):
                yield Button("Rechercher", variant="primary", id="btn-search")
                yield Button("Annuler", variant="default", id="btn-search-cancel")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-search":
            value = self.query_one("#search-input", Input).value
            self.dismiss(value)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SortDialog(ModalScreen):
    """Dialogue de sélection du tri avec sens (ascendant/descendant)."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    SortDialog {
        align: center middle;
    }

    #sort-box {
        width: 52;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $boost;
    }

    #sort-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }

    #sort-reverse-row {
        height: auto;
        margin-top: 1;
        align: left middle;
    }

    #sort-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    #sort-buttons Button {
        margin: 0 2;
        min-width: 14;
    }
    """

    SORT_OPTIONS = [
        ("Port", "Port"),
        ("PID", "PID"),
        ("CPU%", "CPU%"),
        ("RAM", "RAM"),
        ("Processus", "Processus"),
        ("Utilisateur", "Utilisateur"),
        ("État", "État"),
        ("Proto", "Proto"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="sort-box"):
            yield Label("Trier par :", id="sort-title")
            yield Select(
                [(label, value) for label, value in self.SORT_OPTIONS],
                id="sort-select",
                value="Port",
            )
            with Horizontal(id="sort-reverse-row"):
                yield Checkbox("Ordre décroissant", id="sort-reverse")
            with Horizontal(id="sort-buttons"):
                yield Button("Appliquer", variant="primary", id="btn-sort-apply")
                yield Button("Annuler", variant="default", id="btn-sort-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-sort-apply":
            value = self.query_one("#sort-select", Select).value
            reverse = self.query_one("#sort-reverse", Checkbox).value
            if value:
                self.dismiss((str(value), bool(reverse)))
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ExportDialog(ModalScreen[str]):
    """Dialogue de sélection du format d'export."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    ExportDialog {
        align: center middle;
    }

    #export-box {
        width: 52;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $boost;
    }

    #export-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }

    #export-buttons {
        align: center middle;
        height: auto;
        margin-top: 1;
    }

    #export-buttons Button {
        margin: 0 1;
        min-width: 10;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="export-box"):
            yield Label("Exporter en :", id="export-title")
            with Horizontal(id="export-buttons"):
                yield Button("CSV", variant="primary", id="btn-csv")
                yield Button("JSON", variant="primary", id="btn-json")
                yield Button("TXT", variant="primary", id="btn-txt")
                yield Button("Annuler", variant="default", id="btn-cancel-export")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_map = {
            "btn-csv": "csv",
            "btn-json": "json",
            "btn-txt": "txt",
            "btn-cancel-export": "",
        }
        result = button_map.get(event.button.id, "")
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss("")


class ServiceDialog(ModalScreen[str]):
    """Dialogue d'actions sur un service systemd."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    ServiceDialog {
        align: center middle;
    }

    #service-box {
        width: 58;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $boost;
    }

    #service-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }

    #service-buttons {
        align: center middle;
        height: auto;
        margin-bottom: 1;
    }

    #service-buttons Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def compose(self) -> ComposeResult:
        with Vertical(id="service-box"):
            yield Label(f"Service : {self._service_name}", id="service-title")
            with Horizontal(id="service-buttons"):
                yield Button("Start", variant="success", id="btn-svc-start")
                yield Button("Stop", variant="error", id="btn-svc-stop")
                yield Button("Restart", variant="warning", id="btn-svc-restart")
            with Horizontal():
                yield Button("Status", variant="primary", id="btn-svc-status")
                yield Button("Logs", variant="primary", id="btn-svc-logs")
                yield Button("Annuler", variant="default", id="btn-svc-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action_map = {
            "btn-svc-start": "start",
            "btn-svc-stop": "stop",
            "btn-svc-restart": "restart",
            "btn-svc-status": "status",
            "btn-svc-logs": "logs",
            "btn-svc-cancel": "",
        }
        result = action_map.get(event.button.id, "")
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss("")


class BlockPortDialog(ModalScreen[dict | None]):
    """Dialogue de blocage/déblocage de ports via iptables."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    BlockPortDialog {
        align: center middle;
    }

    #block-box {
        width: 66;
        height: auto;
        padding: 1 2;
        border: round $error;
        background: $boost;
    }

    #block-title {
        text-align: center;
        text-style: bold;
        color: $error;
        padding: 0 0 1 0;
    }

    #block-hint {
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    #block-input {
        margin-bottom: 1;
    }

    .block-row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }

    #block-buttons {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    #block-buttons Button {
        margin: 0 1;
        min-width: 14;
    }
    """

    def __init__(self, prefill: str = "") -> None:
        super().__init__()
        self._prefill = prefill

    def compose(self) -> ComposeResult:
        with Vertical(id="block-box"):
            yield Label("Bloquer / Débloquer des ports", id="block-title")
            yield Static(
                "Formats : [bold]80[/bold]  [bold]80,443[/bold]  "
                "[bold]8000-8100[/bold]  [bold]80,443,8000-8010[/bold]",
                id="block-hint",
            )
            yield Input(
                value=self._prefill,
                placeholder="ex: 80  ou  80,443  ou  8000-8100",
                id="block-input",
            )
            with Horizontal(classes="block-row"):
                yield Label("Protocole : ")
                with RadioSet(id="block-proto"):
                    yield RadioButton("TCP", value=True, id="proto-tcp")
                    yield RadioButton("UDP", id="proto-udp")
                    yield RadioButton("TCP+UDP", id="proto-both")
            with Horizontal(classes="block-row"):
                yield Label("Direction : ")
                with RadioSet(id="block-dir"):
                    yield RadioButton("Entrant", value=True, id="dir-in")
                    yield RadioButton("Sortant", id="dir-out")
                    yield RadioButton("Les deux", id="dir-both")
            with Horizontal(id="block-buttons"):
                yield Button("Bloquer", variant="error", id="btn-block")
                yield Button("Débloquer", variant="warning", id="btn-unblock")
                yield Button("Annuler", variant="default", id="btn-block-cancel")

    def on_mount(self) -> None:
        self.query_one("#block-input", Input).focus()

    def _get_values(self) -> dict:
        spec = self.query_one("#block-input", Input).value.strip()

        proto_map = {"proto-tcp": "tcp", "proto-udp": "udp", "proto-both": "both"}
        proto = "tcp"
        for radio_id, val in proto_map.items():
            try:
                if self.query_one(f"#{radio_id}", RadioButton).value:
                    proto = val
                    break
            except Exception:
                pass

        dir_map = {"dir-in": "in", "dir-out": "out", "dir-both": "both"}
        direction = "in"
        for radio_id, val in dir_map.items():
            try:
                if self.query_one(f"#{radio_id}", RadioButton).value:
                    direction = val
                    break
            except Exception:
                pass

        return {"spec": spec, "protocol": proto, "direction": direction}

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-block":
            values = self._get_values()
            values["action"] = "block"
            self.dismiss(values)
        elif event.button.id == "btn-unblock":
            values = self._get_values()
            values["action"] = "unblock"
            self.dismiss(values)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class LogScreen(Screen):
    """Écran dédié à l'affichage des logs d'un service systemd."""

    BINDINGS = [
        ("escape", "close_log", "Fermer"),
        ("q", "close_log", "Fermer"),
    ]

    DEFAULT_CSS = """
    LogScreen {
        align: center middle;
    }

    #log-outer {
        width: 90%;
        height: 80%;
        border: round $primary;
        background: $boost;
        padding: 0 1;
    }

    #log-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1 0;
        height: 3;
    }

    #log-scroll {
        height: 1fr;
        border-top: solid $primary-darken-3;
    }

    #log-content {
        padding: 1;
    }

    #log-footer {
        height: 3;
        align: center middle;
        border-top: solid $primary-darken-3;
    }
    """

    def __init__(self, service_name: str, log_content: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._log_content = log_content

    def compose(self) -> ComposeResult:
        with Vertical(id="log-outer"):
            yield Label(f"Logs : {self._service_name}", id="log-title")
            with ScrollableContainer(id="log-scroll"):
                yield Static(self._log_content or "(aucun log)", id="log-content")
            with Horizontal(id="log-footer"):
                yield Button("Fermer  [Esc]", variant="primary", id="btn-log-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_close_log(self) -> None:
        self.dismiss()

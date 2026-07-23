"""Écran de gestion et d'affichage des alertes."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import Screen, ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from core.alerts import Alert, AlertRule, AlertEngine

_SEV_STYLE = {
    "critical": "bold red",
    "warning": "bold yellow",
    "info": "cyan",
}

_SEV_ICON = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


def _format_alert(a: Alert, idx: int) -> str:
    style = _SEV_STYLE.get(a.severity, "white")
    icon = _SEV_ICON.get(a.severity, "•")
    return (
        f"[dim]{idx + 1:>3}[/]  [{style}]{icon} {a.severity.upper():<9}[/]  "
        f"[bold white]{a.rule_name}[/]  —  {a.message}"
    )


class AddRuleDialog(ModalScreen):
    """Dialogue de création d'une règle d'alerte."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    DEFAULT_CSS = """
    AddRuleDialog { align: center middle; }
    #rule-box {
        width: 70;
        height: auto;
        padding: 1 2;
        border: round $warning;
        background: $boost;
    }
    #rule-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        padding: 0 0 1 0;
    }
    .rule-row { height: 3; margin-bottom: 1; }
    #rule-btns { align: center middle; height: 3; margin-top: 1; }
    #rule-btns Button { margin: 0 1; min-width: 14; }
    """

    SEVERITY_OPTIONS = [("critical", "critical"), ("warning", "warning"), ("info", "info")]

    def compose(self) -> ComposeResult:
        with Vertical(id="rule-box"):
            yield Label("Nouvelle règle d'alerte", id="rule-title")
            yield Input(placeholder="Nom de la règle", id="rule-name")
            yield Select(self.SEVERITY_OPTIONS, value="warning", id="rule-sev", prompt="Sévérité")
            yield Input(placeholder="Port (ex: 22) — laisser vide = tous", id="rule-port")
            yield Input(placeholder="Processus exact (ex: sshd) ou *substr", id="rule-process")
            yield Input(placeholder="Processus interdit (process_not)", id="rule-process-not")
            yield Input(placeholder="Utilisateur (ex: root)", id="rule-user")
            with Horizontal(id="rule-btns"):
                yield Button("Créer", variant="warning", id="btn-rule-create")
                yield Button("Annuler", variant="default", id="btn-rule-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-rule-create":
            name = self.query_one("#rule-name", Input).value.strip()
            if not name:
                return
            sev = str(self.query_one("#rule-sev", Select).value or "warning")
            port_str = self.query_one("#rule-port", Input).value.strip()
            process = self.query_one("#rule-process", Input).value.strip() or None
            process_not = self.query_one("#rule-process-not", Input).value.strip() or None
            user = self.query_one("#rule-user", Input).value.strip() or None
            port = None
            if port_str:
                try:
                    port = int(port_str)
                except ValueError:
                    return
            rule = AlertRule(
                name=name, severity=sev,
                port=port, process=process, process_not=process_not, user=user,
            )
            self.dismiss(rule)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class AlertsScreen(Screen):
    """Vue des alertes actives et gestion des règles."""

    BINDINGS = [
        ("escape", "close", "Fermer"),
        ("q", "close", "Fermer"),
        ("n", "new_rule", "Nouvelle règle"),
    ]

    DEFAULT_CSS = """
    AlertsScreen { align: center middle; }

    #alerts-outer {
        width: 92%;
        height: 88%;
        border: round $error;
        background: $boost;
    }

    #alerts-title {
        text-align: center;
        text-style: bold;
        color: $error;
        height: 3;
        padding: 1 0;
        border-bottom: solid $error-darken-2;
    }

    #alerts-section-title {
        padding: 0 2;
        text-style: bold;
        color: $warning;
        height: 2;
        background: $panel;
    }

    #alerts-scroll {
        height: 1fr;
        padding: 0 1;
        border-bottom: solid $error-darken-2;
    }

    #rules-scroll {
        height: 12;
        padding: 0 1;
    }

    #alerts-footer {
        height: 3;
        align: center middle;
        border-top: solid $error-darken-2;
    }

    #alerts-footer Button { margin: 0 1; min-width: 16; }
    """

    def __init__(self, alerts: list[Alert], engine: AlertEngine) -> None:
        super().__init__()
        self._alerts = alerts
        self._engine = engine

    def compose(self) -> ComposeResult:
        with Vertical(id="alerts-outer"):
            yield Label(
                f"Alertes actives  [dim]({len(self._alerts)})[/dim]",
                id="alerts-title",
            )
            with ScrollableContainer(id="alerts-scroll"):
                if self._alerts:
                    content = "\n".join(_format_alert(a, i) for i, a in enumerate(self._alerts))
                else:
                    content = "[dim]Aucune alerte — tout est normal.[/dim]"
                yield Static(content, id="alerts-content")
            yield Static("Règles configurées", id="alerts-section-title")
            with ScrollableContainer(id="rules-scroll"):
                yield Static(self._render_rules(), id="rules-content")
            with Horizontal(id="alerts-footer"):
                yield Button("+ Règle  [n]", variant="warning", id="btn-add-rule")
                yield Button("Fermer  [Esc]", variant="primary", id="btn-alerts-close")

    def _render_rules(self) -> str:
        rules = self._engine.rules
        if not rules:
            return "[dim]Aucune règle définie.[/dim]"
        lines = []
        for i, r in enumerate(rules):
            style = _SEV_STYLE.get(r.severity, "white")
            conds = []
            if r.port:
                conds.append(f"port={r.port}")
            if r.port_lt:
                conds.append(f"port<{r.port_lt}")
            if r.process:
                conds.append(f"process={r.process}")
            if r.process_not:
                conds.append(f"process≠{r.process_not}")
            if r.user:
                conds.append(f"user={r.user}")
            if r.user_not:
                conds.append(f"user≠{r.user_not}")
            cond_str = "  ".join(conds) or "toujours"
            lines.append(
                f"[dim]{i + 1:>2}[/]  [{style}]{r.severity:<9}[/]  "
                f"[bold]{r.name}[/]  [dim]{cond_str}[/]"
            )
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add-rule":
            self.action_new_rule()
        else:
            self.dismiss()

    def action_close(self) -> None:
        self.dismiss()

    def action_new_rule(self) -> None:
        def on_result(rule: AlertRule | None) -> None:
            if rule:
                self._engine.add_rule(rule)
                self.query_one("#rules-content", Static).update(self._render_rules())
                self.notify(f"Règle '{rule.name}' ajoutée", timeout=3)

        self.app.push_screen(AddRuleDialog(), on_result)

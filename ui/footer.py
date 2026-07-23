"""Pied de page avec raccourcis clavier."""

from textual.widgets import Static


class KeyBindingsFooter(Static):
    """Barre inférieure affichant les raccourcis clavier."""

    DEFAULT_CSS = """
    KeyBindingsFooter {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def render(self) -> str:
        bindings = [
            ("q", "Quitter"),
            ("r", "Rafraîchir"),
            ("/", "Chercher"),
            ("s", "Trier"),
            ("e", "Exporter"),
            ("h", "Historique"),
            ("t", "Stats"),
            ("A", "Alertes"),
            ("B", "Baseline"),
            ("f", "Filtres"),
            ("k/K", "TERM/KILL"),
            ("S", "Service"),
            ("b", "Bloquer"),
            ("Esc", "Fermer"),
            ("^P", "Screenshot"),
        ]
        parts = [
            f"[bold yellow]{key}[/][dim white]:{label}[/]"
            for key, label in bindings
        ]
        return "  ".join(parts)

"""Icônes Unicode pour l'interface."""

# États de connexion
STATE_ICONS: dict[str, str] = {
    "LISTEN": "●",
    "ESTABLISHED": "⇄",
    "TIME_WAIT": "◷",
    "CLOSE_WAIT": "◶",
    "SYN_SENT": "→",
    "SYN_RECV": "←",
    "FIN_WAIT1": "↓",
    "FIN_WAIT2": "↓",
    "LAST_ACK": "✕",
    "CLOSING": "✕",
    "NONE": "○",
}

# Services
SERVICE_ICONS: dict[str, str] = {
    "active": "●",
    "inactive": "○",
    "failed": "✕",
    "activating": "◌",
    "deactivating": "◌",
}

# Général
ICON_PORT = "⚡"
ICON_PROCESS = "⚙"
ICON_SERVICE = "◆"
ICON_NETWORK = "⇌"
ICON_WARNING = "⚠"
ICON_ERROR = "✕"
ICON_OK = "✓"
ICON_SEARCH = "🔍"
ICON_EXPORT = "📁"


def state_icon(state: str) -> str:
    """Retourne l'icône correspondant à un état de connexion."""
    return STATE_ICONS.get(state, "○")


def service_icon(state: str) -> str:
    """Retourne l'icône correspondant à un état de service."""
    return SERVICE_ICONS.get(state, "○")

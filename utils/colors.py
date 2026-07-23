"""Palette de couleurs pour l'interface."""

# États de connexion
STATE_COLORS: dict[str, str] = {
    "LISTEN": "green",
    "ESTABLISHED": "cyan",
    "TIME_WAIT": "yellow",
    "CLOSE_WAIT": "dark_orange",
    "SYN_SENT": "magenta",
    "SYN_RECV": "magenta",
    "FIN_WAIT1": "yellow",
    "FIN_WAIT2": "yellow",
    "LAST_ACK": "red",
    "CLOSING": "red",
    "NONE": "dim",
}

# Services systemd
SERVICE_STATE_COLORS: dict[str, str] = {
    "active": "green",
    "inactive": "dim",
    "failed": "red",
    "activating": "yellow",
    "deactivating": "yellow",
}

# Protocoles
PROTOCOL_COLORS: dict[str, str] = {
    "tcp": "green",
    "tcp6": "bright_green",
    "udp": "blue",
    "udp6": "bright_blue",
    "unix": "magenta",
}

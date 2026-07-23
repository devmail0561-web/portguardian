"""Configuration centralisée de PortGuardian."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Intervalles de rafraîchissement (secondes)
REFRESH_INTERVAL: float = 2.0
WATCHER_INTERVAL: float = 1.0

# Chemins applicatifs
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
LOG_FILE = LOG_DIR / "application.log"

# Chemins utilisateur (XDG)
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "portguardian"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "portguardian"
RULES_FILE = CONFIG_DIR / "rules.json"
BASELINE_FILE = DATA_DIR / "baseline.json"
FILTERS_FILE = CONFIG_DIR / "filters.json"

# Limites
MAX_ENV_VARS_DISPLAY: int = 50
MAX_OPEN_FILES_DISPLAY: int = 100
PROCESS_WAIT_TIMEOUT: int = 5

# États de connexion réseau affichés
CONNECTION_STATES = [
    "LISTEN",
    "ESTABLISHED",
    "TIME_WAIT",
    "CLOSE_WAIT",
    "SYN_SENT",
    "SYN_RECV",
    "FIN_WAIT1",
    "FIN_WAIT2",
    "LAST_ACK",
    "CLOSING",
]

# Protocoles
PROTOCOLS = ["tcp", "tcp6", "udp", "udp6", "unix"]

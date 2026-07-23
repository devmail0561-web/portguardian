"""Configuration du daemon PortGuardian."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DaemonConfig:
    """Configuration de l'agent daemon."""

    # Intervalle de collecte en secondes
    interval: int = 30

    # Identifiant de la machine
    hostname: str = ""

    # Serveur central
    server_url: str = ""
    api_key: str = ""

    # Notifications
    notifications_enabled: bool = True
    webhook_url: str = ""
    email_to: str = ""
    email_from: str = "portguardian@localhost"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    slack_webhook_url: str = ""

    # Stockage local
    data_dir: str = ""
    keep_history: bool = True
    max_history_files: int = 1440  # 24h à 1 snapshot/min

    def __post_init__(self) -> None:
        if not self.data_dir:
            xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
            self.data_dir = str(Path(xdg) / "portguardian" / "daemon")

    @classmethod
    def load(cls, path: Path | None = None) -> "DaemonConfig":
        """Charge la config depuis un fichier JSON."""
        if path is None:
            xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            path = Path(xdg_config) / "portguardian" / "daemon.json"

        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()

    def save(self, path: Path | None = None) -> None:
        """Sauvegarde la config."""
        if path is None:
            xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            path = Path(xdg_config) / "portguardian" / "daemon.json"

        path.parent.mkdir(parents=True, exist_ok=True)
        from dataclasses import asdict
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

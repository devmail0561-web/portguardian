"""Formatage des données pour l'affichage dans les tables."""

from utils.helpers import format_bytes, format_duration, truncate, safe_str


def format_cpu(percent: float) -> str:
    """Formate un pourcentage CPU."""
    if percent < 0.1:
        return "0.0%"
    return f"{percent:.1f}%"


def format_memory(bytes_val: int) -> str:
    """Formate une valeur mémoire."""
    return format_bytes(bytes_val)


def format_memory_percent(percent: float) -> str:
    """Formate un pourcentage mémoire."""
    return f"{percent:.1f}%"


def format_port(port: int) -> str:
    """Formate un numéro de port."""
    return str(port) if port > 0 else "*"


def format_address(addr: str) -> str:
    """Formate une adresse IP pour l'affichage."""
    if not addr:
        return "*"
    if addr == "0.0.0.0":
        return "*"
    if addr == "::":
        return "[::]"
    return addr


def format_pid(pid: int | None) -> str:
    """Formate un PID."""
    if pid is None or pid == 0:
        return "-"
    return str(pid)


def format_process_name(name: str, max_len: int = 20) -> str:
    """Formate un nom de processus."""
    if not name:
        return "-"
    return truncate(name, max_len)


def format_username(username: str) -> str:
    """Formate un nom d'utilisateur."""
    if not username:
        return "-"
    return username

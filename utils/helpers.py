"""Fonctions utilitaires générales."""

import datetime


def format_bytes(n: int) -> str:
    """Convertit un nombre d'octets en représentation lisible."""
    if n < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_duration(seconds: float) -> str:
    """Convertit une durée en secondes en format lisible (jours, heures, min)."""
    if seconds < 0:
        return "N/A"
    delta = datetime.timedelta(seconds=int(seconds))
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if days > 0:
        return f"{days}j {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def truncate(text: str, max_length: int = 40) -> str:
    """Tronque une chaîne avec des points de suspension."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def safe_str(value: object, default: str = "N/A") -> str:
    """Convertit une valeur en string, retourne default si None."""
    if value is None:
        return default
    return str(value)

"""Export des données en CSV, JSON et TXT."""

import csv
import json
import datetime
from pathlib import Path
from typing import Optional

from config import EXPORT_DIR
from core.logs import logger
from core.ports import ConnectionInfo

EXPORT_FIELDS = [
    "protocol", "local_addr", "local_port",
    "remote_addr", "remote_port", "status",
    "pid", "process_name", "username",
    "cpu_percent", "memory_percent", "service", "uptime",
]


def _generate_filename(fmt: str) -> Path:
    """Génère un nom de fichier unique avec timestamp."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return EXPORT_DIR / f"portguardian_{timestamp}.{fmt}"


def _connection_to_dict(
    conn: ConnectionInfo,
    cpu_map: dict[int, float] | None = None,
    memory_map: dict[int, float] | None = None,
    service_map: dict[int, str] | None = None,
    uptime_map: dict[int, str] | None = None,
) -> dict:
    """Convertit une ConnectionInfo en dictionnaire."""
    pid = conn.pid or 0
    return {
        "protocol": conn.protocol,
        "local_addr": conn.local_addr,
        "local_port": conn.local_port,
        "remote_addr": conn.remote_addr,
        "remote_port": conn.remote_port,
        "status": conn.status,
        "pid": conn.pid,
        "process_name": conn.process_name,
        "username": conn.username,
        "cpu_percent": (cpu_map or {}).get(pid, 0.0),
        "memory_percent": (memory_map or {}).get(pid, 0.0),
        "service": (service_map or {}).get(pid, ""),
        "uptime": (uptime_map or {}).get(pid, ""),
    }


def export_csv(
    connections: list[ConnectionInfo],
    cpu_map: dict[int, float] | None = None,
    memory_map: dict[int, float] | None = None,
    service_map: dict[int, str] | None = None,
    uptime_map: dict[int, str] | None = None,
) -> Optional[Path]:
    """Exporte les connexions en CSV."""
    filepath = _generate_filename("csv")
    try:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS)
            writer.writeheader()
            for conn in connections:
                writer.writerow(_connection_to_dict(conn, cpu_map, memory_map, service_map, uptime_map))
        logger.info("Export CSV: %s (%d entrées)", filepath, len(connections))
        return filepath
    except Exception:
        logger.exception("Erreur lors de l'export CSV")
        return None


def export_json(
    connections: list[ConnectionInfo],
    cpu_map: dict[int, float] | None = None,
    memory_map: dict[int, float] | None = None,
    service_map: dict[int, str] | None = None,
    uptime_map: dict[int, str] | None = None,
) -> Optional[Path]:
    """Exporte les connexions en JSON."""
    filepath = _generate_filename("json")
    try:
        data = [_connection_to_dict(conn, cpu_map, memory_map, service_map, uptime_map) for conn in connections]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Export JSON: %s (%d entrées)", filepath, len(connections))
        return filepath
    except Exception:
        logger.exception("Erreur lors de l'export JSON")
        return None


def export_txt(
    connections: list[ConnectionInfo],
    cpu_map: dict[int, float] | None = None,
    memory_map: dict[int, float] | None = None,
    service_map: dict[int, str] | None = None,
    uptime_map: dict[int, str] | None = None,
) -> Optional[Path]:
    """Exporte les connexions en texte tabulé."""
    filepath = _generate_filename("txt")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            header = (
                f"{'Proto':<6} {'Adresse locale':<25} {'Port':<7} "
                f"{'Remote':<25} {'État':<12} {'PID':<8} "
                f"{'Processus':<20} {'Utilisateur':<15} "
                f"{'CPU%':<7} {'RAM%':<7} {'Service':<20} {'Uptime':<8}\n"
            )
            f.write(header)
            f.write("-" * 166 + "\n")
            for conn in connections:
                d = _connection_to_dict(conn, cpu_map, memory_map, service_map, uptime_map)
                line = (
                    f"{conn.protocol:<6} {conn.local_addr:<25} {conn.local_port:<7} "
                    f"{conn.remote_addr or '*':<25} {conn.status:<12} "
                    f"{conn.pid or '-'!s:<8} {conn.process_name or '-':<20} "
                    f"{conn.username or '-':<15} "
                    f"{d['cpu_percent']:<7.1f} {d['memory_percent']:<7.1f} "
                    f"{d['service'] or '-':<20} {d['uptime'] or '-':<8}\n"
                )
                f.write(line)
        logger.info("Export TXT: %s (%d entrées)", filepath, len(connections))
        return filepath
    except Exception:
        logger.exception("Erreur lors de l'export TXT")
        return None


def export_connections(
    connections: list[ConnectionInfo],
    fmt: str,
    cpu_map: dict[int, float] | None = None,
    memory_map: dict[int, float] | None = None,
    service_map: dict[int, str] | None = None,
    uptime_map: dict[int, str] | None = None,
) -> Optional[Path]:
    """Exporte les connexions dans le format spécifié.

    Args:
        connections: liste des connexions à exporter
        fmt: format ('csv', 'json', 'txt')

    Returns:
        Chemin du fichier créé, ou None en cas d'erreur.
    """
    exporters = {
        "csv": export_csv,
        "json": export_json,
        "txt": export_txt,
    }
    exporter = exporters.get(fmt)
    if not exporter:
        logger.warning("Format d'export inconnu: %s", fmt)
        return None
    return exporter(connections, cpu_map, memory_map, service_map, uptime_map)

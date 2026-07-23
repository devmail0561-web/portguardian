"""Collecte des connexions réseau (TCP, UDP, IPv4, IPv6, Unix)."""

import socket
from dataclasses import dataclass
from typing import Optional

import psutil

from core.logs import logger


@dataclass
class ConnectionInfo:
    """Représente une connexion réseau."""

    protocol: str
    local_addr: str
    local_port: int
    remote_addr: str
    remote_port: int
    status: str
    pid: Optional[int]
    process_name: str
    username: str
    fd: int

    @property
    def local_endpoint(self) -> str:
        if ":" in self.local_addr:
            return f"[{self.local_addr}]:{self.local_port}"
        return f"{self.local_addr}:{self.local_port}"

    @property
    def remote_endpoint(self) -> str:
        if not self.remote_addr:
            return ""
        if ":" in self.remote_addr:
            return f"[{self.remote_addr}]:{self.remote_port}"
        return f"{self.remote_addr}:{self.remote_port}"


def _resolve_protocol(family: int, socket_type: int) -> str:
    """Détermine le nom du protocole à partir de la famille et du type."""
    if family == socket.AF_UNIX:
        return "unix"
    proto = "tcp" if socket_type == socket.SOCK_STREAM else "udp"
    if family == socket.AF_INET6:
        proto += "6"
    return proto


def _get_process_info(pid: Optional[int]) -> tuple[str, str]:
    """Retourne (nom_processus, utilisateur) pour un PID donné."""
    if pid is None:
        return ("", "")
    try:
        proc = psutil.Process(pid)
        return (proc.name(), proc.username())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ("", "")


def get_all_connections(
    kinds: list[str] | None = None,
    states: list[str] | None = None,
) -> list[ConnectionInfo]:
    """Collecte toutes les connexions réseau.

    Args:
        kinds: liste de types à inclure (inet4, inet6, udp4, udp6, unix). None = tous sauf unix.
        states: liste d'états à inclure. None = tous.
    """
    if kinds is None:
        kinds = ["inet4", "inet6", "udp4", "udp6"]

    connections: list[ConnectionInfo] = []
    seen: set[tuple] = set()

    for kind in kinds:
        try:
            raw_conns = psutil.net_connections(kind=kind)
        except (psutil.AccessDenied, PermissionError):
            logger.warning("Accès refusé pour net_connections(kind=%s)", kind)
            continue
        except Exception:
            logger.exception("Erreur lors de net_connections(kind=%s)", kind)
            continue

        pid_cache: dict[int, tuple[str, str]] = {}

        for conn in raw_conns:
            local_addr = ""
            local_port = 0
            remote_addr = ""
            remote_port = 0

            if conn.family == socket.AF_UNIX:
                # Pour les sockets Unix, laddr est le chemin (string)
                local_addr = str(conn.laddr) if conn.laddr else ""
                remote_addr = str(conn.raddr) if conn.raddr else ""
                status = conn.status if conn.status else "NONE"
            else:
                if conn.laddr:
                    local_addr = conn.laddr.ip if hasattr(conn.laddr, "ip") else str(conn.laddr)
                    local_port = conn.laddr.port if hasattr(conn.laddr, "port") else 0

                if conn.raddr:
                    remote_addr = conn.raddr.ip if hasattr(conn.raddr, "ip") else ""
                    remote_port = conn.raddr.port if hasattr(conn.raddr, "port") else 0

                status = conn.status if conn.status else "NONE"

            if states and status not in states:
                continue

            protocol = _resolve_protocol(conn.family, conn.type)

            dedup_key = (protocol, local_addr, local_port, remote_addr, remote_port, conn.pid)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            if conn.pid is not None and conn.pid not in pid_cache:
                pid_cache[conn.pid] = _get_process_info(conn.pid)
            proc_name, username = pid_cache.get(conn.pid, ("", ""))

            connections.append(ConnectionInfo(
                protocol=protocol,
                local_addr=local_addr,
                local_port=local_port,
                remote_addr=remote_addr,
                remote_port=remote_port,
                status=status,
                pid=conn.pid,
                process_name=proc_name,
                username=username,
                fd=conn.fd if conn.fd != -1 else 0,
            ))

    connections.sort(key=lambda c: (c.local_port, c.protocol))
    return connections


def get_listening_ports() -> list[ConnectionInfo]:
    """Retourne uniquement les ports en écoute (LISTEN)."""
    return get_all_connections(states=["LISTEN"])


def get_connections_by_pid(pid: int) -> list[ConnectionInfo]:
    """Retourne toutes les connexions d'un processus donné."""
    all_conns = get_all_connections()
    return [c for c in all_conns if c.pid == pid]

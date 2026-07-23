"""Informations détaillées sur les processus."""

import time
from dataclasses import dataclass, field
from typing import Optional

import psutil

from core.logs import logger
from utils.helpers import format_bytes, format_duration


@dataclass
class ProcessDetail:
    """Informations complètes d'un processus."""

    pid: int
    ppid: int
    name: str
    username: str
    group: str
    status: str
    cpu_percent: float
    memory_rss: int
    memory_vms: int
    memory_percent: float
    num_threads: int
    uptime: float
    exe_path: str
    cwd: str
    cmdline: str
    create_time: float
    nice: int
    open_files: list[str] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)
    environ: dict[str, str] = field(default_factory=dict)

    @property
    def memory_rss_human(self) -> str:
        return format_bytes(self.memory_rss)

    @property
    def memory_vms_human(self) -> str:
        return format_bytes(self.memory_vms)

    @property
    def uptime_human(self) -> str:
        return format_duration(self.uptime)


def get_process_detail(pid: int) -> Optional[ProcessDetail]:
    """Récupère les informations détaillées d'un processus.

    Retourne None si le processus n'existe pas ou est inaccessible.
    """
    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return None

    try:
        with proc.oneshot():
            name = _safe_call(proc.name, "")
            ppid = _safe_call(proc.ppid, 0)
            username = _safe_call(proc.username, "")
            status = _safe_call(proc.status, "unknown")
            cpu_percent = _safe_call(proc.cpu_percent, 0.0)
            memory_info = _safe_call(proc.memory_info, None)
            memory_percent = _safe_call(proc.memory_percent, 0.0)
            num_threads = _safe_call(proc.num_threads, 0)
            create_time = _safe_call(proc.create_time, 0.0)
            exe_path = _safe_call(proc.exe, "")
            cwd = _safe_call(proc.cwd, "")
            cmdline_list = _safe_call(proc.cmdline, [])
            nice = _safe_call(proc.nice, 0)

            rss = memory_info.rss if memory_info else 0
            vms = memory_info.vms if memory_info else 0
            cmdline = " ".join(cmdline_list) if cmdline_list else ""
            uptime = time.time() - create_time if create_time else 0.0

            group = _get_group(proc)
            open_files = _get_open_files(proc)
            connections = _get_connections(proc)
            environ = _get_environ(proc)

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    except Exception:
        logger.exception("Erreur lors de la collecte du processus %d", pid)
        return None

    return ProcessDetail(
        pid=pid,
        ppid=ppid,
        name=name,
        username=username,
        group=group,
        status=status,
        cpu_percent=cpu_percent,
        memory_rss=rss,
        memory_vms=vms,
        memory_percent=memory_percent,
        num_threads=num_threads,
        uptime=uptime,
        exe_path=exe_path,
        cwd=cwd,
        cmdline=cmdline,
        create_time=create_time,
        nice=nice,
        open_files=open_files,
        connections=connections,
        environ=environ,
    )


def get_process_cpu_memory(pid: int) -> tuple[float, float]:
    """Retourne rapidement (cpu_percent, memory_percent) pour un PID."""
    try:
        proc = psutil.Process(pid)
        return (proc.cpu_percent(interval=None), proc.memory_percent())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return (0.0, 0.0)


def _safe_call(func, default):
    """Appelle une méthode psutil avec gestion des erreurs d'accès."""
    try:
        return func()
    except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return default


def _get_group(proc: psutil.Process) -> str:
    """Récupère le groupe du processus."""
    try:
        import grp
        gids = proc.gids()
        return grp.getgrgid(gids.real).gr_name
    except (psutil.AccessDenied, KeyError, OSError):
        return ""


def _get_open_files(proc: psutil.Process) -> list[str]:
    """Récupère la liste des fichiers ouverts."""
    try:
        files = proc.open_files()
        return [f.path for f in files[:100]]
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return []


def _get_connections(proc: psutil.Process) -> list[str]:
    """Récupère les connexions du processus sous forme lisible."""
    try:
        conns = proc.net_connections()
        result = []
        for c in conns:
            local = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
            remote = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
            status = c.status if c.status else ""
            result.append(f"{local} -> {remote} ({status})")
        return result
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return []


def _get_environ(proc: psutil.Process) -> dict[str, str]:
    """Récupère les variables d'environnement (limité)."""
    try:
        env = proc.environ()
        return dict(list(env.items())[:50])
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        return {}

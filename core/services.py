"""Détection et gestion des services systemd."""

import subprocess
from typing import Optional

from core.logs import logger


def _run_systemctl(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Exécute une commande systemctl avec timeout."""
    cmd = ["systemctl"] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def get_service_for_pid(pid: int) -> Optional[str]:
    """Trouve le service systemd associé à un PID.

    Utilise systemctl status <pid> pour trouver l'unité.
    """
    try:
        result = _run_systemctl(["status", str(pid)])
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.endswith(".service"):
                return stripped.split()[-1]
            if "Loaded:" in stripped:
                for token in stripped.split():
                    if token.endswith(".service"):
                        return token.rstrip(";").rstrip(")")
        # Première ligne contient souvent "● nom.service - description"
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        for token in first_line.split():
            if token.endswith(".service"):
                return token
    except subprocess.TimeoutExpired:
        logger.warning("Timeout lors de systemctl status %d", pid)
    except Exception:
        logger.exception("Erreur lors de la recherche du service pour PID %d", pid)
    return None


def service_action(service_name: str, action: str) -> tuple[bool, str]:
    """Exécute une action sur un service systemd.

    Args:
        service_name: nom du service (ex: nginx.service)
        action: start, stop, restart, status

    Returns:
        (succès, message)
    """
    valid_actions = ("start", "stop", "restart", "reload", "status")
    if action not in valid_actions:
        return (False, f"Action invalide : {action}")

    try:
        result = _run_systemctl([action, service_name], timeout=30)
        if result.returncode == 0:
            msg = result.stdout.strip() if result.stdout else f"Service {service_name} : {action} OK"
            logger.info("Service %s : %s réussi", service_name, action)
            return (True, msg)
        else:
            error = result.stderr.strip() if result.stderr else f"Échec de {action} sur {service_name}"
            logger.warning("Service %s : %s échoué — %s", service_name, action, error)
            return (False, error)
    except subprocess.TimeoutExpired:
        msg = f"Timeout lors de {action} sur {service_name}"
        logger.warning(msg)
        return (False, msg)
    except Exception:
        logger.exception("Erreur lors de %s sur %s", action, service_name)
        return (False, f"Erreur inattendue lors de {action}")


def get_service_logs(service_name: str, lines: int = 50) -> str:
    """Récupère les logs récents d'un service via journalctl."""
    try:
        result = subprocess.run(
            ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "-xe"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout if result.stdout else result.stderr
    except subprocess.TimeoutExpired:
        return "Timeout lors de la lecture des logs"
    except Exception:
        logger.exception("Erreur lors de la lecture des logs de %s", service_name)
        return "Erreur lors de la lecture des logs"

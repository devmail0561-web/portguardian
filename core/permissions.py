"""Vérification des permissions et privilèges."""

import os
import sys

from core.logs import logger


def is_root() -> bool:
    """Vérifie si l'utilisateur courant est root."""
    return os.geteuid() == 0


def check_permissions() -> bool:
    """Vérifie les permissions nécessaires au fonctionnement.

    Retourne True si les permissions sont suffisantes.
    Affiche un avertissement sinon (mais ne quitte pas).
    """
    if is_root():
        logger.info("Exécution avec privilèges root")
        return True

    logger.warning(
        "Exécution sans privilèges root — certaines informations "
        "seront limitées (PID, chemins d'exécutables, etc.)"
    )
    return False


def suggest_elevation() -> str:
    """Retourne le message de suggestion pour élever les privilèges."""
    script = os.path.abspath(sys.argv[0])
    return (
        f"[yellow]Permissions limitées.[/yellow] "
        f"Pour un accès complet, relancez avec :\n\n"
        f"  [bold]sudo python {script}[/bold]\n"
    )

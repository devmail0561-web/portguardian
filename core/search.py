"""Moteur de recherche et filtrage des connexions."""

from core.ports import ConnectionInfo


def filter_connections(
    connections: list[ConnectionInfo],
    query: str,
) -> list[ConnectionInfo]:
    """Filtre les connexions par une requête de recherche.

    La recherche est insensible à la casse et cherche dans :
    - port (numérique)
    - PID (numérique)
    - nom du processus
    - utilisateur
    - protocole
    - état
    - adresse IP
    """
    if not query:
        return connections

    term = query.strip().lower()
    if not term:
        return connections

    results: list[ConnectionInfo] = []
    for conn in connections:
        if _matches(conn, term):
            results.append(conn)
    return results


def _matches(conn: ConnectionInfo, term: str) -> bool:
    """Vérifie si une connexion correspond au terme de recherche."""
    if term in str(conn.local_port):
        return True
    if conn.pid and term in str(conn.pid):
        return True
    if term in conn.process_name.lower():
        return True
    if term in conn.username.lower():
        return True
    if term in conn.protocol.lower():
        return True
    if term in conn.status.lower():
        return True
    if term in conn.local_addr.lower():
        return True
    if conn.remote_addr and term in conn.remote_addr.lower():
        return True
    return False


def sort_connections(
    connections: list[ConnectionInfo],
    key: str,
    reverse: bool = False,
    cpu_map: dict[int, float] | None = None,
    memory_map: dict[int, float] | None = None,
) -> list[ConnectionInfo]:
    """Trie les connexions par la colonne spécifiée.

    Args:
        connections: liste à trier
        key: colonne de tri (Port, PID, CPU%, RAM, Processus, Utilisateur, État, Proto)
        reverse: ordre inversé
        cpu_map: PID -> CPU% pour le tri par CPU
        memory_map: PID -> MEM% pour le tri par RAM
    """
    if cpu_map is None:
        cpu_map = {}
    if memory_map is None:
        memory_map = {}

    sort_funcs = {
        "Port": lambda c: c.local_port,
        "PID": lambda c: c.pid or 0,
        "CPU%": lambda c: cpu_map.get(c.pid or 0, 0.0),
        "RAM": lambda c: memory_map.get(c.pid or 0, 0.0),
        "Processus": lambda c: c.process_name.lower(),
        "Utilisateur": lambda c: c.username.lower(),
        "État": lambda c: c.status,
        "Proto": lambda c: c.protocol,
    }

    func = sort_funcs.get(key, lambda c: c.local_port)
    return sorted(connections, key=func, reverse=reverse)

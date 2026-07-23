"""Blocage et déblocage de ports (iptables, nftables, ufw, firewalld)."""

import shutil
import subprocess
from core.logs import logger


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Exécute une commande et retourne (succès, sortie)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, f"{cmd[0]} introuvable"
    except Exception:
        logger.exception("Erreur commande %s", cmd[0])
        return False, "Erreur inattendue"


def _detect_backend() -> str:
    """Détecte le backend firewall disponible.

    Ordre de préférence : ufw → firewalld → nftables → iptables.
    Retourne 'ufw', 'firewalld', 'nft', 'iptables' ou ''.
    """
    if shutil.which("ufw"):
        ok, out = _run(["ufw", "status"])
        if ok or "inactive" in out.lower():
            return "ufw"
    if shutil.which("firewall-cmd"):
        ok, _ = _run(["firewall-cmd", "--state"])
        if ok:
            return "firewalld"
    if shutil.which("nft"):
        ok, _ = _run(["nft", "--version"])
        if ok:
            return "nft"
    if shutil.which("iptables"):
        ok, _ = _run(["iptables", "--version"])
        if ok:
            return "iptables"
    return ""


_BACKEND: str | None = None


def get_backend() -> str:
    """Retourne le backend actif (avec cache)."""
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _detect_backend()
    return _BACKEND


def is_firewall_available() -> bool:
    return bool(get_backend())


def is_iptables_available() -> bool:
    """Compatibilité ascendante — vrai si n'importe quel backend est disponible."""
    return is_firewall_available()


# ---------------------------------------------------------------------------
# Port spec parser
# ---------------------------------------------------------------------------

def parse_port_spec(spec: str) -> list[tuple[int, int]]:
    """Parse une spécification de ports en liste de segments (début, fin).

    Formats acceptés :
    - "80"           → [(80, 80)]
    - "80,443"       → [(80, 80), (443, 443)]
    - "8000-8100"    → [(8000, 8100)]
    - "80,443,8000-8010" → [(80, 80), (443, 443), (8000, 8010)]
    """
    segments: list[tuple[int, int]] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            halves = part.split("-", 1)
            start, end = int(halves[0]), int(halves[1])
            if start > end:
                start, end = end, start
        else:
            start = end = int(part)
        if not (1 <= start <= 65535 and 1 <= end <= 65535):
            raise ValueError(f"Port hors plage 1-65535 : {part}")
        segments.append((start, end))
    if not segments:
        raise ValueError("Spécification de port vide")
    return segments


# ---------------------------------------------------------------------------
# iptables backend
# ---------------------------------------------------------------------------

def _iptables(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    return _run(["iptables"] + args, timeout)


def _iptables_apply(
    action: str,
    segments: list[tuple[int, int]],
    protocol: str,
    direction: str,
) -> tuple[bool, str]:
    protocols = ["tcp", "udp"] if protocol == "both" else [protocol]
    chain_flags: list[tuple[str, str]] = []
    if direction in ("in", "both"):
        chain_flags.append(("INPUT", "--dport"))
    if direction in ("out", "both"):
        chain_flags.append(("OUTPUT", "--dport"))

    errors: list[str] = []
    count = 0
    for proto in protocols:
        for chain, flag in chain_flags:
            for start, end in segments:
                port_spec = str(start) if start == end else f"{start}:{end}"
                ok, msg = _iptables([action, chain, "-p", proto, flag, port_spec, "-j", "DROP"])
                if ok:
                    count += 1
                elif action == "-D":
                    if "does a rule exist" not in msg.lower() and "no rule" not in msg.lower():
                        logger.debug("Déblocage iptables: règle absente (%s)", msg)
                else:
                    errors.append(f"{chain}/{proto}/{port_spec}: {msg}")

    if action == "-A":
        if not count:
            return False, "Aucune règle ajoutée. " + "; ".join(errors[:3])
        if errors:
            return True, f"{count} règle(s) ajoutée(s), {len(errors)} erreur(s)"
        _iptables_persist()
        return True, f"{count} règle(s) ajoutée(s)"
    else:
        _iptables_persist()
        return True, f"{count} règle(s) supprimée(s)"


def _iptables_persist() -> None:
    """Sauvegarde les règles iptables si iptables-save est disponible."""
    if shutil.which("iptables-save") and shutil.which("iptables-restore"):
        save_path = "/etc/iptables/rules.v4"
        try:
            import os
            os.makedirs("/etc/iptables", exist_ok=True)
            ok, out = _run(["iptables-save"])
            if ok:
                with open(save_path, "w") as f:
                    f.write(out)
                logger.info("Règles iptables sauvegardées dans %s", save_path)
        except Exception:
            logger.warning("Impossible de sauvegarder les règles iptables")


# ---------------------------------------------------------------------------
# nftables backend
# ---------------------------------------------------------------------------

def _nft_table_exists() -> bool:
    ok, out = _run(["nft", "list", "table", "inet", "portguardian"])
    return ok


def _nft_ensure_table() -> bool:
    """Crée la table nftables portguardian si elle n'existe pas."""
    if _nft_table_exists():
        return True
    cmds = [
        ["nft", "add", "table", "inet", "portguardian"],
        ["nft", "add", "chain", "inet", "portguardian", "input",
         "{ type filter hook input priority 0; policy accept; }"],
        ["nft", "add", "chain", "inet", "portguardian", "output",
         "{ type filter hook output priority 0; policy accept; }"],
    ]
    for cmd in cmds:
        ok, msg = _run(cmd)
        if not ok:
            logger.warning("nft setup: %s", msg)
            return False
    return True


def _nft_apply(
    action: str,
    segments: list[tuple[int, int]],
    protocol: str,
    direction: str,
) -> tuple[bool, str]:
    if not _nft_ensure_table():
        return False, "Impossible d'initialiser la table nftables portguardian"

    protocols = ["tcp", "udp"] if protocol == "both" else [protocol]
    chains = []
    if direction in ("in", "both"):
        chains.append(("input", "dport"))
    if direction in ("out", "both"):
        chains.append(("output", "dport"))

    count = 0
    errors: list[str] = []

    for proto in protocols:
        for chain, port_kw in chains:
            for start, end in segments:
                port_spec = str(start) if start == end else f"{start}-{end}"
                if action == "add":
                    cmd = [
                        "nft", "add", "rule", "inet", "portguardian", chain,
                        proto, port_kw, port_spec, "drop",
                    ]
                else:
                    # Pour supprimer, on liste les règles et on cherche le handle
                    ok, out = _run(["nft", "-a", "list", "chain", "inet", "portguardian", chain])
                    if not ok:
                        continue
                    import re
                    handle = None
                    pattern = re.compile(
                        rf'\b{re.escape(proto)}\b.*\b{re.escape(port_kw)}\s+{re.escape(port_spec)}\b.*\bdrop\b.*#\s*handle\s+(\d+)'
                    )
                    for line in out.splitlines():
                        m = pattern.search(line)
                        if m:
                            handle = m.group(1)
                            break
                    if handle is None:
                        continue
                    cmd = ["nft", "delete", "rule", "inet", "portguardian", chain, "handle", handle]

                ok, msg = _run(cmd)
                if ok:
                    count += 1
                else:
                    errors.append(msg)

    if count:
        _nft_persist()

    if action == "add":
        if not count:
            return False, "Aucune règle ajoutée. " + "; ".join(errors[:3])
        return True, f"{count} règle(s) nft ajoutée(s)"
    return True, f"{count} règle(s) nft supprimée(s)"


def _nft_persist() -> None:
    """Sauvegarde les règles nftables pour persistance au reboot."""
    save_path = "/etc/nftables.d/portguardian.nft"
    try:
        import os
        os.makedirs("/etc/nftables.d", exist_ok=True)
        ok, out = _run(["nft", "list", "table", "inet", "portguardian"])
        if ok:
            with open(save_path, "w") as f:
                f.write(out)
            logger.info("Règles nft sauvegardées dans %s", save_path)
    except Exception:
        logger.warning("Impossible de sauvegarder les règles nftables")


# ---------------------------------------------------------------------------
# ufw backend
# ---------------------------------------------------------------------------

def _ufw_apply(
    action: str,
    segments: list[tuple[int, int]],
    protocol: str,
    direction: str,
) -> tuple[bool, str]:
    protocols = ["tcp", "udp"] if protocol == "both" else [protocol]
    ufw_direction = {"in": "in", "out": "out", "both": "in"}.get(direction, "in")
    verb = "deny" if action == "deny" else "delete deny"

    count = 0
    errors: list[str] = []
    for proto in protocols:
        for start, end in segments:
            port_spec = str(start) if start == end else f"{start}:{end}"
            if action == "deny":
                cmd = ["ufw", ufw_direction, "deny", f"{port_spec}/{proto}"]
            else:
                cmd = ["ufw", "--force", "delete", ufw_direction, "deny", f"{port_spec}/{proto}"]
            ok, msg = _run(cmd)
            if ok:
                count += 1
            else:
                errors.append(msg)
            if direction == "both":
                if action == "deny":
                    _run(["ufw", "out", "deny", f"{port_spec}/{proto}"])
                else:
                    _run(["ufw", "--force", "delete", "out", "deny", f"{port_spec}/{proto}"])

    if action == "deny":
        if not count:
            return False, "; ".join(errors[:3])
        return True, f"{count} règle(s) ufw ajoutée(s)"
    return True, f"{count} règle(s) ufw supprimée(s)"


# ---------------------------------------------------------------------------
# firewalld backend
# ---------------------------------------------------------------------------

def _firewalld_apply(
    action: str,
    segments: list[tuple[int, int]],
    protocol: str,
    direction: str,
) -> tuple[bool, str]:
    protocols = ["tcp", "udp"] if protocol == "both" else [protocol]
    verb = "--add-rich-rule" if action == "add" else "--remove-rich-rule"

    count = 0
    errors: list[str] = []
    for proto in protocols:
        for start, end in segments:
            port_spec = str(start) if start == end else f"{start}-{end}"
            rule = (
                f'rule family="ipv4" port port="{port_spec}" protocol="{proto}" drop'
            )
            ok, msg = _run(["firewall-cmd", "--permanent", f"{verb}={rule}"])
            if ok:
                count += 1
            else:
                errors.append(msg)

    if count:
        _run(["firewall-cmd", "--reload"])

    if action == "add":
        if not count:
            return False, "; ".join(errors[:3])
        return True, f"{count} règle(s) firewalld ajoutée(s)"
    return True, f"{count} règle(s) firewalld supprimée(s)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def block_ports(spec: str, protocol: str = "tcp", direction: str = "in") -> tuple[bool, str]:
    """Bloque les ports décrits par spec via le backend firewall disponible."""
    try:
        segments = parse_port_spec(spec)
    except (ValueError, Exception) as e:
        return False, str(e)

    backend = get_backend()
    logger.info("Blocage ports: spec=%s proto=%s dir=%s backend=%s", spec, protocol, direction, backend)

    if backend == "iptables":
        return _iptables_apply("-A", segments, protocol, direction)
    if backend == "nft":
        return _nft_apply("add", segments, protocol, direction)
    if backend == "ufw":
        return _ufw_apply("deny", segments, protocol, direction)
    if backend == "firewalld":
        return _firewalld_apply("add", segments, protocol, direction)
    return False, "Aucun backend firewall disponible (iptables/nft/ufw/firewalld)"


def unblock_ports(spec: str, protocol: str = "tcp", direction: str = "in") -> tuple[bool, str]:
    """Supprime les règles de blocage pour les ports décrits par spec."""
    try:
        segments = parse_port_spec(spec)
    except (ValueError, Exception) as e:
        return False, str(e)

    backend = get_backend()
    logger.info("Déblocage ports: spec=%s proto=%s dir=%s backend=%s", spec, protocol, direction, backend)

    if backend == "iptables":
        return _iptables_apply("-D", segments, protocol, direction)
    if backend == "nft":
        return _nft_apply("delete", segments, protocol, direction)
    if backend == "ufw":
        return _ufw_apply("delete", segments, protocol, direction)
    if backend == "firewalld":
        return _firewalld_apply("remove", segments, protocol, direction)
    return False, "Aucun backend firewall disponible"


def list_blocked_ports() -> list[str]:
    """Retourne les règles DROP actives selon le backend."""
    backend = get_backend()
    rules: list[str] = []

    if backend == "iptables":
        for chain in ("INPUT", "OUTPUT"):
            ok, output = _iptables(["-L", chain, "-n", "--line-numbers"])
            if ok:
                for line in output.splitlines():
                    if "DROP" in line:
                        rules.append(f"{chain}: {line.strip()}")

    elif backend == "nft":
        ok, output = _run(["nft", "list", "table", "inet", "portguardian"])
        if ok:
            for line in output.splitlines():
                if "drop" in line.lower():
                    rules.append(line.strip())

    elif backend == "ufw":
        ok, output = _run(["ufw", "status", "numbered"])
        if ok:
            for line in output.splitlines():
                if "DENY" in line.upper():
                    rules.append(line.strip())

    elif backend == "firewalld":
        ok, output = _run(["firewall-cmd", "--list-rich-rules"])
        if ok:
            for line in output.splitlines():
                if "drop" in line.lower():
                    rules.append(line.strip())

    return rules


# ---------------------------------------------------------------------------
# IP blocking
# ---------------------------------------------------------------------------

def _validate_ip(ip: str) -> str:
    """Valide une adresse IP ou un CIDR. Retourne l'IP normalisée ou lève ValueError."""
    import ipaddress
    ip = ip.strip()
    try:
        if "/" in ip:
            net = ipaddress.ip_network(ip, strict=False)
            return str(net)
        else:
            addr = ipaddress.ip_address(ip)
            return str(addr)
    except ValueError:
        raise ValueError(f"Adresse IP invalide : {ip}")


def parse_ip_spec(spec: str) -> list[str]:
    """Parse une liste d'IPs séparées par des virgules.

    Formats acceptés :
    - "192.168.1.1"
    - "192.168.1.0/24"
    - "10.0.0.1,10.0.0.2,172.16.0.0/16"
    - "2001:db8::1"
    """
    ips: list[str] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        ips.append(_validate_ip(part))
    if not ips:
        raise ValueError("Spécification d'IP vide")
    return ips


def _iptables_apply_ip(
    action: str,
    ips: list[str],
    direction: str,
) -> tuple[bool, str]:
    chain_flags: list[tuple[str, str]] = []
    if direction in ("in", "both"):
        chain_flags.append(("INPUT", "-s"))
    if direction in ("out", "both"):
        chain_flags.append(("OUTPUT", "-d"))

    errors: list[str] = []
    count = 0
    for chain, flag in chain_flags:
        for ip in ips:
            ok, msg = _iptables([action, chain, flag, ip, "-j", "DROP"])
            if ok:
                count += 1
            else:
                errors.append(f"{chain}/{ip}: {msg}")

    if action == "-A":
        if not count:
            return False, "Aucune règle ajoutée. " + "; ".join(errors[:3])
        _iptables_persist()
        return True, f"{count} règle(s) IP ajoutée(s)"
    else:
        _iptables_persist()
        return True, f"{count} règle(s) IP supprimée(s)"


def _nft_apply_ip(
    action: str,
    ips: list[str],
    direction: str,
) -> tuple[bool, str]:
    if not _nft_ensure_table():
        return False, "Impossible d'initialiser la table nftables portguardian"

    chains = []
    if direction in ("in", "both"):
        chains.append(("input", "saddr"))
    if direction in ("out", "both"):
        chains.append(("output", "daddr"))

    count = 0
    errors: list[str] = []

    for chain, addr_kw in chains:
        for ip in ips:
            if action == "add":
                cmd = [
                    "nft", "add", "rule", "inet", "portguardian", chain,
                    "ip", addr_kw, ip, "drop",
                ]
            else:
                import re
                ok, out = _run(["nft", "-a", "list", "chain", "inet", "portguardian", chain])
                if not ok:
                    continue
                handle = None
                pattern = re.compile(
                    rf'\bip\s+{re.escape(addr_kw)}\s+{re.escape(ip)}\b.*\bdrop\b.*#\s*handle\s+(\d+)'
                )
                for line in out.splitlines():
                    m = pattern.search(line)
                    if m:
                        handle = m.group(1)
                        break
                if handle is None:
                    continue
                cmd = ["nft", "delete", "rule", "inet", "portguardian", chain, "handle", handle]

            ok, msg = _run(cmd)
            if ok:
                count += 1
            else:
                errors.append(msg)

    if count:
        _nft_persist()

    if action == "add":
        if not count:
            return False, "Aucune règle ajoutée. " + "; ".join(errors[:3])
        return True, f"{count} règle(s) IP nft ajoutée(s)"
    return True, f"{count} règle(s) IP nft supprimée(s)"


def _ufw_apply_ip(
    action: str,
    ips: list[str],
    direction: str,
) -> tuple[bool, str]:
    count = 0
    errors: list[str] = []

    for ip in ips:
        if action == "deny":
            if direction in ("in", "both"):
                cmd = ["ufw", "deny", "from", ip]
                ok, msg = _run(cmd)
                if ok:
                    count += 1
                else:
                    errors.append(msg)
            if direction in ("out", "both"):
                cmd = ["ufw", "deny", "out", "to", ip]
                ok, msg = _run(cmd)
                if ok:
                    count += 1
                else:
                    errors.append(msg)
        else:
            if direction in ("in", "both"):
                cmd = ["ufw", "--force", "delete", "deny", "from", ip]
                ok, msg = _run(cmd)
                if ok:
                    count += 1
                else:
                    errors.append(msg)
            if direction in ("out", "both"):
                cmd = ["ufw", "--force", "delete", "deny", "out", "to", ip]
                ok, msg = _run(cmd)
                if ok:
                    count += 1
                else:
                    errors.append(msg)

    if action == "deny":
        if not count:
            return False, "; ".join(errors[:3])
        return True, f"{count} règle(s) IP ufw ajoutée(s)"
    return True, f"{count} règle(s) IP ufw supprimée(s)"


def _firewalld_apply_ip(
    action: str,
    ips: list[str],
    direction: str,
) -> tuple[bool, str]:
    verb = "--add-rich-rule" if action == "add" else "--remove-rich-rule"

    count = 0
    errors: list[str] = []
    for ip in ips:
        if direction in ("in", "both"):
            rule = f'rule family="ipv4" source address="{ip}" drop'
            ok, msg = _run(["firewall-cmd", "--permanent", f"{verb}={rule}"])
            if ok:
                count += 1
            else:
                errors.append(msg)
        if direction in ("out", "both"):
            rule = f'rule family="ipv4" destination address="{ip}" drop'
            ok, msg = _run(["firewall-cmd", "--permanent", f"{verb}={rule}"])
            if ok:
                count += 1
            else:
                errors.append(msg)

    if count:
        _run(["firewall-cmd", "--reload"])

    if action == "add":
        if not count:
            return False, "; ".join(errors[:3])
        return True, f"{count} règle(s) IP firewalld ajoutée(s)"
    return True, f"{count} règle(s) IP firewalld supprimée(s)"


def block_ip(spec: str, direction: str = "in") -> tuple[bool, str]:
    """Bloque les adresses IP décrites par spec via le backend firewall disponible."""
    try:
        ips = parse_ip_spec(spec)
    except (ValueError, Exception) as e:
        return False, str(e)

    backend = get_backend()
    logger.info("Blocage IP: spec=%s dir=%s backend=%s", spec, direction, backend)

    if backend == "iptables":
        return _iptables_apply_ip("-A", ips, direction)
    if backend == "nft":
        return _nft_apply_ip("add", ips, direction)
    if backend == "ufw":
        return _ufw_apply_ip("deny", ips, direction)
    if backend == "firewalld":
        return _firewalld_apply_ip("add", ips, direction)
    return False, "Aucun backend firewall disponible"


def unblock_ip(spec: str, direction: str = "in") -> tuple[bool, str]:
    """Supprime les règles de blocage pour les IPs décrites par spec."""
    try:
        ips = parse_ip_spec(spec)
    except (ValueError, Exception) as e:
        return False, str(e)

    backend = get_backend()
    logger.info("Déblocage IP: spec=%s dir=%s backend=%s", spec, direction, backend)

    if backend == "iptables":
        return _iptables_apply_ip("-D", ips, direction)
    if backend == "nft":
        return _nft_apply_ip("delete", ips, direction)
    if backend == "ufw":
        return _ufw_apply_ip("delete", ips, direction)
    if backend == "firewalld":
        return _firewalld_apply_ip("remove", ips, direction)
    return False, "Aucun backend firewall disponible"

"""Système de règles d'alerte configurables."""

import json
from dataclasses import dataclass, field
from typing import Optional

from config import RULES_FILE
from core.logs import logger
from core.ports import ConnectionInfo


@dataclass
class AlertRule:
    """Règle d'alerte définie par l'utilisateur."""

    name: str
    severity: str            # "critical", "warning", "info"
    # Conditions (toutes doivent être vraies — AND implicite)
    port: Optional[int] = None
    port_lt: Optional[int] = None       # port < N
    port_gt: Optional[int] = None       # port > N
    protocol: Optional[str] = None
    status: Optional[str] = None
    process: Optional[str] = None       # exact ou substring si starts with '*'
    process_not: Optional[str] = None   # process ne doit PAS être cette valeur
    user: Optional[str] = None
    user_not: Optional[str] = None

    def matches(self, conn: ConnectionInfo) -> bool:
        if self.port is not None and conn.local_port != self.port:
            return False
        if self.port_lt is not None and conn.local_port >= self.port_lt:
            return False
        if self.port_gt is not None and conn.local_port <= self.port_gt:
            return False
        if self.protocol is not None and conn.protocol != self.protocol:
            return False
        if self.status is not None and conn.status != self.status:
            return False
        if self.process is not None:
            pattern = self.process
            if pattern.startswith("*"):
                if pattern[1:] not in conn.process_name:
                    return False
            elif conn.process_name != pattern:
                return False
        if self.process_not is not None and conn.process_name == self.process_not:
            return False
        if self.user is not None and conn.username != self.user:
            return False
        if self.user_not is not None and conn.username == self.user_not:
            return False
        return True

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "AlertRule":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Alert:
    """Alerte levée par une règle."""

    rule_name: str
    severity: str
    connection: ConnectionInfo
    message: str = ""

    def __post_init__(self) -> None:
        if not self.message:
            c = self.connection
            self.message = (
                f"[{self.rule_name}] {c.protocol}:{c.local_port} "
                f"{c.process_name} (PID {c.pid}, user {c.username})"
            )


class AlertEngine:
    """Évalue les règles sur les connexions et émet des alertes."""

    def __init__(self) -> None:
        self._rules: list[AlertRule] = []
        self._load_rules()

    def _load_rules(self) -> None:
        if not RULES_FILE.exists():
            self._rules = _default_rules()
            return
        try:
            data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            self._rules = [AlertRule.from_dict(r) for r in data]
            logger.info("AlertEngine: %d règle(s) chargée(s)", len(self._rules))
        except Exception:
            logger.exception("Erreur lors du chargement des règles d'alerte")
            self._rules = _default_rules()

    def save_rules(self) -> None:
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        RULES_FILE.write_text(
            json.dumps([r.to_dict() for r in self._rules], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def reload(self) -> None:
        self._load_rules()

    @property
    def rules(self) -> list[AlertRule]:
        return list(self._rules)

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)
        self.save_rules()

    def remove_rule(self, name: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        if len(self._rules) < before:
            self.save_rules()
            return True
        return False

    def evaluate(self, connections: list[ConnectionInfo]) -> list[Alert]:
        alerts: list[Alert] = []
        for conn in connections:
            for rule in self._rules:
                if rule.matches(conn):
                    alerts.append(Alert(
                        rule_name=rule.name,
                        severity=rule.severity,
                        connection=conn,
                    ))
        return alerts


def _default_rules() -> list[AlertRule]:
    """Règles par défaut illustratives (désactivées — process_not=None)."""
    return [
        AlertRule(
            name="SSH non-sshd",
            severity="critical",
            port=22,
            status="LISTEN",
            process_not="sshd",
        ),
        AlertRule(
            name="Port privilégié / non-root",
            severity="warning",
            port_lt=1024,
            status="LISTEN",
            user_not="root",
        ),
    ]

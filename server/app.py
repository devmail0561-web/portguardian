"""Serveur web Flask — reçoit les rapports des agents et expose un dashboard."""

import hmac
import json
import time
import threading
from datetime import timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, render_template, abort, session, redirect, url_for

from server.auth import (
    require_auth,
    require_action_auth,
    generate_csrf_token,
    verify_password,
    load_password_hash,
    get_or_create_secret_key,
)
from server.audit import get_recent_audit

VERSION = (Path(__file__).parent.parent / "VERSION").read_text().strip()

app = Flask(__name__, template_folder="templates", static_folder="static")

# Stockage en mémoire (remplaçable par une DB)
_lock = threading.Lock()
_hosts: dict[str, dict] = {}
_history: dict[str, list[dict]] = {}
_events: list[dict] = []
_heartbeats: dict[str, dict] = {}
_command_queues: dict[str, list[dict]] = {}

MAX_HISTORY_PER_HOST = 120
MAX_GLOBAL_EVENTS = 500

API_KEY: str | None = None
PASSWORD_HASH: str | None = None
NO_AUTH: bool = False


def require_agent_auth(f):
    """Auth spécifique pour les agents (API key obligatoire)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY:
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], API_KEY):
                abort(401)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Agent endpoint (report)
# ---------------------------------------------------------------------------

@app.route("/api/report", methods=["POST"])
@require_agent_auth
def receive_report():
    """Reçoit un snapshot depuis un agent."""
    data = request.get_json(force=True)
    hostname = data.get("hostname", "unknown")

    with _lock:
        _hosts[hostname] = data

        if hostname not in _history:
            _history[hostname] = []
        _history[hostname].append({
            "timestamp": data.get("timestamp", time.time()),
            "connections_total": data.get("connections_total", 0),
            "listening_total": data.get("listening_total", 0),
        })
        if len(_history[hostname]) > MAX_HISTORY_PER_HOST:
            _history[hostname] = _history[hostname][-MAX_HISTORY_PER_HOST:]

        for event in data.get("events", []):
            event["hostname"] = hostname
            event["timestamp"] = data.get("timestamp", time.time())
            _events.append(event)

        if len(_events) > MAX_GLOBAL_EVENTS:
            _events[:] = _events[-MAX_GLOBAL_EVENTS:]

    return jsonify({"status": "ok"})


@app.route("/api/heartbeat", methods=["POST"])
@require_agent_auth
def receive_heartbeat():
    """Reçoit un heartbeat léger d'un agent."""
    data = request.get_json(force=True)
    hostname = data.get("hostname", "unknown")
    with _lock:
        if hostname not in _heartbeats:
            _heartbeats[hostname] = {}
        _heartbeats[hostname] = {
            "timestamp": data.get("timestamp", time.time()),
            "queue_size": data.get("queue_size", 0),
        }
    return jsonify({"status": "ok"})


@app.route("/api/commands/<hostname>", methods=["GET"])
@require_agent_auth
def get_commands(hostname: str):
    """Retourne les commandes en attente pour un agent et vide la queue."""
    with _lock:
        commands = _command_queues.pop(hostname, [])
    return jsonify(commands)


MAX_QUEUE_PER_HOST = 50
QUEUE_TTL_SECONDS = 3600

VALID_REMOTE_ACTIONS = {"kill", "block-port", "unblock-port", "block-ip", "unblock-ip", "service"}


def _purge_stale_queues() -> None:
    """Supprime les entrées de queue trop anciennes et les queues orphelines vides."""
    cutoff = time.time() - QUEUE_TTL_SECONDS
    with _lock:
        dead = []
        for h, cmds in _command_queues.items():
            _command_queues[h] = [c for c in cmds if c.get("_ts", 0) > cutoff]
            if not _command_queues[h]:
                dead.append(h)
        for h in dead:
            del _command_queues[h]


@app.route("/api/commands/<hostname>", methods=["POST"])
@require_action_auth
def push_command(hostname: str):
    """Enqueue une commande pour un agent distant."""
    data = request.get_json(force=True)
    action = data.get("action", "")
    params = data.get("params", {})

    if not action:
        return jsonify({"success": False, "message": "Action requise"}), 400
    if action not in VALID_REMOTE_ACTIONS:
        return jsonify({"success": False, "message": f"Action invalide: {action}"}), 400

    # Validation minimale des paramètres selon l'action
    if action == "kill":
        pid = params.get("pid")
        if not isinstance(pid, int) or pid <= 1:
            return jsonify({"success": False, "message": "PID invalide (doit être > 1)"}), 400
        sig = params.get("signal", "SIGTERM")
        if sig not in ("SIGTERM", "SIGKILL", "SIGSTOP", "SIGCONT"):
            return jsonify({"success": False, "message": f"Signal invalide: {sig}"}), 400
    elif action in ("block-port", "unblock-port"):
        if not params.get("spec", "").strip():
            return jsonify({"success": False, "message": "Spec de port requise"}), 400
    elif action in ("block-ip", "unblock-ip"):
        if not params.get("spec", "").strip():
            return jsonify({"success": False, "message": "Spec IP requise"}), 400
    elif action == "service":
        if not params.get("name", "").strip() or not params.get("action", "").strip():
            return jsonify({"success": False, "message": "Nom et action du service requis"}), 400

    _purge_stale_queues()

    with _lock:
        if hostname not in _command_queues:
            _command_queues[hostname] = []
        if len(_command_queues[hostname]) >= MAX_QUEUE_PER_HOST:
            return jsonify({"success": False, "message": f"Queue pleine pour {hostname} ({MAX_QUEUE_PER_HOST} max)"}), 429
        _command_queues[hostname].append({"action": action, "params": params, "_ts": time.time()})

    from server.audit import log_action
    log_action(f"remote:{action}", {"hostname": hostname, **params}, "queued", True,
               request.remote_addr or "unknown")

    return jsonify({"success": True, "message": f"Commande {action} envoyée à {hostname}"})


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET"])
def login_page():
    if NO_AUTH or session.get("authenticated"):
        return redirect(url_for("dashboard"))
    return render_template("login.html", error=None, version=VERSION)


@app.route("/login", methods=["POST"])
def login_submit():
    from server.ratelimit import action_limiter
    if not action_limiter.is_allowed(f"login:{request.remote_addr}"):
        return render_template("login.html", error="Trop de tentatives — réessayez dans une minute.", version=VERSION)

    password = request.form.get("password", "")
    stored = PASSWORD_HASH or load_password_hash()

    if stored and verify_password(password, stored):
        session.permanent = True
        session["authenticated"] = True
        generate_csrf_token()
        return redirect(url_for("dashboard"))

    return render_template("login.html", error="Mot de passe incorrect", version=VERSION)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------------------
# API (read-only, authenticated)
# ---------------------------------------------------------------------------

@app.route("/api/hosts")
@require_auth
def api_hosts():
    """Liste des hôtes avec résumé."""
    with _lock:
        result = []
        for hostname, snap in _hosts.items():
            result.append({
                "hostname": hostname,
                "last_seen": snap.get("iso_time", ""),
                "timestamp": snap.get("timestamp", 0),
                "connections_total": snap.get("connections_total", 0),
                "listening_total": snap.get("listening_total", 0),
                "events_count": len(snap.get("events", [])),
            })
    return jsonify(result)


@app.route("/api/hosts/<hostname>")
@require_auth
def api_host_detail(hostname: str):
    """Détail complet d'un hôte."""
    with _lock:
        snap = _hosts.get(hostname)
        if not snap:
            abort(404)
        return jsonify(snap)


@app.route("/api/hosts/<hostname>/history")
@require_auth
def api_host_history(hostname: str):
    """Historique d'un hôte."""
    with _lock:
        hist = _history.get(hostname, [])
    return jsonify(hist)


@app.route("/api/events")
@require_auth
def api_events():
    """Événements globaux récents."""
    limit = request.args.get("limit", 50, type=int)
    with _lock:
        return jsonify(_events[-limit:])


@app.route("/api/hosts/<hostname>/process/<int:pid>")
@require_auth
def api_process_detail(hostname: str, pid: int):
    """Détail d'un processus extrait du dernier snapshot de l'agent distant."""
    with _lock:
        snap = _hosts.get(hostname)
    if not snap:
        abort(404)
    # Cherche dans process_summary du snapshot
    proc = next((p for p in snap.get("process_summary", []) if p.get("pid") == pid), None)
    if proc is None:
        # Cherche dans les connexions (contiennent aussi des métriques par PID)
        conn = next((c for c in snap.get("connections", []) if c.get("pid") == pid), None)
        if conn is None:
            abort(404)
        proc = {k: conn[k] for k in ("pid", "process_name", "cpu_percent", "memory_rss",
                                      "memory_percent", "io_read_bytes", "io_write_bytes",
                                      "uptime_seconds") if k in conn}
        proc["name"] = proc.pop("process_name", "")
    return jsonify({
        "pid": proc.get("pid", pid),
        "name": proc.get("name", ""),
        "service": proc.get("service", ""),
        "connections_count": proc.get("connections_count", 0),
        "cpu_percent": proc.get("cpu_percent", 0),
        "memory_rss": proc.get("memory_rss", 0),
        "memory_vms": proc.get("memory_vms", 0),
        "memory_percent": proc.get("memory_percent", 0),
        "io_read_bytes": proc.get("io_read_bytes", 0),
        "io_write_bytes": proc.get("io_write_bytes", 0),
        "uptime_seconds": proc.get("uptime_seconds", 0),
        # Les champs détaillés (exe, cwd, env, fichiers) nécessitent un agent local
        # Ils seront disponibles via une future commande pull
        "source": "snapshot",
        "hostname": hostname,
    })


@app.route("/api/stats/<hostname>")
@require_auth
def api_host_stats(hostname: str):
    """Séries temporelles pour les graphiques d'un hôte."""
    with _lock:
        hist = _history.get(hostname, [])
    return jsonify(hist)


@app.route("/api/stats")
@require_auth
def api_global_stats():
    """Statistiques agrégées de toutes les machines — séries temporelles + snapshot courant."""
    with _lock:
        hosts_snap = dict(_hosts)
        history_snap = {h: list(v) for h, v in _history.items()}

    now = time.time()

    # Snapshot courant par machine
    machines = []
    total_conns = 0
    total_listen = 0
    for hostname, snap in hosts_snap.items():
        age = now - snap.get("timestamp", 0)
        status = "online" if age < 120 else "stale" if age < 600 else "offline"
        c = snap.get("connections_total", 0)
        l = snap.get("listening_total", 0)
        total_conns += c
        total_listen += l
        sys_info = snap.get("system", {})
        bw = snap.get("bandwidth", [])
        total_recv = sum(i.get("recv_rate", 0) for i in bw)
        total_sent = sum(i.get("sent_rate", 0) for i in bw)
        machines.append({
            "hostname": hostname,
            "status": status,
            "connections": c,
            "listening": l,
            "cpu_percent": sys_info.get("cpu_percent", 0),
            "memory_percent": sys_info.get("memory_percent", 0),
            "recv_rate": total_recv,
            "sent_rate": total_sent,
            "events_count": len(snap.get("events", [])),
        })

    # Série temporelle agrégée : somme connexions + ports sur les N derniers points
    # On aligne sur un axe temps commun (bucket de 30s)
    bucket_size = 30
    buckets: dict[int, dict] = {}
    for hostname, hist in history_snap.items():
        for pt in hist:
            ts = pt.get("timestamp", 0)
            b = int(ts / bucket_size) * bucket_size
            if b not in buckets:
                buckets[b] = {"timestamp": b, "connections_total": 0, "listening_total": 0}
            buckets[b]["connections_total"] += pt.get("connections_total", 0)
            buckets[b]["listening_total"] += pt.get("listening_total", 0)

    timeline = sorted(buckets.values(), key=lambda x: x["timestamp"])[-60:]

    return jsonify({
        "machines": machines,
        "timeline": timeline,
        "totals": {
            "machines": len(machines),
            "online": sum(1 for m in machines if m["status"] == "online"),
            "connections": total_conns,
            "listening": total_listen,
        },
    })


@app.route("/api/audit")
@require_auth
def api_audit():
    """Journal d'audit des actions."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_recent_audit(limit))


@app.route("/api/firewall/rules")
@require_auth
def api_firewall_rules():
    """Règles firewall du serveur local (dépréciée — préférer /api/hosts/<h>/firewall)."""
    from core.firewall import list_blocked_ports, get_backend
    rules = list_blocked_ports()
    return jsonify({"backend": get_backend(), "rules": rules})


@app.route("/api/hosts/<hostname>/firewall")
@require_auth
def api_host_firewall(hostname: str):
    """Règles firewall d'un agent distant, telles que rapportées dans son dernier snapshot."""
    with _lock:
        snap = _hosts.get(hostname)
    if not snap:
        abort(404)
    fw = snap.get("firewall", {})
    return jsonify({
        "hostname": hostname,
        "backend": fw.get("backend", ""),
        "rules": fw.get("rules", []),
        "error": fw.get("error", ""),
    })


# ---------------------------------------------------------------------------
# Web pages (authenticated)
# ---------------------------------------------------------------------------

@app.route("/")
@require_auth
def dashboard():
    """Dashboard web principal."""
    with _lock:
        hosts = []
        now = time.time()
        for hostname, snap in _hosts.items():
            age = now - snap.get("timestamp", 0)
            status = "online" if age < 120 else "stale" if age < 600 else "offline"
            hosts.append({
                "hostname": hostname,
                "status": status,
                "last_seen": snap.get("iso_time", "?"),
                "connections": snap.get("connections_total", 0),
                "listening": snap.get("listening_total", 0),
                "events": len(snap.get("events", [])),
            })
        recent_events = _events[-20:]

    return render_template("dashboard.html", hosts=hosts, events=reversed(recent_events),
                           api_key_set=bool(API_KEY), active_page="dashboard")


@app.route("/events")
@require_auth
def events_page():
    """Page HTML des evenements."""
    with _lock:
        all_events = list(reversed(_events[-100:]))
        hosts_list = list(_hosts.keys())

    return render_template(
        "events.html",
        events=all_events,
        hosts_list=hosts_list,
        hosts_count=len(hosts_list),
        active_page="events",
    )


@app.route("/host/<hostname>")
@require_auth
def host_page(hostname: str):
    """Page détail d'un hôte."""
    with _lock:
        snap = _hosts.get(hostname)
        if not snap:
            abort(404)
        hist = _history.get(hostname, [])

    return render_template("host.html", host=snap, history=hist, active_page="host")


@app.route("/firewall")
@require_auth
def firewall_page():
    """Page règles firewall."""
    return render_template("firewall.html", active_page="firewall")


@app.route("/audit")
@require_auth
def audit_page():
    """Page journal d'audit."""
    entries = get_recent_audit(100)
    return render_template("audit.html", entries=entries, active_page="audit")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(api_key: str | None = None, password: str | None = None, secret_key: str | None = None, no_auth: bool = False) -> Flask:
    global API_KEY, PASSWORD_HASH, NO_AUTH
    API_KEY = api_key
    NO_AUTH = no_auth

    if password:
        from server.auth import hash_password, save_password_hash
        PASSWORD_HASH = hash_password(password)
        save_password_hash(PASSWORD_HASH)
    elif not no_auth:
        PASSWORD_HASH = load_password_hash()

    app.secret_key = secret_key or get_or_create_secret_key()
    app.permanent_session_lifetime = timedelta(hours=8)
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    @app.context_processor
    def inject_globals():
        return {"version": VERSION, "csrf_token": generate_csrf_token()}

    from server.actions import actions_bp
    if "actions" not in {bp.name for bp in app.iter_blueprints()}:
        app.register_blueprint(actions_bp)

    return app

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


@app.route("/api/commands/<hostname>", methods=["POST"])
@require_auth
def push_command(hostname: str):
    """Enqueue une commande pour un agent distant."""
    data = request.get_json(force=True)
    action = data.get("action", "")
    params = data.get("params", {})

    if not action:
        return jsonify({"success": False, "message": "Action requise"}), 400

    with _lock:
        if hostname not in _command_queues:
            _command_queues[hostname] = []
        _command_queues[hostname].append({"action": action, "params": params})

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


@app.route("/api/audit")
@require_auth
def api_audit():
    """Journal d'audit des actions."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_recent_audit(limit))


@app.route("/api/firewall/rules")
@require_auth
def api_firewall_rules():
    """Règles firewall actives."""
    from core.firewall import list_blocked_ports, get_backend
    rules = list_blocked_ports()
    return jsonify({"backend": get_backend(), "rules": rules})


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

    return render_template("dashboard.html", hosts=hosts, events=reversed(recent_events), api_key=API_KEY)


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

    return render_template("host.html", host=snap, history=hist)


@app.route("/firewall")
@require_auth
def firewall_page():
    """Page règles firewall."""
    return render_template("firewall.html")


@app.route("/audit")
@require_auth
def audit_page():
    """Page journal d'audit."""
    entries = get_recent_audit(100)
    return render_template("audit.html", entries=entries)


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

    @app.context_processor
    def inject_globals():
        return {"version": VERSION, "csrf_token": generate_csrf_token()}

    from server.actions import actions_bp
    if "actions" not in {bp.name for bp in app.iter_blueprints()}:
        app.register_blueprint(actions_bp)

    return app

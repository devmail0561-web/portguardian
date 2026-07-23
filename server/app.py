"""Serveur web Flask — reçoit les rapports des agents et expose un dashboard."""

import json
import time
import threading
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, render_template, abort

app = Flask(__name__, template_folder="templates", static_folder="static")

# Stockage en mémoire (remplaçable par une DB)
_lock = threading.Lock()
_hosts: dict[str, dict] = {}  # hostname -> dernier snapshot
_history: dict[str, list[dict]] = {}  # hostname -> N derniers snapshots
_events: list[dict] = []  # événements globaux

MAX_HISTORY_PER_HOST = 120
MAX_GLOBAL_EVENTS = 500

# Clé API (configurable via env ou config)
API_KEY: str | None = None


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY:
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != API_KEY:
                abort(401)
        return f(*args, **kwargs)
    return decorated


@app.route("/api/report", methods=["POST"])
@require_api_key
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


@app.route("/api/hosts")
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
def api_host_detail(hostname: str):
    """Détail complet d'un hôte."""
    with _lock:
        snap = _hosts.get(hostname)
        if not snap:
            abort(404)
        return jsonify(snap)


@app.route("/api/hosts/<hostname>/history")
def api_host_history(hostname: str):
    """Historique d'un hôte."""
    with _lock:
        hist = _history.get(hostname, [])
    return jsonify(hist)


@app.route("/api/events")
def api_events():
    """Événements globaux récents."""
    limit = request.args.get("limit", 50, type=int)
    with _lock:
        return jsonify(_events[-limit:])


@app.route("/")
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
def host_page(hostname: str):
    """Page détail d'un hôte."""
    with _lock:
        snap = _hosts.get(hostname)
        if not snap:
            abort(404)
        hist = _history.get(hostname, [])

    return render_template("host.html", host=snap, history=hist)


def create_app(api_key: str | None = None) -> Flask:
    global API_KEY
    API_KEY = api_key
    return app

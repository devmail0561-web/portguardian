"""Action endpoints — kill, block/unblock ports/IPs, service management."""

import os
import signal

from flask import Blueprint, request, jsonify

from server.auth import require_action_auth
from server.ratelimit import action_limiter
from server.audit import log_action

actions_bp = Blueprint("actions", __name__, url_prefix="/api/actions")

SIGNAL_MAP = {
    "SIGTERM": signal.SIGTERM,
    "SIGKILL": signal.SIGKILL,
    "SIGSTOP": signal.SIGSTOP,
    "SIGCONT": signal.SIGCONT,
}

VALID_PROTOCOLS = ("tcp", "udp", "both")
VALID_DIRECTIONS = ("in", "out", "both")
VALID_SERVICE_ACTIONS = ("start", "stop", "restart", "reload", "status")


def _client_ip() -> str:
    return request.remote_addr or "unknown"


def _check_rate_limit():
    if not action_limiter.is_allowed(_client_ip()):
        return jsonify({"success": False, "message": "Rate limit exceeded"}), 429
    return None


@actions_bp.route("/kill", methods=["POST"])
@require_action_auth
def kill_process():
    limited = _check_rate_limit()
    if limited:
        return limited

    data = request.get_json(force=True)
    pid = data.get("pid")
    sig_name = data.get("signal", "SIGTERM")

    if not isinstance(pid, int) or pid <= 1:
        return jsonify({"success": False, "message": "PID invalide (doit être > 1)"}), 400

    if sig_name not in SIGNAL_MAP:
        return jsonify({"success": False, "message": f"Signal invalide: {sig_name}"}), 400

    try:
        os.kill(pid, SIGNAL_MAP[sig_name])
        msg = f"{sig_name} envoyé à PID {pid}"
        log_action("kill", {"pid": pid, "signal": sig_name}, msg, True, _client_ip())
        return jsonify({"success": True, "message": msg})
    except ProcessLookupError:
        msg = f"PID {pid} introuvable"
        log_action("kill", {"pid": pid, "signal": sig_name}, msg, False, _client_ip())
        return jsonify({"success": False, "message": msg}), 404
    except PermissionError:
        msg = "Permission refusée"
        log_action("kill", {"pid": pid, "signal": sig_name}, msg, False, _client_ip())
        return jsonify({"success": False, "message": msg}), 403
    except Exception as e:
        msg = str(e)
        log_action("kill", {"pid": pid, "signal": sig_name}, msg, False, _client_ip())
        return jsonify({"success": False, "message": msg}), 500


@actions_bp.route("/block-port", methods=["POST"])
@require_action_auth
def block_port():
    limited = _check_rate_limit()
    if limited:
        return limited

    data = request.get_json(force=True)
    spec = data.get("spec", "").strip()
    protocol = data.get("protocol", "tcp")
    direction = data.get("direction", "in")

    if not spec:
        return jsonify({"success": False, "message": "Spécification de port requise"}), 400
    if protocol not in VALID_PROTOCOLS:
        return jsonify({"success": False, "message": f"Protocole invalide: {protocol}"}), 400
    if direction not in VALID_DIRECTIONS:
        return jsonify({"success": False, "message": f"Direction invalide: {direction}"}), 400

    from core.firewall import block_ports
    ok, msg = block_ports(spec, protocol, direction)
    log_action("block-port", {"spec": spec, "protocol": protocol, "direction": direction}, msg, ok, _client_ip())
    status = 200 if ok else 400
    return jsonify({"success": ok, "message": msg}), status


@actions_bp.route("/unblock-port", methods=["POST"])
@require_action_auth
def unblock_port():
    limited = _check_rate_limit()
    if limited:
        return limited

    data = request.get_json(force=True)
    spec = data.get("spec", "").strip()
    protocol = data.get("protocol", "tcp")
    direction = data.get("direction", "in")

    if not spec:
        return jsonify({"success": False, "message": "Spécification de port requise"}), 400
    if protocol not in VALID_PROTOCOLS:
        return jsonify({"success": False, "message": f"Protocole invalide: {protocol}"}), 400
    if direction not in VALID_DIRECTIONS:
        return jsonify({"success": False, "message": f"Direction invalide: {direction}"}), 400

    from core.firewall import unblock_ports
    ok, msg = unblock_ports(spec, protocol, direction)
    log_action("unblock-port", {"spec": spec, "protocol": protocol, "direction": direction}, msg, ok, _client_ip())
    status = 200 if ok else 400
    return jsonify({"success": ok, "message": msg}), status


@actions_bp.route("/block-ip", methods=["POST"])
@require_action_auth
def block_ip_endpoint():
    limited = _check_rate_limit()
    if limited:
        return limited

    data = request.get_json(force=True)
    spec = data.get("spec", "").strip()
    direction = data.get("direction", "in")

    if not spec:
        return jsonify({"success": False, "message": "Spécification d'IP requise"}), 400
    if direction not in VALID_DIRECTIONS:
        return jsonify({"success": False, "message": f"Direction invalide: {direction}"}), 400

    from core.firewall import block_ip
    ok, msg = block_ip(spec, direction)
    log_action("block-ip", {"spec": spec, "direction": direction}, msg, ok, _client_ip())
    status = 200 if ok else 400
    return jsonify({"success": ok, "message": msg}), status


@actions_bp.route("/unblock-ip", methods=["POST"])
@require_action_auth
def unblock_ip_endpoint():
    limited = _check_rate_limit()
    if limited:
        return limited

    data = request.get_json(force=True)
    spec = data.get("spec", "").strip()
    direction = data.get("direction", "in")

    if not spec:
        return jsonify({"success": False, "message": "Spécification d'IP requise"}), 400
    if direction not in VALID_DIRECTIONS:
        return jsonify({"success": False, "message": f"Direction invalide: {direction}"}), 400

    from core.firewall import unblock_ip
    ok, msg = unblock_ip(spec, direction)
    log_action("unblock-ip", {"spec": spec, "direction": direction}, msg, ok, _client_ip())
    status = 200 if ok else 400
    return jsonify({"success": ok, "message": msg}), status


@actions_bp.route("/service", methods=["POST"])
@require_action_auth
def service_endpoint():
    limited = _check_rate_limit()
    if limited:
        return limited

    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    action = data.get("action", "").strip()

    if not name:
        return jsonify({"success": False, "message": "Nom de service requis"}), 400
    if action not in VALID_SERVICE_ACTIONS:
        return jsonify({"success": False, "message": f"Action invalide: {action}"}), 400
    if not name.endswith(".service"):
        name += ".service"

    from core.services import service_action
    ok, msg = service_action(name, action)
    log_action("service", {"name": name, "action": action}, msg, ok, _client_ip())
    status = 200 if ok else 400
    return jsonify({"success": ok, "message": msg}), status

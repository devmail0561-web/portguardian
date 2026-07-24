"""Authentication, session management, and CSRF protection."""

import hashlib
import hmac
import os
import secrets
from pathlib import Path
from functools import wraps

from flask import request, session, redirect, url_for, abort, jsonify

CONFIG_DIR = Path.home() / ".config" / "portguardian"


def _ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def hash_password(plain: str) -> str:
    salt = secrets.token_bytes(32)
    iterations = 260000
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, iterations)
    return f"{salt.hex()}:{iterations}:{dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt_hex, iterations_str, dk_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        iterations = int(iterations_str)
        dk = bytes.fromhex(dk_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, iterations)
        return hmac.compare_digest(candidate, dk)
    except (ValueError, TypeError):
        return False


def save_password_hash(hashed: str) -> None:
    path = _ensure_config_dir() / "server_password.hash"
    path.write_text(hashed, encoding="utf-8")
    os.chmod(path, 0o600)


def load_password_hash() -> str | None:
    path = CONFIG_DIR / "server_password.hash"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def get_or_create_secret_key() -> str:
    path = _ensure_config_dir() / "server_secret.key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    os.chmod(path, 0o600)
    return key


def generate_csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token(token: str) -> bool:
    expected = session.get("csrf_token", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


def require_auth(f):
    """Require either a valid session or a valid API key. Bypassed if NO_AUTH."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from server.app import API_KEY, NO_AUTH

        if NO_AUTH:
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and API_KEY:
            if hmac.compare_digest(auth_header[7:], API_KEY):
                return f(*args, **kwargs)

        if session.get("authenticated"):
            return f(*args, **kwargs)

        if request.is_json or request.path.startswith("/api/"):
            abort(401)

        return redirect(url_for("login_page"))

    return decorated


def require_action_auth(f):
    """Require auth + CSRF validation for session-based requests."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from server.app import API_KEY, NO_AUTH

        if NO_AUTH:
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and API_KEY:
            if hmac.compare_digest(auth_header[7:], API_KEY):
                return f(*args, **kwargs)

        if not session.get("authenticated"):
            abort(401)

        token = request.headers.get("X-CSRF-Token", "")
        if not validate_csrf_token(token):
            abort(403)

        return f(*args, **kwargs)

    return decorated

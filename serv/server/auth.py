import json
import time
from typing import Optional

import pyotp
from flask import Blueprint, current_app, jsonify, request

from .tokens import generate_token, revoke_token

bp = Blueprint("auth", __name__)


def load_secret(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _persist_tokens() -> None:
    tokens_file = current_app.config.get("TOKENS_FILE")
    if not tokens_file:
        return
    with open(tokens_file, "w", encoding="utf8") as handle:
        json.dump(current_app.config.get("AUTHORIZED_TOKENS", {}), handle)


@bp.route("/auth/verify", methods=["POST"])
def verify():
    payload = request.get_json(force=True, silent=True) or {}
    code = (payload.get("code") or "").strip()
    admin_header = request.headers.get("X-Admin-Code")

    s1 = load_secret(current_app.config.get("TOTP_FILE"))
    if s1:
        totp1 = pyotp.TOTP(s1)
        if totp1.verify(code, valid_window=1):
            token = generate_token(1)
            meta = current_app.config["AUTHORIZED_TOKENS"][token]
            return jsonify({"token": token, "level": 1, "expiry": meta["expiry"]})

    s2 = load_secret(current_app.config.get("TOTP_FILE_PRO"))
    if s2:
        totp2 = pyotp.TOTP(s2)
        if totp2.verify(code, valid_window=1):
            admin_secret = load_secret(current_app.config.get("ADMIN_SECRET_FILE"))
            if admin_header and admin_secret and admin_header.strip() == admin_secret.strip():
                sessions = current_app.config.setdefault(
                    "ADMIN_SESSIONS", {"active": {}, "blocked_until": 0}
                )
                now = time.time()
                if sessions.get("blocked_until", 0) > now:
                    return jsonify({"error": "admin_blocked"}), 403
                if len(sessions.get("active", {})) >= 2:
                    sessions["blocked_until"] = now + 24 * 3600
                    tokens = list(current_app.config.get("AUTHORIZED_TOKENS", {}).items())
                    for token_value, meta in tokens:
                        if meta.get("level") == 3:
                            current_app.config["AUTHORIZED_TOKENS"].pop(token_value, None)
                    _persist_tokens()
                    return (
                        jsonify({"error": "admin_limit_exceeded_all_admins_blocked_24h"}),
                        403,
                    )
                token = generate_token(3)
                sessions["active"][token] = now
                current_app.config["ADMIN_SESSIONS"] = sessions
                return jsonify({"token": token, "level": 3, "expiry": None})

            token = generate_token(2)
            meta = current_app.config["AUTHORIZED_TOKENS"][token]
            return jsonify({"token": token, "level": 2, "expiry": meta["expiry"]})

    return jsonify({"error": "invalid_code"}), 401


@bp.route("/auth/logout", methods=["POST"])
def logout():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "authorization_required"}), 401
    token = auth.split(" ", 1)[1].strip()
    revoke_token(token)
    sessions = current_app.config.setdefault("ADMIN_SESSIONS", {"active": {}, "blocked_until": 0})
    sessions.get("active", {}).pop(token, None)
    return jsonify({"ok": True})

import json
import os
import pathlib
import secrets

import pyotp
from flask import Flask


def _ensure_secret_file(path: str) -> None:
    file_path = pathlib.Path(path)
    if file_path.exists():
        return
    secret = pyotp.random_base32()
    file_path.write_text(f"{secret}\n", encoding="utf8")


def _ensure_admin_secret(path: str) -> None:
    file_path = pathlib.Path(path)
    if file_path.exists():
        return
    secret = secrets.token_urlsafe(32)
    file_path.write_text(f"{secret}\n", encoding="utf8")


def create_app() -> Flask:
    base_dir = pathlib.Path(__file__).resolve().parent.parent
    app = Flask(__name__)

    app.config["PROJECT_ROOT"] = str(base_dir)
    app.config["ROOT"] = str(base_dir / "local")
    app.config["BASE"] = "/api"
    app.config["TOKENS_FILE"] = os.path.join(app.config["PROJECT_ROOT"], "tokens.json")
    app.config["TOTP_FILE"] = os.path.join(app.config["PROJECT_ROOT"], "totp_secret.txt")
    app.config["TOTP_FILE_PRO"] = os.path.join(app.config["PROJECT_ROOT"], "totp_secret_pro.txt")
    app.config["TOTP_FILE_ADMIN"] = os.path.join(app.config["PROJECT_ROOT"], "totp_secret_pro.txt")
    app.config["ADMIN_SECRET_FILE"] = os.path.join(
        app.config["PROJECT_ROOT"], "admin", "adminadmin"
    )

    pathlib.Path(app.config["ROOT"]).mkdir(parents=True, exist_ok=True)
    pathlib.Path(app.config["ADMIN_SECRET_FILE"]).parent.mkdir(parents=True, exist_ok=True)
    _ensure_secret_file(app.config["TOTP_FILE"])
    _ensure_secret_file(app.config["TOTP_FILE_PRO"])
    _ensure_admin_secret(app.config["ADMIN_SECRET_FILE"])

    app.config["AUTHORIZED_TOKENS"] = {}
    app.config["PRO_CHANGES"] = {}
    app.config["ADMIN_SESSIONS"] = {"active": {}, "blocked_until": 0}

    tokens_path = pathlib.Path(app.config["TOKENS_FILE"])
    if tokens_path.exists():
        try:
            app.config["AUTHORIZED_TOKENS"] = json.loads(tokens_path.read_text(encoding="utf8"))
        except json.JSONDecodeError:
            app.config["AUTHORIZED_TOKENS"] = {}

    return app

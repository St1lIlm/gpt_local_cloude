import io
import os
import pathlib
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import pyotp
from flask import Blueprint, Response, current_app, jsonify, request, send_file

from .auth import load_secret
from .tokens import get_token_meta

bp = Blueprint("files", __name__)

MAX_OPEN_SIZE = 4 * 1024 * 1024 * 1024


def _safe_resolve(rel_path: str) -> Optional[pathlib.Path]:
    root = pathlib.Path(current_app.config["ROOT"]).resolve()
    rel = pathlib.Path(rel_path)
    if rel.is_absolute():
        return None
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _move_to_local_del(path: pathlib.Path) -> pathlib.Path:
    project_root = pathlib.Path(current_app.config["PROJECT_ROOT"])
    root = pathlib.Path(current_app.config["ROOT"])
    base = project_root / "local_del" / path.parent.relative_to(root)
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest = base / f"{path.stem}_{ts}{path.suffix}"
    shutil.move(str(path), str(dest))
    return dest


def cleanup_local_del(days: int = 14) -> None:
    project_root = pathlib.Path(current_app.config["PROJECT_ROOT"])
    target = project_root / "local_del"
    if not target.exists():
        return
    cutoff = datetime.utcnow() - timedelta(days=days)
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtime = datetime.utcfromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
            except OSError:
                continue


def _get_client_key() -> str:
    return request.headers.get("X-Client-Id") or request.remote_addr or "unknown"


def _check_pro_limit(path_key: str) -> Optional[Tuple[dict, Response]]:
    limit_state: Dict[str, dict] = current_app.config.setdefault("PRO_CHANGES", {})
    client_key = _get_client_key()
    entry = limit_state.setdefault(
        client_key,
        {"paths": {}, "blocked_until": 0, "violations": 0},
    )
    now = time.time()
    if entry.get("blocked_until", 0) > now:
        return None, (
            jsonify({"error": "pro_blocked", "blocked_until": entry["blocked_until"]}),
            403,
        )
    window_start = now - 600
    paths = {k: v for k, v in entry.get("paths", {}).items() if v >= window_start}
    entry["paths"] = paths
    if path_key not in paths:
        paths[path_key] = now
    unique_count = len(paths)
    if unique_count > 10:
        entry["violations"] = entry.get("violations", 0) + 1
        block_minutes = 10 * (entry["violations"] ** 1.5)
        entry["blocked_until"] = now + block_minutes * 60
        return None, (
            jsonify(
                {
                    "error": "pro_limit_exceeded",
                    "blocked_until": entry["blocked_until"],
                    "unique_count": unique_count,
                }
            ),
            403,
        )
    limit_state[client_key] = entry
    return entry, None


def _require_token(level: int) -> Tuple[Optional[dict], Optional[Response]]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify({"error": "authorization_required"}), 401)
    token = auth.split(" ", 1)[1].strip()
    meta = get_token_meta(token)
    if not meta or meta.get("level", 0) < level:
        return None, (jsonify({"error": "forbidden"}), 403)
    return meta, None


def _range_from_header(range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
    if not range_header or not range_header.startswith("bytes="):
        return None
    range_spec = range_header.replace("bytes=", "", 1)
    if "-" not in range_spec:
        return None
    start_s, end_s = range_spec.split("-", 1)
    try:
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
    except ValueError:
        return None
    if start < 0 or end < start:
        return None
    return start, min(end, file_size - 1)


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@bp.route("/list", methods=["GET"])
def list_files():
    _, error = _require_token(1)
    if error:
        return error
    rel = (request.args.get("path") or "").strip("/")
    resolved = _safe_resolve(rel)
    if not resolved or not resolved.exists() or not resolved.is_dir():
        return jsonify({"error": "not_found"}), 404
    items = []
    for entry in sorted(resolved.iterdir(), key=lambda p: p.name.lower()):
        try:
            stat = entry.stat()
        except OSError:
            continue
        items.append(
            {
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": stat.st_size,
                "mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return jsonify({"path": rel, "items": items})


@bp.route("/file/info", methods=["GET"])
def file_info():
    _, error = _require_token(1)
    if error:
        return error
    rel = (request.args.get("path") or "").strip("/")
    resolved = _safe_resolve(rel)
    if not resolved or not resolved.exists():
        return jsonify({"error": "not_found"}), 404
    stat = resolved.stat()
    return jsonify(
        {
            "path": rel,
            "is_dir": resolved.is_dir(),
            "size": stat.st_size,
            "mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
        }
    )


@bp.route("/download/<path:rel_path>", methods=["GET"])
def download(rel_path: str):
    _, error = _require_token(1)
    if error:
        return error
    rel = rel_path.strip("/")
    resolved = _safe_resolve(rel)
    if not resolved or not resolved.exists() or resolved.is_dir():
        return jsonify({"error": "not_found"}), 404

    file_size = resolved.stat().st_size
    range_header = request.headers.get("Range")
    range_tuple = _range_from_header(range_header, file_size)
    if range_tuple:
        start, end = range_tuple
        length = end - start + 1
        with open(resolved, "rb") as handle:
            handle.seek(start)
            data = handle.read(length)
        response = Response(data, 206, mimetype="application/octet-stream")
        response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = str(length)
        return response
    return send_file(resolved, as_attachment=True)


@bp.route("/export", methods=["POST"])
def export_folder():
    _, error = _require_token(1)
    if error:
        return error
    payload = request.get_json(force=True, silent=True) or {}
    rel = (payload.get("path") or "").strip("/")
    resolved = _safe_resolve(rel)
    if not resolved or not resolved.exists() or not resolved.is_dir():
        return jsonify({"error": "not_found"}), 404

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in resolved.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(resolved))
    buffer.seek(0)
    filename = f"{resolved.name}.zip"
    return send_file(buffer, as_attachment=True, download_name=filename)


@bp.route("/file/open", methods=["GET"])
def open_file():
    _, error = _require_token(1)
    if error:
        return error
    rel = (request.args.get("path") or "").strip("/")
    resolved = _safe_resolve(rel)
    if not resolved or not resolved.exists() or resolved.is_dir():
        return jsonify({"error": "not_found"}), 404
    size = resolved.stat().st_size
    if size > MAX_OPEN_SIZE:
        return jsonify({"error": "file_too_large"}), 413
    return send_file(resolved, as_attachment=False)


@bp.route("/file/upload", methods=["POST"])
def upload_file():
    meta, error = _require_token(2)
    if error:
        return error
    if meta and meta.get("level") == 2:
        _, pro_error = _check_pro_limit(request.form.get("path", ""))
        if pro_error:
            return pro_error
    if "file" not in request.files:
        return jsonify({"error": "file_missing"}), 400
    rel = (request.form.get("path") or "").strip("/")
    resolved = _safe_resolve(rel)
    if not resolved:
        return jsonify({"error": "invalid_path"}), 400
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists():
        _move_to_local_del(resolved)
    request.files["file"].save(resolved)
    return jsonify({"ok": True, "path": rel})


@bp.route("/file/delete", methods=["POST"])
def delete_file():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "authorization_required"}), 401
    token = auth.split(" ", 1)[1].strip()
    tokmeta = get_token_meta(token)
    if not tokmeta or tokmeta.get("level") != 3:
        return jsonify({"error": "forbidden_or_not_admin"}), 403

    payload = request.get_json(force=True, silent=True) or {}
    code = (payload.get("code") or "").strip()
    admin_header = request.headers.get("X-Admin-Code", "").strip()
    admin_secret = load_secret(current_app.config.get("ADMIN_SECRET_FILE"))
    if not admin_secret or admin_secret.strip() != admin_header:
        return jsonify({"error": "admin_code_invalid"}), 403
    s2 = load_secret(current_app.config.get("TOTP_FILE_PRO"))
    if not s2 or not pyotp.TOTP(s2).verify(code, valid_window=1):
        return jsonify({"error": "invalid_action_totp"}), 403

    rel = (payload.get("path") or "").strip("/")
    resolved = _safe_resolve(rel)
    if not resolved or not resolved.exists():
        return jsonify({"error": "not_found"}), 404
    try:
        dest = _move_to_local_del(resolved)
        return jsonify(
            {
                "ok": True,
                "moved_to": str(
                    dest.relative_to(pathlib.Path(current_app.config["PROJECT_ROOT"]))
                ),
            }
        )
    except Exception as exc:
        return jsonify({"error": "move_failed", "message": str(exc)}), 500

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from flask import current_app


def _persist_tokens(store: dict) -> None:
    tokens_file = current_app.config.get("TOKENS_FILE")
    if not tokens_file:
        return
    with open(tokens_file, "w", encoding="utf8") as handle:
        json.dump(store, handle)


def generate_token(level: int) -> str:
    if level == 3:
        token = secrets.token_urlsafe(64)
        expiry = None
    elif level == 2:
        token = secrets.token_urlsafe(48)
        expiry = (datetime.utcnow() + timedelta(hours=12)).isoformat()
    else:
        token = secrets.token_urlsafe(40)
        expiry = (datetime.utcnow() + timedelta(days=1)).isoformat()

    store = current_app.config.setdefault("AUTHORIZED_TOKENS", {})
    store[token] = {"level": level, "expiry": expiry}
    _persist_tokens(store)
    return token


def revoke_token(token: str) -> None:
    store = current_app.config.setdefault("AUTHORIZED_TOKENS", {})
    if token in store:
        store.pop(token, None)
        _persist_tokens(store)


def get_token_meta(token: str) -> Optional[dict]:
    store = current_app.config.setdefault("AUTHORIZED_TOKENS", {})
    meta = store.get(token)
    if not meta:
        return None
    expiry = meta.get("expiry")
    if expiry:
        try:
            expires_at = datetime.fromisoformat(expiry)
        except ValueError:
            revoke_token(token)
            return None
        if expires_at < datetime.utcnow():
            revoke_token(token)
            return None
    return meta

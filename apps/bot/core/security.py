from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl

import jwt

from apps.bot.infra.settings import get_settings

settings = get_settings()


class AuthError(Exception):
    pass


def _build_data_check_string(params: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(params.items()))


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict[str, Any]:
    if not init_data:
        raise AuthError("Missing init data")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_value = pairs.pop("hash", None)
    if not hash_value:
        raise AuthError("Missing hash")

    data_check_string = _build_data_check_string(pairs)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, hash_value):
        raise AuthError("Invalid hash")

    user_raw = pairs.get("user")
    if not user_raw:
        raise AuthError("Missing user payload")
    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise AuthError("Invalid user payload") from exc
    return user_data


def create_crash_jwt(user_id: int, tg_id: int) -> tuple[str, int]:
    ttl = settings.crash_jwt_ttl
    expires = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl)
    payload = {
        "sub": str(user_id),
        "tg_id": tg_id,
        "exp": expires,
        "type": "crash",
    }
    token = jwt.encode(payload, settings.crash_jwt_secret, algorithm="HS256")
    return token, ttl


def decode_crash_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.crash_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid token") from exc

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from apps.bot.core.security import AuthError, settings, verify_telegram_init_data


def _build_init_data(auth_date: int) -> str:
    payload = {
        "auth_date": str(auth_date),
        "query_id": "AAEAA",
        "user": json.dumps({"id": 42, "username": "tester"}),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token_test.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    payload["hash"] = signature
    return urlencode(payload)


def test_verify_telegram_init_data_allows_recent_payload() -> None:
    init_data = _build_init_data(int(time.time()))
    user = verify_telegram_init_data(init_data, settings.bot_token_test)
    assert user["id"] == 42


def test_verify_telegram_init_data_rejects_expired_payload() -> None:
    expired_timestamp = int(time.time() - (settings.telegram_init_ttl + 30))
    init_data = _build_init_data(expired_timestamp)
    with pytest.raises(AuthError):
        verify_telegram_init_data(init_data, settings.bot_token_test)

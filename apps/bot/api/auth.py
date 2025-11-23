from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.api.deps import get_session
from apps.bot.core.security import AuthError, create_crash_jwt, verify_telegram_init_data
from apps.bot.core.wallets import get_wallet_balance
from apps.bot.infra.settings import get_settings
from apps.bot.repositories.users import upsert_telegram_user

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _candidate_bot_tokens() -> list[str]:
    tokens: list[str] = []
    if settings.bot_token_main:
        tokens.append(settings.bot_token_main)
    if settings.bot_token_test and settings.bot_token_test not in tokens:
        tokens.append(settings.bot_token_test)
    return tokens


def _verify_init_data(init_data: str) -> dict:
    last_error: AuthError | None = None
    for token in _candidate_bot_tokens():
        try:
            return verify_telegram_init_data(init_data, token)
        except AuthError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise AuthError("Bot tokens are not configured")


@router.post("/telegram")
async def auth_telegram(
    *,
    authorization: str = Header(..., alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    if not authorization.lower().startswith("tma "):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing init data")
    init_data = authorization[4:].strip()
    try:
        payload = _verify_init_data(init_data)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    tg_id = int(payload.get("id"))
    username = payload.get("username")
    first_name = payload.get("first_name")
    language = payload.get("language_code")

    user = await upsert_telegram_user(
        session,
        tg_id=tg_id,
        username=username,
        first_name=first_name,
        language_code=language,
    )
    wallet = await get_wallet_balance(session, user.id)
    token, ttl = create_crash_jwt(user.id, tg_id)
    return {
        "token": token,
        "expires_in": ttl,
        "user": {
            "id": user.id,
            "telegramId": user.tg_id,
            "username": user.username,
            "firstName": first_name,
            "avatarUrl": payload.get("photo_url"),
            "blocked": user.banned,
        },
        "wallet": {
            "cash": wallet.coins_cash,
            "bonus": wallet.coins_bonus,
            "total": wallet.coins_cash + wallet.coins_bonus,
        },
    }

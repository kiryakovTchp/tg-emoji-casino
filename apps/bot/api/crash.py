from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, conint, confloat
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.api.deps import get_current_user, get_session
from apps.bot.db.models import User
from apps.bot.services import crash as crash_service

router = APIRouter(prefix="/api/crash", tags=["crash"])


class BetRequest(BaseModel):
    amount: conint(gt=0)
    auto_cashout: confloat(gt=1.0) | None = Field(default=None, description="Auto cashout multiplier")


class CashoutRequest(BaseModel):
    pass


def _as_http_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get("/state")
async def crash_state(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    snapshot = await crash_service.get_state(session, user.id)
    return snapshot.to_dict()


@router.post("/bet")
async def crash_bet(
    request: BetRequest,
    fastapi_request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    try:
        snapshot = await crash_service.place_bet(
            session,
            user=user,
            amount=int(request.amount),
            auto_cashout=float(request.auto_cashout) if request.auto_cashout else None,
        )
    except ValueError as exc:
        raise _as_http_error(exc)
    manager = getattr(fastapi_request.app.state, "crash_ws", None)
    if manager:
        await manager.notify_bet(user.id, snapshot)
    return snapshot.to_dict()


@router.post("/cashout")
async def crash_cashout(
    fastapi_request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    try:
        snapshot = await crash_service.cashout(session, user=user)
    except ValueError as exc:
        raise _as_http_error(exc)
    manager = getattr(fastapi_request.app.state, "crash_ws", None)
    if manager:
        await manager.notify_cashout(user.id, snapshot)
    return snapshot.to_dict()

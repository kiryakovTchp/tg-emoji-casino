from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.security import AuthError, decode_crash_jwt
from apps.bot.db.models import User

security = HTTPBearer(auto_error=True)


async def get_session(request: Request) -> AsyncSession:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise RuntimeError("Database is not configured")
    async with database.session() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_crash_jwt(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    user_id = int(payload.get("sub", 0))
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.banned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User banned")
    return user

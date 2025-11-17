from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.db.models import Event


async def track_event(
    session: AsyncSession,
    *,
    user_id: int | None,
    name: str,
    props: dict | None = None,
    source: str = "bot",
) -> Event:
    event = Event(
        user_id=user_id,
        name=name,
        props=props or {},
        source=source,
        created_at=datetime.utcnow(),
    )
    session.add(event)
    return event

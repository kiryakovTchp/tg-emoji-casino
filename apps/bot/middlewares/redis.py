from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis


class RedisMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["redis"] = self._redis
        return await handler(event, data)

from __future__ import annotations

from redis.asyncio import Redis, from_url

from .settings import Settings


def create_redis_pool(settings: Settings) -> Redis:
    return from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

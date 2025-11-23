from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

import uvicorn
from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from apps.bot.api.http import router as http_router
from apps.bot.ws.crash import router as crash_ws_router, CrashWebSocketManager
from apps.bot.handlers import register_handlers
from apps.bot.infra.db import Database
from apps.bot.infra.logging import setup_logging
from apps.bot.infra.redis import create_redis_pool
from apps.bot.infra.settings import get_settings
from apps.bot.middlewares import DatabaseSessionMiddleware, RedisMiddleware


@dataclass
class BotRunner:
    name: str
    bot: Bot
    dispatcher: Dispatcher
    task: asyncio.Task | None = field(default=None, init=False)


settings = get_settings()
setup_logging(settings.log_level)

database = Database(settings)
redis = create_redis_pool(settings)
crash_ws_manager = CrashWebSocketManager(database, redis)


def build_dispatcher(name: str) -> Dispatcher:
    dp = Dispatcher(name=f"{name}_dispatcher")
    dp.update.middleware(DatabaseSessionMiddleware(database))
    dp.update.middleware(RedisMiddleware(redis))
    register_handlers(dp)
    return dp


def build_bot_runners() -> list[BotRunner]:
    runners: list[BotRunner] = []
    for name, token in settings.bot_tokens.items():
        bot = Bot(token=token, parse_mode="HTML")
        dp = build_dispatcher(name)
        runners.append(BotRunner(name=name, bot=bot, dispatcher=dp))
    return runners


bot_runners = build_bot_runners()


def build_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.state.database = database
    app.state.redis = redis
    app.state.crash_ws = crash_ws_manager
    app.include_router(http_router)
    app.include_router(crash_ws_router)

    @app.on_event("startup")
    async def on_startup() -> None:
        for runner in bot_runners:
            runner.task = asyncio.create_task(runner.dispatcher.start_polling(runner.bot))
        await crash_ws_manager.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await crash_ws_manager.stop()
        for runner in bot_runners:
            if runner.task:
                runner.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await runner.task
            await runner.bot.session.close()
        await database.dispose()
        await redis.close()

    return app


app = build_app()


if __name__ == "__main__":
    uvicorn.run("apps.bot.main:app", host="0.0.0.0", port=8000)

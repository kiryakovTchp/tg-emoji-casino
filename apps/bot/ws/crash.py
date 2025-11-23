from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from apps.bot.core.security import AuthError, decode_crash_jwt
from apps.bot.db.models import CrashRoundStatus, User
from apps.bot.infra.db import Database
from apps.bot.services import crash as crash_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CrashWebSocketManager:
    EVENT_CHANNEL = "crash:events"
    ROUND_LOCK_KEY = "crash:round-loop"
    ROUND_LOCK_TTL = 10

    def __init__(self, database: Database, redis: Redis) -> None:
        self._database = database
        self._redis = redis
        self._connections: dict[int, set[WebSocket]] = {}
        self._round_task: asyncio.Task | None = None
        self._pubsub_task: asyncio.Task | None = None
        self._pubsub = None
        self._lock = asyncio.Lock()
        self._last_round: dict | None = None
        self._node_id = secrets.token_hex(8)

    async def start(self) -> None:
        crash_service.set_auto_cashout_consumer(self._handle_auto_cashout_event)
        await self._drain_pending_auto_cashouts()
        if self._pubsub_task is None:
            await self._start_pubsub()
        if self._round_task is None:
            self._round_task = asyncio.create_task(self._round_loop())

    async def stop(self) -> None:
        crash_service.set_auto_cashout_consumer(None)
        if self._round_task:
            self._round_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._round_task
            self._round_task = None
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pubsub_task
            self._pubsub_task = None
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(self.EVENT_CHANNEL)
                await self._pubsub.close()
            self._pubsub = None

    async def handle_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            auth_message = await websocket.receive_json()
        except WebSocketDisconnect:
            await websocket.close()
            return
        token = auth_message.get("token")
        if not token:
            await websocket.close(code=4403)
            return
        try:
            payload = decode_crash_jwt(token)
        except AuthError as exc:
            logger.warning(f"WS Auth failed: {exc}")
            await websocket.close(code=4403)
            return
        user_id = int(payload.get("sub", 0))
        logger.info(f"WS Auth success for user_id={user_id}")
        async with self._database.session() as session:
            try:
                user = await session.get(User, user_id)
                if user is None or user.banned:
                    await websocket.close(code=4403)
                    return
                snapshot = await crash_service.get_state(session, user.id)
                history = await crash_service.get_recent_history(session, limit=30)
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()
        await websocket.send_json(
            {
                "type": "auth-success",
                "user": {
                    "id": user_id,
                    "telegramId": payload.get("tg_id"),
                    "username": user.username,
                },
            }
        )
        await websocket.send_json({"type": "sync", **snapshot.session})
        await websocket.send_json({"type": "balance-update", "userId": user_id, "balance": snapshot.balance["total"]})
        await websocket.send_json({"type": "session-history", "history": history})

        await self._register(user_id, websocket)
        try:
            while True:
                try:
                    # Wait for messages with a timeout (e.g. 60s)
                    # If client doesn't ping, we disconnect
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                except asyncio.TimeoutError:
                    logger.info(f"WS Client timeout user_id={user_id}")
                    break
                except WebSocketDisconnect:
                    break
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
        finally:
            await self._unregister(user_id, websocket)

    async def notify_bet(self, user_id: int, snapshot: crash_service.CrashSnapshot) -> None:
        await self._emit_event(
            {
                "type": "bet-accepted",
                "userId": user_id,
                "bet": snapshot.bet,
                "sessionId": snapshot.session["id"],
            }
        )
        await self._emit_event(
            {"type": "balance-update", "userId": user_id, "balance": snapshot.balance["total"]},
        )

    async def notify_cashout(self, user_id: int, snapshot: crash_service.CrashSnapshot) -> None:
        await self._emit_event(
            {
                "type": "cashout-processed",
                "userId": user_id,
                "cashout": snapshot.cashout,
                "sessionId": snapshot.session["id"],
            }
        )
        await self._emit_event(
            {"type": "balance-update", "userId": user_id, "balance": snapshot.balance["total"]},
        )

    async def _register(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def _unregister(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns and websocket in conns:
                conns.remove(websocket)
            if conns is not None and not conns:
                self._connections.pop(user_id, None)

    async def _round_loop(self) -> None:
        lock = self._redis.lock(self.ROUND_LOCK_KEY, timeout=self.ROUND_LOCK_TTL)
        while True:
            try:
                acquired = await lock.acquire(blocking=False)
                if not acquired:
                    await asyncio.sleep(1)
                    continue
                try:
                    while True:
                        async with self._database.session() as session:
                            try:
                                summary = await crash_service.get_round_summary(session)
                            except Exception:
                                await session.rollback()
                                raise
                            else:
                                await session.commit()
                        await self._maybe_emit_round_events(summary)
                        await lock.extend(self.ROUND_LOCK_TTL)
                        await asyncio.sleep(1)
                finally:
                    if await lock.locked():
                        with contextlib.suppress(Exception):
                            await lock.release()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # TODO: Add proper logging
                print(f"Error in round loop: {exc}")
                await asyncio.sleep(1)

    async def _maybe_emit_round_events(self, summary: dict) -> None:
        last = self._last_round
        event_type = None
        if last is None or summary["id"] != last["id"]:
            event_type = "game-start"
        elif summary["phase"] != last["phase"]:
            if summary["phase"] == CrashRoundStatus.FLYING.value:
                event_type = "game-flying"
            elif summary["phase"] == CrashRoundStatus.CRASHED.value:
                event_type = "game-crash"
        if event_type:
            payload = {"type": event_type, "sessionId": summary["id"], **summary}
            await self._emit_event(payload)
        self._last_round = summary

    async def _send_to_user(self, user_id: int, payload: dict) -> None:
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))
        await self._send_many(sockets, payload)

    async def _broadcast_local(self, payload: dict) -> None:
        async with self._lock:
            sockets = [ws for ws_set in self._connections.values() for ws in ws_set]
        await self._send_many(sockets, payload)

    async def _send_many(self, sockets: list[WebSocket], payload: dict) -> None:
        if not sockets:
            return

        async def _send_one(websocket: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(websocket.send_json(payload), timeout=0.5)
                return None
            except Exception:
                return websocket

        results = await asyncio.gather(*[_send_one(ws) for ws in sockets], return_exceptions=True)
        
        stale = []
        for result in results:
            if isinstance(result, WebSocket):
                stale.append(result)
            elif isinstance(result, Exception):
                # Should not happen due to return_exceptions=True but safe to handle
                pass
        
        for websocket in stale:
            await self._remove_socket(websocket)

    async def _remove_socket(self, websocket: WebSocket) -> None:
        with contextlib.suppress(Exception):
            await websocket.close()
        async with self._lock:
            for user_id, conns in list(self._connections.items()):
                if websocket in conns:
                    conns.remove(websocket)
                    if not conns:
                        self._connections.pop(user_id, None)
                    break

    async def _emit_event(self, event: dict[str, Any], publish: bool = True) -> None:
        payload = dict(event)
        payload["origin"] = self._node_id
        await self._deliver_event(payload)
        if publish:
            await self._redis.publish(self.EVENT_CHANNEL, json.dumps(payload, default=str))

    async def _deliver_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type in {"bet-accepted", "cashout-processed"}:
            user_id = int(event.get("userId", 0))
            await self._send_to_user(user_id, event)
        if event_type in {"bet-accepted", "cashout-processed"}:
            # nothing else to do here; balance update handled separately
            return
        if event_type == "balance-update":
            await self._send_to_user(int(event.get("userId", 0)), event)
            return
        if event_type in {"game-start", "game-flying", "game-crash"}:
            await self._broadcast_local(event)

    async def _start_pubsub(self) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self.EVENT_CHANNEL)
        self._pubsub_task = asyncio.create_task(self._pubsub_loop())

    async def _pubsub_loop(self) -> None:
        assert self._pubsub is not None
        while True:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    try:
                        payload = json.loads(data)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if payload.get("origin") == self._node_id:
                        continue
                    await self._deliver_event(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1)

    async def _handle_auto_cashout_event(self, event: crash_service.AutoCashoutEvent) -> None:
        asyncio.create_task(self._process_auto_cashout_event(event))

    async def _process_auto_cashout_event(self, event: crash_service.AutoCashoutEvent) -> None:
        snapshot = event.snapshot
        await self._emit_event(
            {
                "type": "cashout-processed",
                "userId": event.user_id,
                "cashout": snapshot.cashout,
                "sessionId": snapshot.session["id"],
            }
        )
        await self._emit_event(
            {"type": "balance-update", "userId": event.user_id, "balance": snapshot.balance["total"]},
        )

    async def _drain_pending_auto_cashouts(self) -> None:
        pending = crash_service.consume_auto_cashout_events()
        for event in pending:
            await self._process_auto_cashout_event(event)


@router.websocket("/ws/crash")
async def crash_socket(websocket: WebSocket):
    manager: CrashWebSocketManager | None = getattr(websocket.app.state, "crash_ws", None)
    if manager is None:
        await websocket.close()
        return
    await manager.handle_websocket(websocket)

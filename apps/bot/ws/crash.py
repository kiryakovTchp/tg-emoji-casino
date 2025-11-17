from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.bot.core.security import AuthError, decode_crash_jwt
from apps.bot.db.models import CrashRoundStatus, User
from apps.bot.infra.db import Database
from apps.bot.services import crash as crash_service

router = APIRouter()


class CrashWebSocketManager:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._connections: dict[int, set[WebSocket]] = {}
        self._round_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._last_round: dict | None = None

    async def start(self) -> None:
        if self._round_task is None:
            self._round_task = asyncio.create_task(self._round_loop())

    async def stop(self) -> None:
        if self._round_task:
            self._round_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._round_task
            self._round_task = None

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
        except AuthError:
            await websocket.close(code=4403)
            return
        user_id = int(payload.get("sub", 0))
        async with self._database.session() as session:
            user = await session.get(User, user_id)
            if user is None or user.banned:
                await websocket.close(code=4403)
                return
            snapshot = await crash_service.get_state(session, user.id)
            history = await crash_service.get_recent_history(session, limit=30)
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
                    message = await websocket.receive_json()
                except WebSocketDisconnect:
                    break
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
        finally:
            await self._unregister(user_id, websocket)

    async def notify_bet(self, user_id: int, snapshot: crash_service.CrashSnapshot) -> None:
        event = {
            "type": "bet-accepted",
            "userId": user_id,
            "bet": snapshot.bet,
            "sessionId": snapshot.session["id"],
        }
        await self._send_to_user(user_id, event)
        await self._send_to_user(
            user_id,
            {"type": "balance-update", "userId": user_id, "balance": snapshot.balance["total"]},
        )

    async def notify_cashout(self, user_id: int, snapshot: crash_service.CrashSnapshot) -> None:
        event = {
            "type": "cashout-processed",
            "userId": user_id,
            "cashout": snapshot.cashout,
            "sessionId": snapshot.session["id"],
        }
        await self._send_to_user(user_id, event)
        await self._send_to_user(
            user_id,
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
            if conns and not conns:
                self._connections.pop(user_id, None)

    async def _round_loop(self) -> None:
        while True:
            try:
                async with self._database.session() as session:
                    summary = await crash_service.get_round_summary(session)
                await self._maybe_emit_round_events(summary)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
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
            await self._broadcast(payload)
        self._last_round = summary

    async def _send_to_user(self, user_id: int, payload: dict) -> None:
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))
        await self._send_many(sockets, payload)

    async def _broadcast(self, payload: dict) -> None:
        async with self._lock:
            sockets = [ws for ws_set in self._connections.values() for ws in ws_set]
        await self._send_many(sockets, payload)

    async def _send_many(self, sockets: list[WebSocket], payload: dict) -> None:
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                continue


@router.websocket("/ws/crash")
async def crash_socket(websocket: WebSocket):
    manager: CrashWebSocketManager | None = getattr(websocket.app.state, "crash_ws", None)
    if manager is None:
        await websocket.close()
        return
    await manager.handle_websocket(websocket)

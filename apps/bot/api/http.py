from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .auth import router as auth_router
from .crash import router as crash_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(crash_router)


@router.get("/health", response_class=PlainTextResponse)
async def healthcheck() -> str:
    return "ok"


@router.get("/metrics")
async def metrics() -> Response:
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

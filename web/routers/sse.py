"""Server-Sent Events router for real-time queue updates."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sse", tags=["sse"])

# Injected during app startup
_event_bus = None
_auth_manager = None

SSE_KEEPALIVE_TIMEOUT = 30  # seconds before sending a keepalive comment


def set_dependencies(event_bus, auth_manager) -> None:
    global _event_bus, _auth_manager
    _event_bus = event_bus
    _auth_manager = auth_manager


def _verify_token(token: str) -> bool:
    if not _auth_manager or not token:
        return False
    is_valid, _ = _auth_manager.verify_token(token)
    if is_valid:
        return True
    is_valid, _ = _auth_manager.verify_api_token(token)
    return is_valid


async def _event_stream(channel: str) -> AsyncGenerator[str, None]:
    queue = _event_bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_TIMEOUT)
                if event["channel"] == channel:
                    yield f"data: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        _event_bus.unsubscribe(queue)


def _sse_response(channel: str) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(channel),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _not_ready() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Service not ready"})


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})


@router.get("/downloads")
async def sse_downloads(token: str = Query(...)):
    """SSE endpoint for download queue updates."""
    if not _verify_token(token):
        return _unauthorized()
    if _event_bus is None:
        return _not_ready()
    return _sse_response("download_queue")


@router.get("/ocr")
async def sse_ocr(token: str = Query(...)):
    """SSE endpoint for OCR queue updates."""
    if not _verify_token(token):
        return _unauthorized()
    if _event_bus is None:
        return _not_ready()
    return _sse_response("ocr_queue")

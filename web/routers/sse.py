"""Server-Sent Events router for real-time queue updates."""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from web.routers.auth import get_verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sse", tags=["sse"])

# Injected during app startup
_event_bus = None
_auth_manager = None

SSE_KEEPALIVE_TIMEOUT = 30  # seconds before sending a keepalive comment
_TICKET_TTL = 30  # seconds before a ticket expires

_tickets: dict[str, float] = {}


def set_dependencies(event_bus, auth_manager) -> None:
    global _event_bus, _auth_manager
    _event_bus = event_bus
    _auth_manager = auth_manager


def _validate_ticket(ticket: str) -> None:
    """Validate a one-time SSE ticket. Purges expired tickets, checks existence, deletes on use."""
    now = time.time()
    expired = [t for t, ts in _tickets.items() if now - ts > _TICKET_TTL]
    for t in expired:
        del _tickets[t]

    if ticket not in _tickets:
        raise HTTPException(status_code=401, detail="Invalid or expired ticket")

    del _tickets[ticket]


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


@router.post("/ticket")
async def create_sse_ticket(
    _username: str = Depends(get_verify_token),
) -> dict:
    """Issue a short-lived one-time ticket for SSE authentication."""
    ticket = str(uuid.uuid4())
    _tickets[ticket] = time.time()
    return {"ticket": ticket}


@router.get("/downloads")
async def sse_downloads(ticket: str = Query(...)):
    """SSE endpoint for download queue updates."""
    _validate_ticket(ticket)
    if _event_bus is None:
        return _not_ready()
    return _sse_response("download_queue")


@router.get("/ocr")
async def sse_ocr(ticket: str = Query(...)):
    """SSE endpoint for OCR queue updates."""
    _validate_ticket(ticket)
    if _event_bus is None:
        return _not_ready()
    return _sse_response("ocr_queue")

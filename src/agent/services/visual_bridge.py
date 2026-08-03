"""Publishes agent state and wake word events to the Nowva display page.

Best-effort fire-and-forget: events are queued and pushed to the display
server's /ingest websocket by a background task that reconnects on
failure. A missing display server never affects the voice pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

DISPLAY_INGEST_URL = "ws://localhost:8768/ingest"
RECONNECT_SECONDS = 3.0
QUEUE_MAXSIZE = 32


class VisualBridge:
    def __init__(self, url: str = DISPLAY_INGEST_URL) -> None:
        self._url = url
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._sender_loop())

    def send(self, event: dict) -> None:
        try:
            self._queue.put_nowait(json.dumps(event))
        except asyncio.QueueFull:
            pass

    def send_agent_state(self, state: str) -> None:
        self.send({"type": "agent_state", "state": state})

    def send_wake_event(self, event: str) -> None:
        self.send({"type": "wake_word", "event": event})

    async def aclose(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _sender_loop(self) -> None:
        import websockets

        while True:
            try:
                async with websockets.connect(self._url, open_timeout=3) as ws:
                    logger.info("[VISUAL] Connected to display server")
                    while True:
                        payload = await self._queue.get()
                        await ws.send(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(RECONNECT_SECONDS)

"""Streams composed display frames to the Nowva display page over WebSocket.

Replaces the fullscreen OpenCV window: the pose process pushes JPEG
frames to the display server's /ingest endpoint and the browser renders
them. Sending is best-effort from a background thread — the pipeline
loop never blocks on the network, and a missing display server just
means no frames are shown.
"""

from __future__ import annotations

import json
import queue
import threading
import time

import cv2
import numpy as np

DISPLAY_INGEST_URL = "ws://localhost:8768/ingest"
JPEG_QUALITY = 82
RECONNECT_SECONDS = 2.0

_sink: LiveStreamSink | None = None


def get_display_sink() -> "LiveStreamSink":
    global _sink
    if _sink is None:
        _sink = LiveStreamSink()
    return _sink


class LiveStreamSink:
    def __init__(self, url: str = DISPLAY_INGEST_URL) -> None:
        self._url = url
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._running = True
        self._thread = threading.Thread(
            target=self._sender_loop, name="display-stream", daemon=True,
        )
        self._thread.start()

    def show(self, frame_bgr: np.ndarray) -> None:
        """Encode and queue a frame, dropping the previous one if unsent."""
        ok, encoded = cv2.imencode(
            ".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
        )
        if not ok:
            return
        self._put_latest(encoded.tobytes())

    def send_event(self, event: dict) -> None:
        self._put_latest(json.dumps(event))

    def close(self) -> None:
        self._running = False

    def _put_latest(self, item) -> None:
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                pass

    def _sender_loop(self) -> None:
        from websockets.sync.client import connect

        while self._running:
            try:
                with connect(self._url, open_timeout=3) as ws:
                    while self._running:
                        try:
                            item = self._queue.get(timeout=0.5)
                        except queue.Empty:
                            continue
                        ws.send(item)
            except Exception:
                time.sleep(RECONNECT_SECONDS)

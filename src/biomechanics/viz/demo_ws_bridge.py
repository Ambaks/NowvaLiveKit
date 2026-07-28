"""WebSocket + HTTP bridge for the Three.js choreography viewer."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import numpy as np
import websockets
from websockets.http11 import Request, Response

from biomechanics.diagnosis.demo_builder import DemoData

_VIEWER_HTML = Path(__file__).with_name("demo_viewer.html")
_CHOREOGRAPHER_JS = Path(__file__).with_name("choreographer.mjs")

DEMO_WS_PORT = 8767
LIVE_POSE_JOINT_COUNT = 19

MORPH_IN_SECONDS = 0.8
MORPH_OUT_SECONDS = 0.8
YOYO_TRAVEL_SECONDS = 1.2
YOYO_HOLD_SECONDS = 0.25
SETTLE_SECONDS = 0.4
FINAL_HOLD_SECONDS = 1.0

HIGHLIGHT_JOINTS: dict[str, tuple[int, ...]] = {
    "narrow_stance": (13, 14, 15, 16, 17, 18),
    "narrow_foot_angle": (15, 16, 17, 18),
    "knee_track_cue": (13, 14),
    "weight_shift_cue": (5, 6, 11, 12),
    "depth_cue_unfamiliar": (11, 12, 13, 14),
}


def _mediapipe_to_viewer_coords(points: np.ndarray) -> np.ndarray:
    """Transform MediaPipe world coords → viewer coords.

    MediaPipe: X=subject's left, Y=down, Z=toward camera.
    Viewer: vis_x=mp_z, vis_y=-mp_y, vis_z=-mp_x.
    Same convention as biomechanics.diagnosis.bridge, which transforms
    the demo pose stack — live poses must match or the skeleton renders
    upside down when the choreography morphs back to the live pose.
    """
    return np.column_stack([points[:, 2], -points[:, 1], -points[:, 0]])


def _ground_and_center_stack(pose_stack: np.ndarray) -> np.ndarray:
    """Ground feet to Y=0 and center horizontally, using pose 0 as reference."""
    stack = pose_stack.copy()
    ref = stack[0]
    foot_y = float(ref[[15, 16, 17, 18], 1].min())
    hip_mid_x = (ref[11, 0] + ref[12, 0]) / 2
    hip_mid_z = (ref[11, 2] + ref[12, 2]) / 2
    stack[:, :, 1] -= foot_y
    stack[:, :, 0] -= hip_mid_x
    stack[:, :, 2] -= hip_mid_z
    return stack


def _serialize_demo_data(demo_data: DemoData) -> dict[str, Any]:
    grounded = _ground_and_center_stack(demo_data.pose_stack)
    pose_list = grounded.tolist()
    cues_list = [cue.model_dump() for cue in demo_data.cues]
    return {
        "type": "init",
        "pose_stack": pose_list,
        "cues": cues_list,
        "highlight_map": HIGHLIGHT_JOINTS,
        "timing": {
            "morphIn": MORPH_IN_SECONDS,
            "morphOut": MORPH_OUT_SECONDS,
            "yoyoTravel": YOYO_TRAVEL_SECONDS,
            "yoyoHold": YOYO_HOLD_SECONDS,
            "settle": SETTLE_SECONDS,
            "finalHold": FINAL_HOLD_SECONDS,
        },
    }


class DemoWSBridge:
    """Serves the Three.js viewer over HTTP and bridges demo events over WebSocket."""

    def __init__(self, port: int = DEMO_WS_PORT) -> None:
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: Any = None
        self._clients: set[websockets.WebSocketServerProtocol] = set()
        self._done_event = threading.Event()
        self._started_event = threading.Event()
        self._html_bytes: bytes | None = None
        self._js_bytes: bytes | None = None
        self._init_payload: str | None = None
        self._event_backlog: list[str] = []
        self._latest_live_payload: str | None = None

    def start(self) -> None:
        self._done_event.clear()
        self._started_event.clear()
        self._event_backlog.clear()
        self._latest_live_payload = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        self._html_bytes = _VIEWER_HTML.read_bytes()
        self._js_bytes = _CHOREOGRAPHER_JS.read_bytes()
        self._server = await websockets.serve(
            self._ws_handler,
            "0.0.0.0",
            self._port,
            process_request=self._http_handler,
        )
        await self._server.wait_closed()

    async def _http_handler(
        self, connection: Any, request: Request,
    ) -> Response | None:
        if request.path == "/" or request.path == "/index.html":
            return Response(
                200,
                "OK",
                websockets.Headers({"Content-Type": "text/html; charset=utf-8"}),
                self._html_bytes,
            )
        if request.path == "/choreographer.mjs":
            return Response(
                200,
                "OK",
                websockets.Headers({"Content-Type": "text/javascript; charset=utf-8"}),
                self._js_bytes,
            )
        if request.path == "/ws":
            return None
        return Response(404, "Not Found", websockets.Headers(), b"not found")

    async def _ws_handler(self, ws: websockets.WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        try:
            if self._init_payload is not None:
                await ws.send(self._init_payload)
                # Replay events sent before this client connected, so a
                # slow-loading browser doesn't miss demo_start/demo_cue.
                for payload in list(self._event_backlog):
                    await ws.send(payload)
            if self._latest_live_payload is not None:
                await ws.send(self._latest_live_payload)
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "started":
                    self._started_event.set()
                elif msg.get("type") == "done":
                    self._done_event.set()
        finally:
            self._clients.discard(ws)

    def send_init(self, demo_data: DemoData) -> None:
        payload = json.dumps(_serialize_demo_data(demo_data))
        self._init_payload = payload
        self._broadcast(payload)

    def send_event(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event)
        self._event_backlog.append(payload)
        self._broadcast(payload)

    def send_live_pose(self, points: np.ndarray) -> None:
        """Stream one live skeleton frame; kept out of the event backlog."""
        if points.shape[0] < LIVE_POSE_JOINT_COUNT:
            return
        viewer_points = _mediapipe_to_viewer_coords(
            points[:LIVE_POSE_JOINT_COUNT].astype(np.float64)
        )
        grounded = _ground_and_center_stack(viewer_points[np.newaxis])
        payload = json.dumps({"type": "live_pose", "points": grounded[0].tolist()})
        self._latest_live_payload = payload
        self._broadcast(payload)

    def wait_started(self, timeout: float | None = None) -> bool:
        return self._started_event.wait(timeout=timeout)

    def wait_done(self, timeout: float | None = None) -> bool:
        return self._done_event.wait(timeout=timeout)

    def _broadcast(self, payload: str) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._async_broadcast(payload), self._loop)

    async def _async_broadcast(self, payload: str) -> None:
        if not self._clients:
            return
        await asyncio.gather(
            *(client.send(payload) for client in self._clients),
            return_exceptions=True,
        )

    def stop(self) -> None:
        if self._server is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._server.close)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._loop = None
        self._thread = None
        self._server = None
        self._clients.clear()

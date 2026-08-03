"""Condensed workout replay for the promo video screen capture.

Same event vocabulary as scripts/demos/replay_workout_display.py but the
whole flow runs in ~15 seconds: boot, menu, quick-exercise setup, four
reps with cues, set scores. No browser is opened; the capture harness
connects its own headless page. Run: ./venv/bin/python rack-video/replay_condensed.py
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visual.display_server import DISPLAY_PORT, DisplayServer

INGEST_URL = f"ws://localhost:{DISPLAY_PORT}/ingest"
FRAME_INTERVAL_S = 1 / 20
REP_INTERVAL_S = 1.3

SET_SCORES = {"depth": 0.84, "trunk_control": 0.72, "knee_tracking": 0.79,
              "symmetry": 0.85, "tempo": 0.80}


def _stick_figure_frame(t: float) -> bytes:
    h, w = 720, 1280
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (14, 9, 9)
    squat = 0.5 - 0.5 * math.cos(t * 2 * math.pi / REP_INTERVAL_S)
    cx, ground = w // 2, 640
    hip_y = int(420 + squat * 130)
    knee_y = int((hip_y + ground) / 2)
    head_y = hip_y - 190
    color = (250, 139, 167)
    cv2.circle(img, (cx, head_y), 34, color, 3)
    cv2.line(img, (cx, head_y + 34), (cx, hip_y), color, 3)
    for side in (-1, 1):
        cv2.line(img, (cx, hip_y), (cx + side * 55, knee_y), color, 3)
        cv2.line(img, (cx + side * 55, knee_y), (cx + side * 45, ground), color, 3)
        cv2.line(img, (cx, head_y + 70), (cx + side * 90, head_y + 130), color, 3)
    ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpeg.tobytes() if ok else b""


async def _frame_pump(ws) -> None:
    t = 0.0
    while True:
        await ws.send(_stick_figure_frame(t))
        await asyncio.sleep(FRAME_INTERVAL_S)
        t += FRAME_INTERVAL_S


async def _run(ws) -> None:
    async def send(event: dict, pause: float = 0.0) -> None:
        await ws.send(json.dumps(event))
        if pause:
            await asyncio.sleep(pause)

    await send({"type": "boot", "label": "warming up", "progress": 1.0})
    await send({"type": "agent_state", "state": "idle"}, pause=1.2)
    await send({"type": "menu", "action": "show"}, pause=1.0)
    await send({"type": "agent_state", "state": "listening"}, pause=0.2)
    await send({"type": "menu", "action": "select", "choice": "quick_exercise"},
               pause=1.0)
    await send({
        "type": "setup", "action": "show", "exercise": "Barbell Back Squat",
        "params": {"sets": 3, "reps": None, "weight_lbs": None,
                   "rest_seconds": None},
    }, pause=1.2)
    await send({
        "type": "setup", "action": "complete", "exercise": "Barbell Back Squat",
        "params": {"sets": 3, "reps": 8, "weight_lbs": 185, "rest_seconds": 120},
    }, pause=1.4)

    await send({
        "type": "workout", "action": "start",
        "exercise": "Barbell Back Squat",
        "total_sets": 3, "target_reps": 8, "weight_lbs": 185,
    }, pause=1.3)

    depth_names = ["Below Parallel", "Parallel", "Below Parallel", "Below Parallel"]
    pump = asyncio.ensure_future(_frame_pump(ws))
    try:
        for rep in range(1, 5):
            await send({
                "type": "rep", "rep_number": rep, "set_number": 1,
                "depth_class_name": depth_names[rep - 1],
                "is_clean": rep != 2,
                "faults": [],
            })
            if rep == 2:
                await send({"type": "cue", "key": "knees_out",
                            "text": "Knees out!", "kind": "correction"})
            if rep == 4:
                await send({"type": "cue", "key": "great_depth",
                            "text": "Great depth!", "kind": "positive"})
            await asyncio.sleep(REP_INTERVAL_S)

        await send({
            "type": "set_summary", "set_number": 1,
            "total_reps": 4, "clean_reps": 3,
            "avg_depth": 99, "depth_consistency": 3.8,
            "fault_summary": {"knee_valgus": {"count": 1, "avg_severity": 0.5}},
        })
        await send({
            "type": "set_scores", "set_number": 1,
            "mean_score": round(sum(SET_SCORES.values()) / 5, 3),
            "per_dimension": SET_SCORES,
            "best_rep": 4, "worst_rep": 2,
        })
        await asyncio.sleep(3.0)
    finally:
        pump.cancel()


async def main() -> None:
    server = DisplayServer()
    if not server.start():
        raise SystemExit("display server failed to start (port in use?)")
    print("READY", flush=True)
    await asyncio.sleep(2.5)  # let the capture page connect and reveal
    async with websockets.connect(INGEST_URL, max_size=8 * 1024 * 1024) as ws:
        await _run(ws)
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

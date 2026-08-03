"""Replays a scripted workout against the Nowva display page.

Starts the display server, opens the browser, and feeds it fake pose
frames plus the full workout event sequence (reps, cues, set reports,
rest, completion) so the workout UI can be previewed without running
the real pipeline. Run from the repo root: ./venv/bin/python
scripts/demos/replay_workout_display.py
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import webbrowser
from pathlib import Path

import cv2
import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from visual.display_server import DISPLAY_PORT, DisplayServer

INGEST_URL = f"ws://localhost:{DISPLAY_PORT}/ingest"
FRAME_INTERVAL_S = 1 / 20
REP_INTERVAL_S = 2.6
REST_SECONDS = 18

SET_SCORES = [
    {"depth": 0.71, "trunk_control": 0.64, "knee_tracking": 0.58,
     "symmetry": 0.82, "tempo": 0.77},
    {"depth": 0.84, "trunk_control": 0.72, "knee_tracking": 0.79,
     "symmetry": 0.85, "tempo": 0.80},
    {"depth": 0.88, "trunk_control": 0.81, "knee_tracking": 0.86,
     "symmetry": 0.87, "tempo": 0.84},
]


def _stick_figure_frame(t: float) -> bytes:
    """Dark frame with a squatting stick figure so body.pose activates."""
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


async def _send_event(ws, event: dict, pause: float = 0.0) -> None:
    await ws.send(json.dumps(event))
    if pause:
        await asyncio.sleep(pause)


async def _run_menu(ws) -> None:
    send = lambda e, pause=0.0: _send_event(ws, e, pause)

    await send({"type": "boot", "label": "warming up", "progress": 1.0})
    await send({"type": "agent_state", "state": "idle"}, pause=2.0)

    # --- main menu → quick exercise setup (no pose frames yet) ---
    await send({"type": "menu", "action": "show"}, pause=6.0)
    await send({"type": "agent_state", "state": "listening"}, pause=2.0)
    await send({"type": "menu", "action": "select", "choice": "quick_exercise"},
               pause=1.6)
    await send({
        "type": "setup", "action": "show", "exercise": "Barbell Back Squat",
        "params": {"sets": 3, "reps": None, "weight_lbs": None,
                   "rest_seconds": None},
    }, pause=6.0)
    await send({
        "type": "setup", "action": "complete", "exercise": "Barbell Back Squat",
        "params": {"sets": 3, "reps": 8, "weight_lbs": 185, "rest_seconds": 120},
    }, pause=6.0)


async def _run_workout(ws) -> None:
    send = lambda e, pause=0.0: _send_event(ws, e, pause)

    await send({
        "type": "workout", "action": "start",
        "exercise": "Barbell Back Squat",
        "total_sets": 3, "target_reps": 8, "weight_lbs": 185,
    }, pause=2.0)

    depth_names = ["Below Parallel", "Below Parallel", "Parallel",
                   "Below Parallel", "Below Parallel", "Parallel",
                   "Below Parallel", "Below Parallel"]
    for set_number in range(1, 4):
        for rep in range(1, 9):
            if set_number == 1 and rep == 4:
                await send({"type": "shallow_rep",
                            "depth_class_name": "Half"}, pause=REP_INTERVAL_S)
            await send({
                "type": "rep", "rep_number": rep, "set_number": set_number,
                "depth_class_name": depth_names[rep - 1],
                "is_clean": not (set_number == 1 and rep in (3, 6)),
                "faults": [],
            })
            if set_number == 1 and rep == 3:
                await send({"type": "cue", "key": "knees_out",
                            "text": "Knees out!", "kind": "correction"})
            if rep == 5:
                await send({"type": "cue", "key": "great_depth",
                            "text": "Great depth!", "kind": "positive"})
            await asyncio.sleep(REP_INTERVAL_S)

        await send({
            "type": "set_summary", "set_number": set_number,
            "total_reps": 8, "clean_reps": 6 + (set_number - 1),
            "avg_depth": 96 + set_number * 3,
            "depth_consistency": round(4.8 - set_number, 1),
            "fault_summary": {} if set_number == 3 else {
                "knee_valgus": {"count": 3 - set_number, "avg_severity": 0.5},
            },
        })
        await send({
            "type": "set_scores", "set_number": set_number,
            "mean_score": round(
                sum(SET_SCORES[set_number - 1].values()) / 5, 3),
            "per_dimension": SET_SCORES[set_number - 1],
            "best_rep": 5, "worst_rep": 3,
        })
        if set_number < 3:
            await send({"type": "rest", "action": "start",
                        "seconds": REST_SECONDS}, pause=REST_SECONDS)
            await send({"type": "rest", "action": "end"}, pause=1.5)

    await send({"type": "workout", "action": "complete"})
    print("Replay finished — complete screen is up. Ctrl+C to exit.")
    await asyncio.sleep(3600)


async def main() -> None:
    server = DisplayServer()
    if not server.start():
        raise SystemExit("display server failed to start (port in use?)")
    webbrowser.open(f"http://localhost:{DISPLAY_PORT}")
    await asyncio.sleep(2.0)  # let the page connect and reveal
    async with websockets.connect(INGEST_URL, max_size=8 * 1024 * 1024) as ws:
        # frames start with the workout — the camera view supersedes the
        # menu/setup screens, so pumping earlier would hide them
        pump: asyncio.Future | None = None
        try:
            await _run_menu(ws)
            pump = asyncio.ensure_future(_frame_pump(ws))
            await _run_workout(ws)
        finally:
            if pump is not None:
                pump.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

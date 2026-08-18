"""Setup-card replay for the promo: menu -> quick-exercise glow -> Regular Squat
card with placeholder dots held long enough for the user's dictation audio,
then the fill cascade and LOCKED IN hold. Captured headless by capture_setup.mjs.
Run: ./venv/bin/python rack-video/replay_setup.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visual.display_server import DISPLAY_PORT, DisplayServer

INGEST_URL = f"ws://localhost:{DISPLAY_PORT}/ingest"


async def _run(ws) -> None:
    async def send(event: dict, pause: float = 0.0) -> None:
        await ws.send(json.dumps(event))
        if pause:
            await asyncio.sleep(pause)

    await send({"type": "boot", "label": "warming up", "progress": 1.0})
    await send({"type": "agent_state", "state": "idle"}, pause=0.8)
    await send({"type": "menu", "action": "show"}, pause=1.2)
    await send({"type": "agent_state", "state": "listening"}, pause=0.2)
    await send({"type": "menu", "action": "select", "choice": "quick_exercise"},
               pause=1.8)
    await send({
        "type": "setup", "action": "show", "exercise": "Regular Squat",
        "params": {"sets": None, "reps": None, "weight_lbs": None,
                   "rest_seconds": None},
    }, pause=6.2)
    await send({
        "type": "setup", "action": "complete", "exercise": "Regular Squat",
        "params": {"sets": 2, "reps": 5, "weight_lbs": 0, "rest_seconds": 20},
    }, pause=4.5)


async def main() -> None:
    server = DisplayServer()
    if not server.start():
        raise SystemExit("display server failed to start (port in use?)")
    print("READY", flush=True)
    await asyncio.sleep(2.5)
    async with websockets.connect(INGEST_URL, max_size=8 * 1024 * 1024) as ws:
        await _run(ws)
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

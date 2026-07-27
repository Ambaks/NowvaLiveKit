#!/usr/bin/env python3
"""Replay the coaching demo choreography in the Three.js browser viewer.

Uses the same session loading and diagnosis as replay_demo_choreography.py,
but displays in the Three.js viewer via WebSocket instead of cv2.

Usage:
    python scripts/demos/replay_demo_threejs.py
    python scripts/demos/replay_demo_threejs.py path/to/session.json
    python scripts/demos/replay_demo_threejs.py --cycles 3
"""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.viz.demo_renderer import (
    MORPH_IN_SECONDS,
    MORPH_OUT_SECONDS,
    YOYO_HOLD_SECONDS,
    YOYO_TRAVEL_SECONDS,
    SETTLE_SECONDS,
    FINAL_HOLD_SECONDS,
)
from biomechanics.viz.demo_ws_bridge import DemoWSBridge

from replay_demo_choreography import _resolve_last_session, _load_session, _build_demo


def _play_threejs(demo, cycles_per_cue: int, port: int) -> None:
    yoyo_period = 2.0 * (YOYO_TRAVEL_SECONDS + YOYO_HOLD_SECONDS)
    dwell = cycles_per_cue * yoyo_period

    bridge = DemoWSBridge(port=port)
    bridge.start()
    time.sleep(0.5)

    url = f"http://localhost:{port}"
    print(f"\n  Opening {url} ...")
    webbrowser.open(url)
    time.sleep(2.0)

    bridge.send_init(demo)
    time.sleep(0.5)

    print("  Sending demo_start")
    bridge.send_event({"type": "demo_start"})
    time.sleep(MORPH_IN_SECONDS + 0.2)

    for i, cue in enumerate(demo.cues):
        print(f"  Sending demo_cue {i}: {cue.cause_id} — {cue.magnitude_text}")
        bridge.send_event({"type": "demo_cue", "cue_index": i})
        time.sleep(SETTLE_SECONDS + dwell)

    print("  Sending demo_end")
    bridge.send_event({"type": "demo_end"})

    print("  Waiting for morph-out to finish...")
    done = bridge.wait_done(timeout=SETTLE_SECONDS + FINAL_HOLD_SECONDS + MORPH_OUT_SECONDS + 3.0)
    if done:
        print("  Demo complete.")
    else:
        print("  Timed out waiting for done signal.")

    print("\n  Press Enter to stop the server and exit...")
    try:
        input()
    except KeyboardInterrupt:
        pass

    bridge.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay coaching demo in Three.js browser viewer",
    )
    parser.add_argument(
        "session", nargs="?", default=None,
        help="Path to .session.json (default: latest)",
    )
    parser.add_argument(
        "--cycles", type=int, default=2,
        help="Yoyo cycles per cue (default: 2)",
    )
    parser.add_argument(
        "--port", type=int, default=8767,
        help="WebSocket server port (default: 8767)",
    )
    args = parser.parse_args()

    recordings_dir = Path(__file__).parent.parent / "recordings"
    if args.session:
        session_path = Path(args.session)
    else:
        session_path = _resolve_last_session(recordings_dir)
        if session_path is None:
            print("ERROR: No saved session found. Run a full capture first.")
            sys.exit(1)

    payload = _load_session(session_path)
    athlete_params = payload.get("athlete_params")
    if not athlete_params:
        print("ERROR: Session has no athlete params")
        sys.exit(1)

    print(f"Session: {session_path}")
    print(f"Reps: {len(payload['replay_reps'])}")
    print()

    demo, info = _build_demo(
        payload["replay_reps"], athlete_params, payload["baseline"],
    )

    print(f"  Confidence: {info['confidence']:.0%}")
    print(f"  Symptoms: {info['symptoms']}")
    print(f"  Tier-1 causes: {info['causes']}")
    print(f"  Worst rep: {info['worst_rep']} (score {info['worst_score']}/100)")
    print(f"  Mean score: {info['mean_score']}/100")

    if demo is None:
        print("\nNo immediate causes — nothing to animate.")
        return

    print(f"\nDemo cues ({len(demo.cues)}):")
    for cue in demo.cues:
        print(f"  [{cue.cue_index}] {cue.cause_id} — {cue.magnitude_text}")

    print("\nPlaying choreography in browser...")
    _play_threejs(demo, args.cycles, args.port)


if __name__ == "__main__":
    main()

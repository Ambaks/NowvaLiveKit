#!/usr/bin/env python3
"""
Simulate a full squat workout through the IPC pipeline.

This script acts as a fake biomechanics pipeline, sending the same messages
that the real pose_estimation_process.py would send. It connects to main.py's
IPC server and plays through a realistic 3-set x 5-rep squat workout with
faults, rep counts, and set summaries.

Usage:
    Standalone (no main.py needed — plays audio through speakers):
       venv/bin/python scripts/simulate_squat_workout.py --standalone
       venv/bin/python scripts/simulate_squat_workout.py --standalone --fast

    Through main.py (requires main.py running in workout mode):
       venv/bin/python scripts/simulate_squat_workout.py

    Direct to voice agent (skip main.py, voice agent must be in workout mode):
       venv/bin/python scripts/simulate_squat_workout.py --direct
"""

import argparse
import asyncio
import random
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agent.core.ipc_communication import IPCClient, IPCServer

# ── Squat cue dictionary (mirrors cue_cache.py SQUAT_CUES) ──────────────

SQUAT_CUES = {
    "knees_out": "knees_out", "chest_up": "chest_up", "deeper": "deeper",
    "heels_down": "heels_down", "even_it_out": "even_it_out",
    "slow_down": "slow_down", "brace": "brace",
    "good_rep": "good_rep", "great_depth": "great_depth",
    "strong": "strong", "clean": "clean", "perfect": "perfect",
}
for i in range(1, 21):
    SQUAT_CUES[f"rep_{i}"] = f"rep_{i}"

# ── Fault scenarios ──────────────────────────────────────────────────────

FAULT_SCENARIOS = [
    {"fault_type": "knee_valgus", "severity": "moderate", "severity_score": 1.8,
     "message": "Knees caving in — push knees out", "cue": "knees_out"},
    {"fault_type": "forward_lean", "severity": "mild", "severity_score": 1.0,
     "message": "Slight forward lean — stay tall", "cue": "chest_up"},
    {"fault_type": "depth", "severity": "mild", "severity_score": 0.8,
     "message": "Depth is a bit shallow — get deeper", "cue": "deeper"},
    None,  # clean rep (no fault)
    None,  # clean rep
]

DEPTH_CATEGORIES = ["below_parallel", "parallel", "parallel", "half", "below_parallel"]
POSITIVE_CUES = ["good_rep", "great_depth", "strong", "clean", "perfect"]


def send(client: IPCClient, msg: dict, label: str = ""):
    """Send a message and print it."""
    tag = f" ({label})" if label else ""
    print(f"  >> {msg['type']}{tag}")
    client.send_message(msg)


def simulate_workout(client: IPCClient, fast: bool = False):
    """Run a simulated 3-set x 5-rep squat workout."""
    pause = 0.5 if fast else 1.5  # time between events
    rep_pause = 1.0 if fast else 3.0  # time between reps (simulates rep duration)

    # ── Phase 1: Cache cues ──────────────────────────────────────────
    print("\n═══ PHASE 1: CACHE CUES ═══")
    send(client, {
        "type": "cache_cues",
        "exercise_name": "Barbell Back Squat",
        "cues": SQUAT_CUES,
    }, f"{len(SQUAT_CUES)} cues")

    print("  Waiting for TTS generation...")
    time.sleep(6 if not fast else 3)  # give time for TTS to finish

    # ── Phase 2: Pipeline status ─────────────────────────────────────
    send(client, {
        "type": "pipeline_status",
        "status": "running",
        "latency_ms": {"capture": 12.3, "pose": 45.2, "ik": 8.1, "faults": 5.4},
    })
    time.sleep(pause)

    # ── Phase 3: Sets ────────────────────────────────────────────────
    for set_num in range(1, 4):
        print(f"\n═══ SET {set_num} of 3 ═══")
        time.sleep(pause)

        set_faults = []

        for rep in range(1, 6):
            print(f"\n  ── Rep {rep} ──")
            time.sleep(rep_pause)

            # Maybe trigger a fault mid-rep
            fault_scenario = random.choice(FAULT_SCENARIOS)
            is_clean = fault_scenario is None

            if fault_scenario:
                send(client, {
                    "type": "fault",
                    "fault_type": fault_scenario["fault_type"],
                    "severity": fault_scenario["severity"],
                    "severity_score": fault_scenario["severity_score"],
                    "message": fault_scenario["message"],
                    "cue": fault_scenario["cue"],
                    "rep_number": rep,
                }, fault_scenario["fault_type"])
                set_faults.append(fault_scenario)
                time.sleep(pause)

            # Rep complete
            depth = random.choice(DEPTH_CATEGORIES)
            send(client, {
                "type": "rep_complete",
                "rep_number": rep,
                "max_depth_angle": round(random.uniform(85, 120), 1),
                "depth_category": depth,
                "faults_in_rep": [fault_scenario["fault_type"]] if fault_scenario else [],
                "rep_duration_ms": random.randint(2000, 3500),
                "is_clean": is_clean,
            }, f"{depth}, {'clean' if is_clean else 'faulted'}")

            # Rep count cue
            time.sleep(0.3)
            send(client, {"type": "play_cue", "cue": f"rep_{rep}"}, f"rep_{rep}")

            # Positive cue for clean reps
            if is_clean:
                time.sleep(0.3)
                cue = random.choice(POSITIVE_CUES)
                send(client, {"type": "play_cue", "cue": cue}, cue)

        # Set complete
        time.sleep(pause * 2)
        print(f"\n  ── Set {set_num} Summary ──")

        # Build fault summary
        fault_summary = {}
        for f in set_faults:
            ft = f["fault_type"]
            if ft not in fault_summary:
                fault_summary[ft] = {"count": 0, "total_severity": 0.0}
            fault_summary[ft]["count"] += 1
            fault_summary[ft]["total_severity"] += f["severity_score"]
        for data in fault_summary.values():
            data["avg_severity"] = round(data["total_severity"] / data["count"], 2)

        clean_reps = 5 - len(set_faults)
        send(client, {
            "type": "set_complete",
            "set_number": set_num,
            "total_reps": 5,
            "avg_depth": round(random.uniform(95, 110), 1),
            "depth_consistency": round(random.uniform(2, 8), 1),
            "clean_reps": clean_reps,
            "fault_summary": fault_summary,
        }, f"{clean_reps}/5 clean")

        if set_num < 3:
            rest = 5 if not fast else 2
            print(f"\n  Rest {rest}s between sets...")
            time.sleep(rest)

    print("\n═══ WORKOUT COMPLETE ═══")
    print("All 3 sets simulated. The voice agent should have spoken cues throughout.")


def run_direct_mode(fast: bool):
    """
    Direct mode: starts its own coaching IPC server and waits for the voice agent
    to connect. Use this to test without main.py running.
    """
    print("DIRECT MODE — acting as coaching IPC server on /tmp/nowva_coaching.sock")
    print("Start the voice agent and enter workout mode, then it will connect here.\n")

    server = IPCServer(socket_path="/tmp/nowva_coaching.sock")

    # Start server in background (blocks until client connects)
    def run_server():
        server.start()
        # Don't call listen() — we're only sending, not receiving

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    print("Waiting for voice agent to connect...")
    while not server.client_socket:
        time.sleep(0.5)
    print("Voice agent connected!\n")

    # Create a duck-typed "client" that uses the server's send_message
    class ServerAsSender:
        def send_message(self, msg):
            server.send_message(msg)

    simulate_workout(ServerAsSender(), fast=fast)
    time.sleep(3)
    server.stop()


def run_normal_mode(fast: bool):
    """
    Normal mode: connects to main.py's IPC server on /tmp/nowva_ipc.sock
    (acts as the pose estimation process).
    """
    print("NORMAL MODE — connecting to main.py IPC server on /tmp/nowva_ipc.sock")
    print("Make sure main.py is running and in workout mode.\n")

    client = IPCClient(socket_path="/tmp/nowva_ipc.sock")
    print("Connecting to IPC server...")

    if not client.connect(timeout=15):
        print("ERROR: Could not connect. Is main.py running in workout mode?")
        sys.exit(1)

    print("Connected!\n")
    simulate_workout(client, fast=fast)
    time.sleep(2)
    client.disconnect()


def play_pcm_audio(pcm_bytes: bytes):
    """Play PCM audio (24kHz 16-bit mono) through speakers using ffplay or afplay."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
        # Write a minimal WAV header + PCM data
        import struct
        sample_rate = 24000
        num_channels = 1
        bits_per_sample = 16
        data_size = len(pcm_bytes)
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        # WAV header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # chunk size
        f.write(struct.pack("<H", 1))   # PCM format
        f.write(struct.pack("<H", num_channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bits_per_sample))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm_bytes)

    try:
        subprocess.run(["afplay", wav_path], check=True, timeout=5)
    except FileNotFoundError:
        try:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", wav_path],
                check=True, timeout=5,
            )
        except FileNotFoundError:
            print("    (no audio player found — install ffplay or use macOS afplay)")
    except subprocess.TimeoutExpired:
        pass
    finally:
        Path(wav_path).unlink(missing_ok=True)


def run_standalone_mode(fast: bool):
    """
    Standalone mode: pre-caches TTS audio via OpenAI, then simulates a workout
    playing the cached cues through your speakers. No main.py or voice agent needed.
    """
    from agent.services.audio_cue_service import AudioCueService, CUE_TEXT_MAP

    print("STANDALONE MODE — generates TTS audio and plays through speakers")
    print("No main.py or voice agent needed. Just listen!\n")

    svc = AudioCueService()

    # Phase 1: Cache cues
    print("═══ PHASE 1: PRE-GENERATING TTS AUDIO ═══")
    print(f"  Generating {len(SQUAT_CUES)} cues via OpenAI TTS API...")

    start = time.time()
    asyncio.run(svc.cache_cues(SQUAT_CUES))
    elapsed = time.time() - start

    cached = len(svc.cache)
    print(f"  Cached {cached} cues in {elapsed:.1f}s")
    if cached == 0:
        print("\n  ERROR: No cues were cached. Check your OPENAI_API_KEY in .env")
        sys.exit(1)

    total_bytes = sum(len(v) for v in svc.cache.values())
    print(f"  Total audio: {total_bytes:,} bytes ({total_bytes / 48000:.1f}s at 24kHz)")

    pause = 0.3 if fast else 1.0
    rep_pause = 0.8 if fast else 2.5

    # Phase 2: Simulate workout
    for set_num in range(1, 4):
        print(f"\n═══ SET {set_num} of 3 ═══")
        time.sleep(pause)

        set_faults = []

        for rep in range(1, 6):
            print(f"\n  ── Rep {rep} ──")
            time.sleep(rep_pause)

            # Maybe trigger a fault
            fault_scenario = random.choice(FAULT_SCENARIOS)
            is_clean = fault_scenario is None

            if fault_scenario:
                cue_key = fault_scenario["cue"]
                cue_text = CUE_TEXT_MAP.get(cue_key, cue_key)
                print(f"    FAULT: {fault_scenario['fault_type']} ({fault_scenario['severity']})")
                audio = svc.get_cue_audio(cue_key)
                if audio:
                    print(f"    Playing cached cue: \"{cue_text}\"")
                    play_pcm_audio(audio)
                else:
                    print(f"    [cache miss — would fall back to voice agent: \"{cue_text}\"]")
                set_faults.append(fault_scenario)
                time.sleep(0.3)

            # Rep count cue
            depth = random.choice(DEPTH_CATEGORIES)
            rep_cue_key = f"rep_{rep}"
            rep_text = CUE_TEXT_MAP.get(rep_cue_key, str(rep))
            print(f"    Rep complete ({depth}) — playing: \"{rep_text}\"")
            audio = svc.get_cue_audio(rep_cue_key)
            if audio:
                play_pcm_audio(audio)

            # Positive cue for clean reps
            if is_clean:
                time.sleep(0.2)
                pos_cue = random.choice(POSITIVE_CUES)
                pos_text = CUE_TEXT_MAP.get(pos_cue, pos_cue)
                print(f"    Clean rep! Playing: \"{pos_text}\"")
                audio = svc.get_cue_audio(pos_cue)
                if audio:
                    play_pcm_audio(audio)

        # Set summary
        clean_count = 5 - len(set_faults)
        print(f"\n  ── Set {set_num} Summary: {clean_count}/5 clean reps ──")
        if set_faults:
            fault_types = [f["fault_type"] for f in set_faults]
            print(f"    Faults: {', '.join(fault_types)}")
        else:
            print("    Perfect set!")

        if set_num < 3:
            rest = 2 if fast else 5
            print(f"\n  Rest {rest}s...")
            time.sleep(rest)

    print("\n═══ WORKOUT COMPLETE ═══")
    print("All 3 sets simulated with cached audio cue playback.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a squat workout via IPC")
    parser.add_argument("--direct", action="store_true",
                        help="Direct mode: act as coaching IPC server (skip main.py)")
    parser.add_argument("--standalone", action="store_true",
                        help="Standalone mode: generate TTS and play through speakers (no IPC)")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode: shorter pauses between events")
    args = parser.parse_args()

    try:
        if args.standalone:
            run_standalone_mode(args.fast)
        elif args.direct:
            run_direct_mode(args.fast)
        else:
            run_normal_mode(args.fast)
    except KeyboardInterrupt:
        print("\n\nSimulation cancelled.")

# Biomechanics Pipeline — Implementation Specification v2

## Integrated with NowvaLiveKit

**Target:** `src/biomechanics/` within the existing NowvaLiveKit project
**Runtime:** Python 3.11+ on macOS ARM64 (M2 MacBook Pro)
**Goal:** Replace the placeholder pose estimation subprocess with a validated, layered biomechanics pipeline that feeds real-time coaching data to the existing Nova voice agent via the existing IPC system.

---

## 0. Existing Architecture (What We Already Have)

Before building anything, understand what exists and what we're integrating into:

### 0.1 Voice Agent (`src/agents/voice_agent.py`)
- **4000-line** LiveKit-based voice agent using OpenAI Realtime API
- Modes: `onboarding`, `main_menu`, `workout`, `program_creation`
- `start_workout()` function tool switches to workout mode → triggers pose estimation
- `end_workout()` function tool logs progress to DB → stops pose estimation
- Workout prompt (`src/agents/prompts/workout_prompt.py`) already defines coaching personality
- The voice agent **already speaks coaching cues** — we just need to feed it the right data

### 0.2 IPC System (`src/core/ipc_communication.py`)
- UNIX domain socket at `/tmp/nowva_ipc.sock`
- `IPCServer` runs in `main.py`, `IPCClient` runs in the pose estimation subprocess
- Already sends messages: `{"type": "rep_count", "value": N}` and `{"type": "feedback", "value": "knees caving"}`
- **We keep this exact protocol** and extend it with richer biomechanics data

### 0.3 Workout Session (`src/core/workout_session.py`)
- `WorkoutSession` class with `ExerciseProgress` and `SetProgress` dataclasses
- Tracks current exercise, current set, reps, progress
- `mark_set_complete()`, `advance_to_next_set()`, `get_progress_summary()`
- Stored in `AgentState` and saved to JSON file

### 0.4 Main Orchestrator (`src/main.py`)
- Monitors `AgentState` file for mode changes
- When workout mode detected: starts IPC server → launches pose estimation subprocess
- When workout ends: terminates subprocess, cleans up

### 0.5 Existing Pose Process (`src/pose/pose_estimation_process.py`)
- **This is what we're replacing.** Currently sends placeholder rep counts and fake feedback.
- Uses RTMPose + stereo triangulation from `src/biomechanics/` week folders
- We replace this with the full layered pipeline

### 0.6 Existing Biomechanics (`src/biomechanics/complete_pipeline.py`)
- Earlier prototype: RTMPose → stereo triangulation → IK → muscle force prediction
- Has working RTMPose inference and stereo reconstruction code
- We refactor and extend this into the layered architecture

---

## 1. Project Structure

The biomechanics pipeline lives inside the existing project structure. **No separate package, no separate pyproject.toml.**

```
NowvaLiveKit/
├── src/
│   ├── main.py                        # EXISTING — update to launch new pipeline
│   ├── agents/
│   │   ├── voice_agent.py             # EXISTING — no changes needed
│   │   └── prompts/
│   │       └── workout_prompt.py      # EXISTING — minor update for fault data format
│   ├── core/
│   │   ├── agent_state.py             # EXISTING — no changes
│   │   ├── ipc_communication.py       # EXISTING — extend message protocol
│   │   ├── workout_session.py         # EXISTING — add biomechanics fields
│   │   └── session_logger.py          # EXISTING — no changes
│   ├── pose/
│   │   └── pose_estimation_process.py # REPLACE — new pipeline entry point
│   │
│   └── biomechanics/                  # ← ALL NEW CODE GOES HERE
│       ├── __init__.py
│       ├── pipeline.py                # Pipeline orchestrator
│       ├── config.py                  # Pipeline configuration
│       │
│       ├── pose/                      # Layer 1: 2D Pose Estimation
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── rtmpose.py             # RTMPose ONNX (from existing code)
│       │   └── mediapipe_fallback.py   # Zero-setup fallback
│       │
│       ├── triangulation/             # Layer 2: 3D Reconstruction
│       │   ├── __init__.py
│       │   ├── stereo.py              # Stereo triangulation (from existing code)
│       │   ├── calibration.py
│       │   └── sim_cameras.py         # Simulated multi-cam for single-webcam testing
│       │
│       ├── kinematics/                # Layer 3: Inverse Kinematics
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── analytical_ik.py       # Lightweight geometric solver
│       │   ├── opensim_ik.py          # OpenSim solver (production)
│       │   └── subject_scaling.py
│       │
│       ├── faults/                    # Layer 4: Fault Detection
│       │   ├── __init__.py
│       │   ├── rule_engine.py
│       │   ├── rep_counter.py
│       │   ├── fault_types.py
│       │   ├── tcn_model.py           # TCN for dynamic faults (v2)
│       │   └── rules/
│       │       ├── __init__.py
│       │       ├── depth.py
│       │       ├── symmetry.py
│       │       ├── heel_rise.py
│       │       ├── forward_lean.py
│       │       └── knee_valgus.py
│       │
│       ├── coaching/                  # Layer 5: Coaching Integration
│       │   ├── __init__.py
│       │   ├── cue_cache.py           # Pre-cached audio cue system
│       │   ├── ipc_bridge.py          # Bridge to existing IPC system
│       │   └── session_tracker.py     # Biomechanics session data
│       │
│       ├── viz/                       # Visualization
│       │   ├── __init__.py
│       │   ├── overlay_2d.py
│       │   └── dashboard.py           # OpenCV debug dashboard
│       │
│       └── utils/
│           ├── __init__.py
│           ├── types.py               # Shared Pydantic data types
│           ├── timing.py              # Performance profiling
│           └── geometry.py            # Geometric math utilities
│
├── tests/
│   └── test_biomechanics/
│       ├── conftest.py
│       ├── test_pose.py
│       ├── test_kinematics.py
│       ├── test_faults.py
│       ├── test_rep_counter.py
│       ├── test_pipeline.py
│       └── fixtures/
│           ├── sample_keypoints.json
│           ├── sample_3d_points.json
│           └── sample_angles.json
│
├── scripts/
│   ├── download_models.py
│   ├── benchmark_pipeline.py
│   └── generate_synthetic.py
│
└── config/
    └── biomechanics.yaml              # Pipeline configuration
```

---

## 2. Dependencies

**Add to the existing `requirements.txt`** — do NOT create a separate pyproject.toml:

```
# Biomechanics Pipeline (append to existing requirements.txt)
onnxruntime>=1.17
mediapipe>=0.10.9
pydantic>=2.5
pyyaml>=6.0
torch>=2.2
```

OpenCV is already in the project. NumPy, scipy are likely already present.

### OpenSim (optional, for production IK):
```bash
conda install -c opensim-org opensim=4.5
```
The system MUST work without OpenSim — analytical IK is the default.

---

## 3. IPC Message Protocol Extension

The existing IPC sends simple messages. We extend the protocol while maintaining backward compatibility.

### Existing Messages (keep working):
```json
{"type": "status", "value": "initialized"}
{"type": "rep_count", "value": 3}
{"type": "feedback", "value": "knees caving"}
{"type": "error", "value": "camera not found"}
```

### New Extended Messages:

```python
# Real-time frame data (sent every frame or every N frames)
{
    "type": "frame_data",
    "joint_angles": {
        "hip_flexion_r": 85.2,
        "hip_flexion_l": 83.7,
        "knee_flexion_r": 92.1,
        "knee_flexion_l": 90.5,
        "ankle_dorsiflexion_r": 28.3,
        "ankle_dorsiflexion_l": 27.9,
        "trunk_flexion": 32.1
    },
    "fps": 28.5,
    "frame_index": 1423
}

# Fault detected (sent when fault fires, with deduplication)
{
    "type": "fault",
    "fault_type": "knee_valgus",
    "severity": "moderate",           # none | mild | moderate | severe
    "severity_score": 2.1,            # 0.0–3.0
    "message": "Knees tracking inward — push knees out",
    "cue": "knees_out",               # Key for cached audio cue
    "rep_number": 3
}

# Rep completed (sent when rep counter detects rep boundary)
{
    "type": "rep_complete",
    "rep_number": 3,
    "max_depth_angle": 95.2,
    "depth_category": "parallel",     # quarter | half | parallel | below_parallel
    "faults_in_rep": ["forward_lean"],
    "rep_duration_ms": 2340
}

# Set summary (sent when set ends — pause > threshold)
{
    "type": "set_complete",
    "set_number": 2,
    "total_reps": 8,
    "avg_depth": 93.5,
    "depth_consistency": 2.1,         # std dev of depth across reps
    "faults_summary": {
        "knee_valgus": {"count": 2, "avg_severity": 1.5},
        "forward_lean": {"count": 1, "avg_severity": 1.0}
    }
}

# Cue cache request (sent before each set to pre-cache audio)
{
    "type": "cache_cues",
    "exercise_name": "Barbell Back Squat",
    "cues": {
        "knees_out": "Push your knees out!",
        "chest_up": "Chest up, stay tight!",
        "deeper": "Get deeper, break parallel!",
        "heels_down": "Heels down!",
        "even_it_out": "Even it out, balance both sides!",
        "good_rep": "Nice rep!",
        "great_depth": "Great depth!"
    }
}

# Pipeline status updates
{
    "type": "pipeline_status",
    "status": "running",              # initializing | running | paused | error
    "latency_ms": {
        "pose": 8.2,
        "triangulation": 1.5,
        "ik": 4.1,
        "faults": 0.9,
        "total": 14.7
    }
}
```

---

## 4. Pre-Cached Audio Cue System

**This is the key latency optimization.** Instead of generating TTS in real-time when a fault fires, we pre-generate and cache all possible coaching cues BEFORE the set begins.

### 4.1 Architecture

```
Set starts
    ↓
Pipeline sends "cache_cues" message via IPC
    ↓
Voice agent (or a dedicated audio service) receives cue list
    ↓
For each cue, generate TTS audio using OpenAI TTS API
    ↓
Store audio buffers in memory (dict[cue_key] → audio_bytes)
    ↓
When fault detected → pipeline sends "fault" with cue key
    ↓
Audio service plays cached audio immediately (~5ms)
```

### 4.2 `coaching/cue_cache.py`

```python
"""
Pre-cached audio cue system for ultra-low-latency coaching feedback.

Instead of generating TTS on every fault detection (100-500ms latency),
we pre-generate all possible cues for the current exercise BEFORE the
set begins. When a fault fires, we play the cached audio immediately.

Cache lifecycle:
1. Exercise starts → generate cue set based on exercise type
2. Before first set → send cache_cues message via IPC
3. Voice agent pre-generates TTS for each cue
4. During set → fault detected → play cached cue by key (~5ms)
5. Between sets → refresh cache if exercise changes

The cue texts are exercise-aware. A squat gets "knees out" and "deeper",
while a deadlift would get "hips through" and "flat back". The cache
is rebuilt when the exercise changes.
"""

from typing import Dict, Optional

# Cue libraries per exercise category
SQUAT_CUES = {
    # Corrections
    "knees_out": "Push your knees out!",
    "chest_up": "Chest up, stay tight!",
    "deeper": "Get deeper!",
    "heels_down": "Heels down!",
    "even_it_out": "Even it out!",
    "slow_down": "Control the descent!",
    "brace": "Brace your core!",
    # Positive reinforcement
    "good_rep": "Nice rep!",
    "great_depth": "Great depth!",
    "strong": "Strong!",
    "clean": "Clean rep!",
    "perfect": "Perfect form!",
    # Rep counting (pre-cache numbers 1-20)
    **{f"rep_{i}": str(i) for i in range(1, 21)},
}

DEADLIFT_CUES = {
    "hips_through": "Drive your hips through!",
    "flat_back": "Keep your back flat!",
    "chest_up": "Chest up!",
    "lockout": "Lock it out!",
    "slow_down": "Control it down!",
    "good_rep": "Nice rep!",
    "strong": "Strong pull!",
    **{f"rep_{i}": str(i) for i in range(1, 21)},
}

# Default cues for unknown exercises
DEFAULT_CUES = {
    "good_rep": "Nice rep!",
    "chest_up": "Chest up!",
    "brace": "Brace your core!",
    "slow_down": "Control the movement!",
    "strong": "Strong!",
    **{f"rep_{i}": str(i) for i in range(1, 21)},
}

# Map exercise categories to cue libraries
EXERCISE_CUE_MAP = {
    "squat": SQUAT_CUES,
    "back_squat": SQUAT_CUES,
    "front_squat": SQUAT_CUES,
    "goblet_squat": SQUAT_CUES,
    "deadlift": DEADLIFT_CUES,
    "romanian_deadlift": DEADLIFT_CUES,
    "sumo_deadlift": DEADLIFT_CUES,
}


class CueCache:
    """Manages pre-cached coaching cues for the current exercise."""

    def __init__(self):
        self.current_exercise: Optional[str] = None
        self.cues: Dict[str, str] = {}
        self.last_cue_time: float = 0.0
        self.min_cue_gap: float = 2.0  # seconds between cues

    def prepare_for_exercise(self, exercise_name: str) -> Dict[str, str]:
        """Get the cue set for an exercise. Returns dict to send via IPC."""
        normalized = exercise_name.lower().replace(" ", "_")

        # Find matching cue library
        cues = DEFAULT_CUES.copy()
        for key, cue_set in EXERCISE_CUE_MAP.items():
            if key in normalized:
                cues = cue_set.copy()
                break

        self.current_exercise = exercise_name
        self.cues = cues
        return cues

    def get_cue_for_fault(self, fault_type: str, timestamp: float) -> Optional[str]:
        """Get the cached cue key for a fault type, respecting rate limiting."""
        if timestamp - self.last_cue_time < self.min_cue_gap:
            return None  # Rate limited

        # Map fault types to cue keys
        fault_to_cue = {
            "knee_valgus": "knees_out",
            "forward_lean": "chest_up",
            "depth": "deeper",
            "heel_rise": "heels_down",
            "bilateral_asymmetry": "even_it_out",
            "back_rounding": "chest_up",
        }

        cue_key = fault_to_cue.get(fault_type)
        if cue_key and cue_key in self.cues:
            self.last_cue_time = timestamp
            return cue_key

        return None

    def get_rep_cue(self, rep_number: int) -> Optional[str]:
        """Get the cue key for a rep count announcement."""
        key = f"rep_{rep_number}"
        if key in self.cues:
            return key
        return None

    def get_positive_cue(self) -> Optional[str]:
        """Get a positive reinforcement cue for a clean rep."""
        import random
        positive_keys = [k for k in self.cues if k in
                        ("good_rep", "great_depth", "strong", "clean", "perfect")]
        return random.choice(positive_keys) if positive_keys else None
```

### 4.3 How the Voice Agent Receives and Caches

The voice agent side needs a small update. When it receives a `cache_cues` IPC message, it pre-generates TTS audio for each cue text using the OpenAI Realtime API's TTS capabilities (which it already has access to). When a `fault` message arrives with a `cue` key, it plays the pre-cached audio buffer instead of generating new speech.

**Implementation approach in the voice agent:**
- On `cache_cues` message → call OpenAI TTS for each cue text → store `dict[cue_key] → audio_bytes`
- On `fault` message with `cue` key → look up cached audio → play immediately
- On `rep_complete` message → play cached rep number audio + optional positive cue
- Cache is stored in memory — no disk I/O during playback

---

## 5. IPC Bridge (`coaching/ipc_bridge.py`)

This module bridges the biomechanics pipeline to the existing IPC system.

```python
"""
Bridge between the biomechanics pipeline and the existing NowvaLiveKit
IPC system (UNIX domain sockets).

This module handles:
1. Sending pipeline output to the voice agent via IPCClient
2. Receiving control messages from the voice agent (pause, resume, end)
3. Sending cache_cues before each set
4. Rate-limiting and deduplicating fault messages
5. Managing the cue cache lifecycle

The bridge does NOT own the IPC connection — it receives an IPCClient
instance from the pipeline entry point (pose_estimation_process.py).
"""

import time
from typing import Dict, Optional, List
from collections import defaultdict

# Import from existing codebase
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.ipc_communication import IPCClient

from biomechanics.coaching.cue_cache import CueCache
from biomechanics.utils.types import (
    FaultEvent, RepData, JointAngles, PipelineFrame
)


class IPCBridge:
    """Bridges biomechanics pipeline output to the voice agent via IPC."""

    def __init__(self, ipc_client: IPCClient):
        self.ipc = ipc_client
        self.cue_cache = CueCache()

        # Rate limiting
        self.last_fault_send: Dict[str, float] = defaultdict(float)
        self.fault_cooldown = 3.0  # seconds between same fault type

        # Frame data throttling — don't send every frame
        self.frame_send_interval = 10  # Send frame data every N frames
        self.frame_counter = 0

    def prepare_exercise(self, exercise_name: str):
        """Prepare cue cache for a new exercise and send to voice agent."""
        cues = self.cue_cache.prepare_for_exercise(exercise_name)
        self.ipc.send_message({
            "type": "cache_cues",
            "exercise_name": exercise_name,
            "cues": cues
        })

    def send_frame_data(self, frame: PipelineFrame):
        """Send frame data to voice agent (throttled)."""
        self.frame_counter += 1
        if self.frame_counter % self.frame_send_interval != 0:
            return

        if frame.joint_angles:
            self.ipc.send_message({
                "type": "frame_data",
                "joint_angles": frame.joint_angles.as_dict(),
                "fps": 1000.0 / sum(frame.latency_ms.values()) if frame.latency_ms else 0,
                "frame_index": frame.frame_index
            })

    def send_fault(self, fault: FaultEvent):
        """Send fault to voice agent with deduplication and rate limiting."""
        now = time.time()

        # Rate limit per fault type
        if now - self.last_fault_send[fault.fault_type] < self.fault_cooldown:
            return

        # Get cached cue key
        cue_key = self.cue_cache.get_cue_for_fault(fault.fault_type, now)

        self.ipc.send_message({
            "type": "fault",
            "fault_type": fault.fault_type,
            "severity": fault.severity.value,
            "severity_score": fault.severity_score,
            "message": fault.message,
            "cue": cue_key,
            "rep_number": fault.rep_number
        })

        self.last_fault_send[fault.fault_type] = now

    def send_rep_complete(self, rep: RepData):
        """Send rep completion to voice agent."""
        # Send rep data
        self.ipc.send_message({
            "type": "rep_complete",
            "rep_number": rep.rep_number,
            "max_depth_angle": rep.max_depth_angle,
            "depth_category": self._depth_category(rep.max_depth_angle),
            "faults_in_rep": [f.fault_type for f in rep.faults],
            "rep_duration_ms": int((rep.end_time - rep.start_time) * 1000)
        })

        # Also send legacy rep_count for backward compatibility
        self.ipc.send_message({
            "type": "rep_count",
            "value": rep.rep_number
        })

        # Send rep count audio cue
        cue_key = self.cue_cache.get_rep_cue(rep.rep_number)
        if cue_key:
            self.ipc.send_message({
                "type": "play_cue",
                "cue": cue_key
            })

        # If clean rep, send positive reinforcement
        if not rep.faults:
            positive_cue = self.cue_cache.get_positive_cue()
            if positive_cue:
                self.ipc.send_message({
                    "type": "play_cue",
                    "cue": positive_cue
                })

    def send_set_complete(self, set_number: int, reps: List[RepData]):
        """Send set summary to voice agent."""
        if not reps:
            return

        # Compute summary stats
        depths = [r.max_depth_angle for r in reps]
        all_faults = [f for r in reps for f in r.faults]
        fault_summary = defaultdict(lambda: {"count": 0, "total_severity": 0.0})

        for f in all_faults:
            fault_summary[f.fault_type]["count"] += 1
            fault_summary[f.fault_type]["total_severity"] += f.severity_score

        for k in fault_summary:
            fault_summary[k]["avg_severity"] = (
                fault_summary[k]["total_severity"] / fault_summary[k]["count"]
            )

        self.ipc.send_message({
            "type": "set_complete",
            "set_number": set_number,
            "total_reps": len(reps),
            "avg_depth": sum(depths) / len(depths),
            "depth_consistency": float(
                (sum((d - sum(depths)/len(depths))**2 for d in depths) / len(depths)) ** 0.5
            ),
            "faults_summary": dict(fault_summary)
        })

    def send_pipeline_status(self, status: str, latency: Dict[str, float]):
        """Send pipeline health status."""
        self.ipc.send_message({
            "type": "pipeline_status",
            "status": status,
            "latency_ms": latency
        })

    @staticmethod
    def _depth_category(angle: float) -> str:
        if angle >= 100: return "below_parallel"
        if angle >= 90: return "parallel"
        if angle >= 60: return "half"
        return "quarter"
```

---

## 6. Updated Pipeline Entry Point

Replace `src/pose/pose_estimation_process.py` with a new version that runs the full biomechanics pipeline.

```python
"""
Biomechanics Pipeline Process
Replaces the old pose_estimation_process.py with the full layered pipeline.

Launched as a subprocess by main.py when workout mode starts.
Communicates with the voice agent via the existing IPC system.
"""

import sys
import os
import time
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ipc_communication import IPCClient
from biomechanics.pipeline import BiomechanicsPipeline
from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.config import load_pipeline_config


def run_biomechanics_pipeline(
    cam0_id: int = 0,
    cam1_id: int = 1,
    config_path: str = None,
    exercise_name: str = "Barbell Back Squat"
):
    """
    Run the full biomechanics pipeline as a subprocess.

    This is called by main.py when workout mode starts.
    Connects to the existing IPC server and sends real-time
    coaching data to the voice agent.
    """
    print("\n=== Biomechanics Pipeline Starting ===")

    # Connect to IPC server (started by main.py)
    ipc_client = IPCClient()
    if not ipc_client.connect(timeout=10):
        print("Failed to connect to IPC server. Exiting.")
        return

    # Load config
    config = load_pipeline_config(config_path)

    # Initialize pipeline
    try:
        pipeline = BiomechanicsPipeline(config)
        bridge = IPCBridge(ipc_client)

        # Pre-cache coaching cues for the first exercise
        bridge.prepare_exercise(exercise_name)

        ipc_client.send_message({"type": "status", "value": "initialized"})
        bridge.send_pipeline_status("running", {})

        print(f"Pipeline initialized. Running at target {config.target_fps} FPS")
        print("Press Ctrl+C to stop\n")

    except Exception as e:
        print(f"Pipeline initialization failed: {e}")
        ipc_client.send_message({"type": "error", "value": str(e)})
        ipc_client.disconnect()
        return

    # Main processing loop
    try:
        while True:
            result = pipeline.process_frame()

            # Send data to voice agent via IPC bridge
            bridge.send_frame_data(result)

            # Send faults
            for fault in result.faults:
                bridge.send_fault(fault)

            # Send rep completions
            if result.rep_data:
                bridge.send_rep_complete(result.rep_data)

            # Check for set completion
            # (pipeline.session_tracker handles set boundary detection)

            # Throttle to target FPS
            total_ms = sum(result.latency_ms.values())
            target_ms = 1000.0 / config.target_fps
            if total_ms < target_ms:
                time.sleep((target_ms - total_ms) / 1000.0)

    except KeyboardInterrupt:
        print("\nPipeline stopped by user")
    except Exception as e:
        print(f"\nPipeline error: {e}")
        ipc_client.send_message({"type": "error", "value": str(e)})
    finally:
        pipeline.release()
        bridge.send_pipeline_status("stopped", {})
        ipc_client.disconnect()
        print("Biomechanics pipeline stopped")


if __name__ == "__main__":
    cam0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cam1 = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    exercise = sys.argv[3] if len(sys.argv) > 3 else "Barbell Back Squat"

    run_biomechanics_pipeline(cam0_id=cam0, cam1_id=cam1, exercise_name=exercise)
```

---

## 7. Shared Data Types (`utils/types.py`)

Same Pydantic models as v1 spec (Keypoint2D, Skeleton2D, MultiViewPose, Point3D, Skeleton3D, JointAngles, FaultSeverity, FaultEvent, RepData, SessionState, PipelineFrame). See v1 implementation spec Section 3 — those types are unchanged.

---

## 8. Layer Implementations

### Layers 1–4 are identical to v1 spec:
- **Layer 1 (Pose):** RTMPose ONNX + MediaPipe fallback. Same as v1 Section 4.2.
- **Layer 2 (Triangulation):** Stereo geometry + simulated multi-cam. Same as v1 Section 4.3. Additionally, refactor code from the existing `src/biomechanics/complete_pipeline.py` — the `StereoReconstructor` class is already functional.
- **Layer 3 (IK):** Analytical solver + OpenSim. Same as v1 Section 4.4. The existing `SimpleLowerBodyIK` in `src/biomechanics/` can be used as a starting point for the analytical solver.
- **Layer 4 (Faults):** Rule engine + rep counter. Same as v1 Section 4.5.

### Layer 5 (Coaching) — CHANGED from v1:

**v1 used pyttsx3 for TTS and a standalone LLM coach. v2 replaces both:**

- `coaching/cue_cache.py` — Pre-cached audio cues (see Section 4 above)
- `coaching/ipc_bridge.py` — Bridge to existing IPC (see Section 5 above)
- `coaching/session_tracker.py` — Tracks set boundaries and generates summaries

**No pyttsx3. No standalone Anthropic client.** The voice agent already handles TTS (OpenAI Realtime) and can invoke Claude for analysis via its own function tools. We just feed it structured data.

---

## 9. Updates to Existing Files

### 9.1 `src/main.py` — Update subprocess launch

In the workout mode monitoring loop, update the subprocess launch to use the new pipeline:

```python
# BEFORE (old):
pose_script = Path(__file__).parent / 'pose' / 'pose_estimation_process.py'
self.pose_process = subprocess.Popen(
    [sys.executable, str(pose_script), str(cam0_id), str(cam1_id)],
    ...
)

# AFTER (new):
pose_script = Path(__file__).parent / 'pose' / 'pose_estimation_process.py'
# Pass exercise name from workout session
exercise_name = "Barbell Back Squat"  # Get from workout session
self.pose_process = subprocess.Popen(
    [sys.executable, str(pose_script), str(cam0_id), str(cam1_id), exercise_name],
    ...
)
```

### 9.2 `src/main.py` — Handle new IPC message types

Extend the IPC message handler to process the richer message types:

```python
def handle_ipc_message(message):
    msg_type = message.get("type")

    if msg_type == "rep_complete":
        # Update workout session with real rep data
        rep_num = message["rep_number"]
        depth = message["depth_category"]
        print(f"[BIOMECH] Rep {rep_num} complete — {depth}")

    elif msg_type == "fault":
        # Log fault and relay cue key to voice agent
        print(f"[BIOMECH] Fault: {message['fault_type']} ({message['severity']})")

    elif msg_type == "set_complete":
        # Trigger voice agent to give set summary
        print(f"[BIOMECH] Set {message['set_number']} complete — {message['total_reps']} reps")

    elif msg_type == "cache_cues":
        # Pre-generate TTS audio for all cues
        # This is where the voice agent (or a TTS service) generates audio
        print(f"[BIOMECH] Caching {len(message['cues'])} audio cues for {message['exercise_name']}")

    elif msg_type == "play_cue":
        # Play a pre-cached audio cue immediately
        print(f"[BIOMECH] Play cue: {message['cue']}")

    # Backward-compatible handling
    elif msg_type == "rep_count":
        print(f"[BIOMECH] Rep count: {message['value']}")
    elif msg_type == "feedback":
        print(f"[BIOMECH] Feedback: {message['value']}")
```

### 9.3 Workout Prompt — Add fault data format documentation

The existing workout prompt already tells the agent to coach in real-time. We add a section describing the data format it will receive:

```python
# Addition to workout_prompt.py get_workout_prompt():

# Add after existing prompt text:
"""
# Real-Time Data Feed
You will receive structured data from the biomechanics system during the workout:
- **Rep counts** with depth quality (parallel, below parallel, etc.)
- **Form faults** with severity (mild, moderate, severe) and specific cue
- **Set summaries** with average depth and fault breakdown

When you receive a fault alert, deliver the coaching cue immediately and naturally.
When a rep completes, acknowledge the count. When a set completes, give a brief summary.

React to the data — don't narrate it. Say "Knees out!" not "The system detected knee valgus."
"""
```

---

## 10. Configuration (`config/biomechanics.yaml`)

```yaml
pipeline:
  target_fps: 30
  log_level: INFO
  single_camera_mode: true     # Set false when stereo cameras available

capture:
  source: webcam
  device_id: 0
  resolution: [1280, 720]

pose:
  backend: mediapipe            # mediapipe | rtmpose
  confidence_threshold: 0.3

triangulation:
  enabled: false                # Set true when stereo cameras available

kinematics:
  backend: analytical           # analytical | opensim

faults:
  depth:
    parallel: 90.0
    below_parallel: 100.0
  bilateral_asymmetry:
    mild: 5.0
    moderate: 10.0
    severe: 15.0
  heel_rise:
    threshold_cm: 2.0
  forward_lean:
    mild: 35.0
    moderate: 45.0
    severe: 55.0
  knee_valgus:
    mild: 5.0
    moderate: 10.0
    severe: 15.0

rep_detection:
  entry_threshold: 30.0
  min_rep_duration_frames: 20

coaching:
  min_cue_gap_seconds: 2.0
  set_timeout_seconds: 30.0     # Pause > this = new set
  cache_cues_before_set: true

ipc:
  frame_send_interval: 10       # Send frame data every N frames
  fault_cooldown_seconds: 3.0
```

---

## 11. Build Order

**Phase 1: Foundation**
1. Project structure under `src/biomechanics/`
2. `utils/types.py`, `utils/timing.py`, `utils/geometry.py`
3. `config.py` + `config/biomechanics.yaml`

**Phase 2: Pose + IK (single camera path)**
4. `pose/mediapipe_fallback.py` (working immediately)
5. `kinematics/analytical_ik.py`
6. `viz/overlay_2d.py` for visual verification
7. Tests for pose + IK

**Phase 3: Fault Detection**
8. `faults/fault_types.py`, `faults/rep_counter.py`
9. `faults/rule_engine.py` + all rules
10. Tests for faults

**Phase 4: Coaching + IPC Integration**
11. `coaching/cue_cache.py`
12. `coaching/ipc_bridge.py`
13. `coaching/session_tracker.py`
14. Update `src/pose/pose_estimation_process.py`
15. Update `src/main.py` IPC handler

**Phase 5: Pipeline Assembly**
16. `pipeline.py` connecting all layers
17. End-to-end integration test
18. `scripts/benchmark_pipeline.py`

**Phase 6: Stereo + RTMPose (when hardware ready)**
19. `triangulation/` modules (refactor from existing code)
20. `pose/rtmpose.py` (refactor from existing code)

**Phase 7: Advanced**
21. OpenSim IK integration
22. TCN training infrastructure
23. Web dashboard

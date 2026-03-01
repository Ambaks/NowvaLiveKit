# Biomechanics Pipeline — Implementation Specification

## For Claude Code: Build & Test on Apple Silicon (M2 MacBook Pro)

**Target:** `biomechanics/` folder at project root
**Runtime:** Python 3.11+ on macOS ARM64
**Goal:** Build the full 5-layer real-time biomechanics coaching pipeline as described in the Squat Rack Biomechanics System design document, adapted for local development and testing with webcam/video file input before deploying to production hardware.

---

## 1. Project Structure

```
biomechanics/
├── CLAUDE.md                      # Project-level instructions for Claude Code
├── pyproject.toml                 # Project config (use uv or pip)
├── README.md
├── .env.example
├── config/
│   ├── default.yaml               # Default pipeline config
│   ├── camera_sim.yaml            # Simulated multi-cam config for testing
│   └── models/
│       └── rajagopal_2016/        # OpenSim model files (downloaded)
│           ├── Rajagopal2016.osim
│           └── geometry/
├── biomechanics/
│   ├── __init__.py
│   ├── main.py                    # CLI entry point & orchestrator
│   ├── pipeline.py                # Pipeline orchestrator (connects all layers)
│   ├── config.py                  # Pydantic settings / YAML loader
│   │
│   ├── capture/                   # Camera input abstraction
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract CaptureSource
│   │   ├── webcam.py              # Single webcam capture (OpenCV)
│   │   ├── video_file.py          # Video file input (for offline testing)
│   │   └── multi_cam.py           # Multi-camera manager (sync simulation)
│   │
│   ├── pose/                      # Layer 1: 2D Pose Estimation
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract PoseEstimator
│   │   ├── rtmpose.py             # RTMPose via ONNX Runtime
│   │   ├── mediapipe_fallback.py  # MediaPipe fallback (easier setup)
│   │   └── models/                # Downloaded ONNX model files
│   │       └── .gitkeep
│   │
│   ├── triangulation/             # Layer 2: 3D Reconstruction
│   │   ├── __init__.py
│   │   ├── stereo.py              # OpenCV triangulation
│   │   ├── calibration.py         # Camera calibration utilities
│   │   └── sim_cameras.py         # Simulated multi-camera geometry
│   │
│   ├── kinematics/                # Layer 3: Inverse Kinematics
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract IKSolver
│   │   ├── opensim_ik.py          # OpenSim IK solver (production)
│   │   ├── analytical_ik.py       # Lightweight analytical IK (dev/fallback)
│   │   ├── subject_scaling.py     # Subject-specific model scaling
│   │   └── joint_angles.py        # Joint angle extraction & representation
│   │
│   ├── faults/                    # Layer 4: Fault Detection
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract FaultDetector
│   │   ├── rule_engine.py         # Rule-based geometric fault detectors
│   │   ├── tcn_model.py           # TCN architecture for dynamic faults
│   │   ├── rep_counter.py         # Rep detection via peak detection
│   │   ├── fault_types.py         # Fault type definitions & severity scales
│   │   └── rules/
│   │       ├── depth.py           # Squat depth achievement
│   │       ├── symmetry.py        # Bilateral asymmetry
│   │       ├── heel_rise.py       # Heel rise detection
│   │       ├── forward_lean.py    # Excessive forward lean
│   │       └── knee_valgus.py     # Knee valgus (rule v1, TCN v2)
│   │
│   ├── coaching/                  # Layer 5: Coaching Output
│   │   ├── __init__.py
│   │   ├── audio_cues.py          # Real-time audio feedback (TTS)
│   │   ├── llm_coach.py           # LLM-powered session analysis
│   │   ├── session.py             # Session state management
│   │   └── report.py              # Post-session report generation
│   │
│   ├── viz/                       # Visualization
│   │   ├── __init__.py
│   │   ├── overlay_2d.py          # 2D skeleton overlay on camera feed
│   │   ├── viewer_3d.py           # 3D skeleton viewer (matplotlib/open3d)
│   │   ├── dashboard.py           # Real-time metrics dashboard
│   │   └── web_ui.py              # FastAPI + WebSocket live dashboard
│   │
│   └── utils/
│       ├── __init__.py
│       ├── timing.py              # Performance profiling decorators
│       ├── logging.py             # Structured logging setup
│       ├── geometry.py            # Geometric math utilities
│       └── types.py               # Shared data types (Pydantic models)
│
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── test_pose/
│   │   ├── test_rtmpose.py
│   │   └── test_mediapipe.py
│   ├── test_triangulation/
│   │   ├── test_stereo.py
│   │   └── test_sim_cameras.py
│   ├── test_kinematics/
│   │   ├── test_analytical_ik.py
│   │   └── test_joint_angles.py
│   ├── test_faults/
│   │   ├── test_rule_engine.py
│   │   ├── test_rep_counter.py
│   │   └── test_depth.py
│   ├── test_pipeline/
│   │   └── test_end_to_end.py
│   └── fixtures/
│       ├── sample_keypoints.json  # Known-good 2D keypoints
│       ├── sample_3d_points.json  # Known-good 3D landmarks
│       └── sample_angles.json     # Known-good joint angles
│
├── scripts/
│   ├── download_models.py         # Download RTMPose ONNX + OpenSim model
│   ├── generate_synthetic.py      # Synthetic data generation via OpenSim
│   ├── calibrate_cameras.py       # Camera calibration utility
│   ├── run_on_video.py            # Offline analysis on video file
│   └── benchmark.py               # Latency benchmark per layer
│
└── notebooks/
    ├── 01_pose_exploration.ipynb
    ├── 02_triangulation_viz.ipynb
    ├── 03_ik_comparison.ipynb
    └── 04_fault_detection.ipynb
```

---

## 2. Environment & Dependencies

### 2.1 Python Environment Setup

```bash
# Use Python 3.11 — best compatibility with opensim + onnxruntime on ARM
python3.11 -m venv .venv
source .venv/bin/activate
```

### 2.2 Core Dependencies (pyproject.toml)

```toml
[project]
name = "biomechanics"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Core
    "numpy>=1.26",
    "scipy>=1.12",
    "opencv-python-headless>=4.9",     # Use headless in CI, full for local dev
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "pyyaml>=6.0",

    # Layer 1: Pose Estimation
    "onnxruntime>=1.17",               # Apple Silicon optimized
    "mediapipe>=0.10.9",               # Fallback pose estimator

    # Layer 3: Inverse Kinematics
    # opensim — install via conda: conda install -c opensim-org opensim
    # For dev without opensim, the analytical_ik.py fallback is used

    # Layer 4: Fault Detection
    "torch>=2.2",                      # MPS backend on Apple Silicon
    "torchvision>=0.17",

    # Layer 5: Coaching
    "anthropic>=0.40",                 # Claude API for LLM coaching
    "pyttsx3>=2.90",                   # Offline TTS for real-time cues

    # Visualization
    "matplotlib>=3.8",
    "fastapi>=0.109",
    "uvicorn>=0.27",
    "websockets>=12.0",
    "jinja2>=3.1",

    # Utilities
    "rich>=13.7",                      # Pretty console output
    "typer>=0.9",                      # CLI framework
    "structlog>=24.1",                 # Structured logging
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.2",
    "mypy>=1.8",
    "jupyter>=1.0",
    "ipykernel>=6.29",
]

[project.scripts]
biomechanics = "biomechanics.main:app"
```

### 2.3 OpenSim Installation (Conda)

OpenSim does not have a pip package for Apple Silicon. Install via conda:

```bash
# Create a conda env OR install into existing env
conda install -c opensim-org opensim=4.5
# Verify
python -c "import opensim; print(opensim.GetVersion())"
```

**If conda/opensim is unavailable**, the system must fall back to `analytical_ik.py` gracefully. All code must handle `ImportError` for opensim and route to the fallback solver. This is a hard requirement — the system must be testable without OpenSim installed.

### 2.4 RTMPose Model Download

The `scripts/download_models.py` script should download:

```
# RTMPose-m (COCO 17-keypoint, ONNX format)
# Source: https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose
# Direct ONNX: rtmpose-m_simcc-body7_pt-body7_420e-256x192.onnx
# Place in: biomechanics/pose/models/rtmpose_m.onnx

# Also download the Rajagopal2016 OpenSim model
# Source: https://simtk.org/projects/full_body
# Place in: config/models/rajagopal_2016/
```

---

## 3. Shared Data Types

All layers communicate through well-defined Pydantic models. This is the contract between layers.

### `biomechanics/utils/types.py`

```python
"""Shared data types for the biomechanics pipeline.

All inter-layer communication uses these types. Each layer receives
one type and produces another — no layer reaches into another layer's
internals.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
import numpy as np
from typing import Optional
import time


class Keypoint2D(BaseModel):
    """Single 2D keypoint from pose estimation."""
    x: float
    y: float
    confidence: float
    name: str

    model_config = {"arbitrary_types_allowed": True}


class Skeleton2D(BaseModel):
    """Full 2D skeleton from a single camera view."""
    keypoints: list[Keypoint2D]
    camera_id: int
    timestamp: float
    frame_index: int

    def to_numpy(self) -> np.ndarray:
        """Return (N, 3) array of [x, y, confidence]."""
        return np.array([[kp.x, kp.y, kp.confidence] for kp in self.keypoints])

    model_config = {"arbitrary_types_allowed": True}


class MultiViewPose(BaseModel):
    """2D poses from all camera views for a single time instant."""
    skeletons: list[Skeleton2D]
    timestamp: float
    frame_index: int


class Point3D(BaseModel):
    """Single 3D point in world coordinates (meters)."""
    x: float
    y: float
    z: float
    confidence: float
    name: str


class Skeleton3D(BaseModel):
    """Full 3D skeleton after triangulation."""
    landmarks: list[Point3D]
    timestamp: float
    frame_index: int

    def to_numpy(self) -> np.ndarray:
        """Return (N, 3) array of [x, y, z]."""
        return np.array([[lm.x, lm.y, lm.z] for lm in self.landmarks])

    model_config = {"arbitrary_types_allowed": True}


class JointAngles(BaseModel):
    """Joint angles from IK solver (degrees)."""
    hip_flexion_r: float = 0.0
    hip_flexion_l: float = 0.0
    hip_adduction_r: float = 0.0
    hip_adduction_l: float = 0.0
    knee_flexion_r: float = 0.0
    knee_flexion_l: float = 0.0
    ankle_dorsiflexion_r: float = 0.0
    ankle_dorsiflexion_l: float = 0.0
    trunk_flexion: float = 0.0
    trunk_lateral_bend: float = 0.0
    pelvis_tilt: float = 0.0
    timestamp: float = 0.0
    frame_index: int = 0

    def as_dict(self) -> dict[str, float]:
        return {k: v for k, v in self.model_dump().items()
                if k not in ("timestamp", "frame_index")}


class FaultSeverity(str, Enum):
    NONE = "none"            # 0 — no fault
    MILD = "mild"            # 1 — minor deviation
    MODERATE = "moderate"    # 2 — should correct
    SEVERE = "severe"        # 3 — injury risk


class FaultEvent(BaseModel):
    """A detected fault with type, severity, and context."""
    fault_type: str                          # e.g. "knee_valgus", "depth", "heel_rise"
    severity: FaultSeverity
    severity_score: float = 0.0              # Continuous 0.0–3.0
    message: str                             # Human-readable description
    joint_data: dict[str, float] = {}        # Relevant angle values
    timestamp: float = 0.0
    frame_index: int = 0
    rep_number: int = 0


class RepData(BaseModel):
    """Data for a single completed rep."""
    rep_number: int
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    max_depth_angle: float                   # Peak hip flexion
    faults: list[FaultEvent] = []
    joint_angle_series: list[JointAngles] = []


class SessionState(BaseModel):
    """Current state of a training session."""
    session_id: str
    start_time: float
    current_rep: int = 0
    reps: list[RepData] = []
    active_faults: list[FaultEvent] = []
    is_in_rep: bool = False


class PipelineFrame(BaseModel):
    """Complete output of one pipeline cycle — everything produced for a single frame."""
    frame_index: int
    timestamp: float
    skeletons_2d: Optional[MultiViewPose] = None
    skeleton_3d: Optional[Skeleton3D] = None
    joint_angles: Optional[JointAngles] = None
    faults: list[FaultEvent] = []
    rep_data: Optional[RepData] = None       # Set when a rep completes
    latency_ms: dict[str, float] = {}        # Per-layer latency

    model_config = {"arbitrary_types_allowed": True}
```

---

## 4. Layer-by-Layer Implementation Details

### 4.1 Capture Layer (`capture/`)

**Purpose:** Abstract camera input so the pipeline doesn't care whether input is a webcam, video file, or multi-camera rig.

```python
# base.py — Abstract interface
class CaptureSource(ABC):
    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray]:
        """Return (success, frame) — same interface as cv2.VideoCapture."""
        ...

    @abstractmethod
    def get_camera_matrix(self) -> np.ndarray:
        """Return 3x3 intrinsic camera matrix."""
        ...

    @abstractmethod
    def get_distortion_coeffs(self) -> np.ndarray:
        """Return distortion coefficients."""
        ...

    @property
    @abstractmethod
    def fps(self) -> float: ...

    @property
    @abstractmethod
    def resolution(self) -> tuple[int, int]: ...
```

**webcam.py**: Wraps `cv2.VideoCapture(0)`. Uses default/estimated intrinsics for M2 MacBook webcam. Provides a single-camera test path.

**video_file.py**: Wraps `cv2.VideoCapture(filepath)`. Supports frame-by-frame stepping and looping. Essential for reproducible testing.

**multi_cam.py**: For testing multi-camera triangulation without physical cameras:
- Takes a single video/webcam input
- Generates synthetic "second camera" views by applying known homography transforms
- Maintains simulated camera matrices with known extrinsic parameters
- This lets us test the full triangulation pipeline with a single webcam

### 4.2 Layer 1: Pose Estimation (`pose/`)

**RTMPose via ONNX Runtime** (`rtmpose.py`):

```python
class RTMPoseEstimator(PoseEstimator):
    """RTMPose inference via ONNX Runtime.

    Model: rtmpose-m with SimCC head, COCO 17-keypoint format.
    Expected latency on M2: ~8-12ms per frame.

    Keypoint order (COCO 17):
        0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear,
        5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow,
        9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip,
        13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle
    """

    KEYPOINT_NAMES = [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle"
    ]

    def __init__(self, model_path: str):
        import onnxruntime as ort
        # Use CoreML EP on macOS for best M2 performance, fall back to CPU
        providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, providers=providers)
        # ... preprocessing params from model metadata

    def estimate(self, frame: np.ndarray) -> Skeleton2D:
        # 1. Preprocess: resize to 256x192, normalize
        # 2. Run inference
        # 3. Decode SimCC output to keypoint coordinates
        # 4. Map back to original image coordinates
        # 5. Return Skeleton2D
        ...
```

**MediaPipe fallback** (`mediapipe_fallback.py`): Use `mediapipe.solutions.pose` as a zero-setup fallback. Map MediaPipe's 33 landmarks to COCO 17 format for pipeline compatibility. This ensures the full pipeline is testable even if RTMPose ONNX model isn't downloaded yet.

**Critical implementation notes:**
- Both estimators MUST return `Skeleton2D` with COCO 17 keypoint order
- Confidence threshold filtering: drop keypoints below 0.3 confidence
- The pose estimator does NOT do person detection — for v1, assume one person in frame. If using RTMPose, use a simple center-crop bounding box or integrate a lightweight detector.

### 4.3 Layer 2: 3D Triangulation (`triangulation/`)

**stereo.py** — Core triangulation logic:

```python
class StereoTriangulator:
    """Triangulate 3D points from multi-view 2D keypoints.

    Uses OpenCV's triangulatePoints with DLT algorithm.
    Requires calibrated camera intrinsics and extrinsics.
    """

    def __init__(self, camera_params: list[CameraParams]):
        self.cameras = camera_params
        # Precompute projection matrices: P = K @ [R|t]
        self.projection_matrices = [
            cam.intrinsic @ np.hstack([cam.rotation, cam.translation.reshape(3, 1)])
            for cam in camera_params
        ]

    def triangulate(self, multi_view: MultiViewPose) -> Skeleton3D:
        """Triangulate 3D skeleton from multi-view 2D detections.

        For each keypoint:
        1. Collect all views where confidence > threshold
        2. If 2+ views available, triangulate via DLT
        3. If only 1 view, use depth prior from previous frame
        4. Compute reprojection error as quality metric
        """
        ...
```

**sim_cameras.py** — Simulated multi-camera setup for single-webcam testing:

```python
class SimulatedMultiCam:
    """Generate synthetic multi-camera views from a single camera.

    Places 4 virtual cameras around a defined capture volume:
    - Front-left at 45°
    - Front-right at -45°
    - Rear-left at 135°
    - Rear-right at -135°

    For a single real camera input, generates plausible 2D projections
    from the other virtual camera positions using the 3D pose from
    the real camera (lifted via depth estimation or prior).
    """
    CAMERA_POSITIONS = {
        "front_left":  {"azimuth": 45,  "elevation": 15, "distance": 2.5},
        "front_right": {"azimuth": -45, "elevation": 15, "distance": 2.5},
        "rear_left":   {"azimuth": 135, "elevation": 15, "distance": 2.5},
        "rear_right":  {"azimuth": -135, "elevation": 15, "distance": 2.5},
    }
```

**calibration.py**: Camera calibration utilities. For testing, provide reasonable defaults for common webcams and the M2 MacBook built-in camera. Include a checkerboard calibration script for users who want accurate intrinsics.

### 4.4 Layer 3: Inverse Kinematics (`kinematics/`)

**Two IK solvers — the system must work with either:**

**analytical_ik.py** (always available, used for dev/testing):

```python
class AnalyticalIKSolver(IKSolver):
    """Lightweight geometric IK solver.

    Computes joint angles directly from 3D landmark positions using
    vector math. Less accurate than OpenSim but runs in <1ms and
    has zero external dependencies.

    Angles computed:
    - Hip flexion: angle between trunk vector and thigh vector
    - Knee flexion: angle between thigh vector and shank vector
    - Ankle dorsiflexion: angle between shank vector and foot vector
    - Trunk flexion: angle of trunk from vertical
    - Bilateral: all angles computed for left and right independently
    """

    def solve(self, skeleton: Skeleton3D) -> JointAngles:
        landmarks = {lm.name: np.array([lm.x, lm.y, lm.z])
                     for lm in skeleton.landmarks}

        # Hip flexion = angle between pelvis-to-shoulder and pelvis-to-knee
        # Knee flexion = angle at knee between hip-knee and knee-ankle vectors
        # etc. — pure vector angle calculations
        ...
```

**opensim_ik.py** (production solver, requires opensim package):

```python
class OpenSimIKSolver(IKSolver):
    """OpenSim inverse kinematics using Rajagopal 2016 model.

    IMPORTANT: This solver must be initialized with a subject-scaled model.
    Call scale_model() during onboarding before using solve().

    Expected latency: 15-50ms per frame on M2 (benchmark early!).
    If >30ms, consider the model distillation path.
    """

    def __init__(self, model_path: str):
        try:
            import opensim as osim
            self.model = osim.Model(model_path)
            self.model.initSystem()
            self.ik_tool = osim.InverseKinematicsSolver(...)
        except ImportError:
            raise ImportError(
                "OpenSim not installed. Install via conda: "
                "conda install -c opensim-org opensim=4.5\n"
                "Or use AnalyticalIKSolver as fallback."
            )

    def solve(self, skeleton: Skeleton3D) -> JointAngles:
        # 1. Map COCO keypoints to OpenSim marker positions
        # 2. Set marker positions on model
        # 3. Run IK solver for single frame
        # 4. Extract joint angles from solved state
        # 5. Return JointAngles
        ...
```

**subject_scaling.py**:

```python
class SubjectScaler:
    """Scale the Rajagopal model to match a specific person.

    Onboarding flow:
    1. User stands in neutral T-pose or anatomical position
    2. System captures 3D skeleton for ~3 seconds (180 frames at 60fps)
    3. Average segment lengths computed from stable frames
    4. OpenSim scaling tool adjusts model segments proportionally
    5. Scaled model saved to user profile directory

    Segment measurements used for scaling:
    - Shoulder width: left_shoulder ↔ right_shoulder
    - Upper arm: shoulder ↔ elbow
    - Forearm: elbow ↔ wrist
    - Torso: mid-shoulder ↔ mid-hip
    - Thigh: hip ↔ knee
    - Shank: knee ↔ ankle
    """
```

### 4.5 Layer 4: Fault Detection (`faults/`)

**fault_types.py** — Central fault definitions:

```python
class FaultType(str, Enum):
    DEPTH = "depth"
    BILATERAL_ASYMMETRY = "bilateral_asymmetry"
    HEEL_RISE = "heel_rise"
    FORWARD_LEAN = "forward_lean"
    KNEE_VALGUS = "knee_valgus"
    BACK_ROUNDING = "back_rounding"

# Thresholds (configurable via YAML)
DEFAULT_THRESHOLDS = {
    "depth": {
        "parallel": 90.0,         # degrees hip flexion for parallel
        "below_parallel": 100.0,  # degrees for below parallel
    },
    "bilateral_asymmetry": {
        "mild": 5.0,              # degrees difference
        "moderate": 10.0,
        "severe": 15.0,
    },
    "heel_rise": {
        "threshold_cm": 2.0,      # vertical ankle displacement
    },
    "forward_lean": {
        "mild": 35.0,             # degrees trunk from vertical
        "moderate": 45.0,
        "severe": 55.0,
    },
    "knee_valgus": {
        "mild": 5.0,              # degrees knee adduction
        "moderate": 10.0,
        "severe": 15.0,
    },
}
```

**rule_engine.py** — Orchestrates all rule-based detectors:

```python
class RuleEngine:
    """Runs all registered fault detectors on each frame's joint angles.

    Architecture:
    - Each rule in rules/ implements FaultRule with a single method:
      evaluate(angles: JointAngles, history: deque[JointAngles]) -> Optional[FaultEvent]
    - Rules are stateless — temporal context comes from the history buffer
    - RuleEngine maintains the history buffer and passes it to each rule
    """

    def __init__(self, config: dict):
        self.rules: list[FaultRule] = [
            DepthRule(config.get("depth", {})),
            SymmetryRule(config.get("bilateral_asymmetry", {})),
            HeelRiseRule(config.get("heel_rise", {})),
            ForwardLeanRule(config.get("forward_lean", {})),
            KneeValgusRule(config.get("knee_valgus", {})),
        ]
        self.history: deque[JointAngles] = deque(maxlen=90)  # ~1.5s at 60fps

    def evaluate(self, angles: JointAngles) -> list[FaultEvent]:
        self.history.append(angles)
        faults = []
        for rule in self.rules:
            fault = rule.evaluate(angles, self.history)
            if fault:
                faults.append(fault)
        return faults
```

**Example rule — `rules/depth.py`:**

```python
class DepthRule(FaultRule):
    """Evaluate squat depth based on hip flexion angle.

    Depth categories:
    - Quarter squat: hip flexion < 60°
    - Half squat: 60° ≤ hip flexion < 90°
    - Parallel: 90° ≤ hip flexion < 100°
    - Below parallel: hip flexion ≥ 100°

    Fault fires at rep completion (detected by rep counter) if
    target depth was not achieved.
    """

    def evaluate(self, angles: JointAngles,
                 history: deque[JointAngles]) -> Optional[FaultEvent]:
        # Use max of left and right hip flexion
        max_depth = max(angles.hip_flexion_r, angles.hip_flexion_l)

        if max_depth < self.thresholds["parallel"]:
            return FaultEvent(
                fault_type=FaultType.DEPTH,
                severity=FaultSeverity.MODERATE,
                severity_score=1.5,
                message=f"Squat depth: {max_depth:.0f}° — not reaching parallel",
                joint_data={"hip_flexion_r": angles.hip_flexion_r,
                            "hip_flexion_l": angles.hip_flexion_l},
            )
        return None
```

**rep_counter.py:**

```python
class RepCounter:
    """Detect rep boundaries using hip flexion angle peak detection.

    State machine:
    - IDLE: hip flexion < entry_threshold (30°)
    - IN_REP: hip flexion >= entry_threshold
    - Transition IN_REP → IDLE = rep complete

    On rep completion, emit RepData with all buffered joint angles
    and accumulated faults for that rep.
    """

    def __init__(self, entry_threshold: float = 30.0,
                 min_rep_duration_frames: int = 20):
        self.entry_threshold = entry_threshold
        self.min_rep_duration = min_rep_duration_frames
        self.state = "IDLE"
        self.rep_count = 0
        self.current_rep_frames: list[JointAngles] = []
        self.current_rep_faults: list[FaultEvent] = []
        self.rep_start_frame = 0
        self.rep_start_time = 0.0
```

**tcn_model.py** — TCN architecture (for v2, but scaffold now):

```python
class TemporalConvNet(nn.Module):
    """Temporal Convolutional Network for dynamic fault detection.

    Architecture:
    - Input: (batch, channels, seq_len) where channels = number of joint angles
    - 3 temporal conv blocks with residual connections
    - 64 hidden units per block
    - Causal convolution (no future leakage)
    - Output: severity score (0-3) per fault type

    For v1, this is scaffolded but not trained. The rule engine
    handles all fault detection. TCN training requires labeled data.
    """

    def __init__(self, input_channels: int = 11,  # number of joint angles
                 hidden_channels: int = 64,
                 num_layers: int = 3,
                 kernel_size: int = 7,
                 num_fault_types: int = 2):  # valgus, rounding
        super().__init__()
        # Build temporal conv blocks
        ...
```

### 4.6 Layer 5: Coaching Output (`coaching/`)

**audio_cues.py:**

```python
class AudioCueEngine:
    """Real-time audio feedback during sets.

    Design principles:
    - Short, actionable cues: "knees out", "chest up", "deeper"
    - Minimum 2-second gap between cues to avoid overload
    - Priority system: higher severity faults override pending cues
    - Uses pyttsx3 for offline TTS (no network latency)

    On macOS, pyttsx3 uses NSSpeechSynthesizer — low latency, no setup.
    """

    CUE_MAP = {
        "knee_valgus": "knees out",
        "forward_lean": "chest up",
        "depth": "deeper",
        "heel_rise": "heels down",
        "bilateral_asymmetry": "even it out",
    }

    def __init__(self, min_gap_seconds: float = 2.0):
        import pyttsx3
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 180)  # Slightly fast for urgency
        self.min_gap = min_gap_seconds
        self.last_cue_time = 0.0
```

**llm_coach.py:**

```python
class LLMCoach:
    """LLM-powered coaching analysis using Claude API.

    IMPORTANT: The LLM is a COMMUNICATION layer, not a DECISION layer.
    It receives structured fault data from the validated pipeline and
    translates it into natural language. It never makes biomechanical
    decisions.

    Used for:
    - Between-set summaries
    - Post-session reports
    - Personalized recommendations based on session history
    """

    SYSTEM_PROMPT = """You are an expert strength coach analyzing squat data
    from a biomechanics system. You receive structured data about joint angles,
    detected faults, and rep quality. Your job is to communicate this data
    as clear, actionable coaching feedback.

    Rules:
    - Only reference faults that appear in the data — never invent issues
    - Use coaching language, not clinical language
    - Prioritize the 1-2 most impactful corrections
    - Reference specific rep numbers when relevant
    - Be encouraging but honest about form issues
    """

    def __init__(self, api_key: str | None = None):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)  # Uses ANTHROPIC_API_KEY env var

    async def analyze_set(self, reps: list[RepData]) -> str:
        """Generate coaching feedback for a completed set."""
        structured_data = self._format_set_data(reps)
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": structured_data}]
        )
        return response.content[0].text
```

### 4.7 Pipeline Orchestrator (`pipeline.py`)

```python
class BiomechanicsPipeline:
    """Connects all layers into a real-time processing pipeline.

    Data flow per frame:
    capture → pose_estimator → triangulator → ik_solver → fault_engine → coaching

    Each layer is timed independently. The pipeline enforces the type
    contracts between layers — each layer receives exactly the type it
    expects and produces exactly the type the next layer expects.
    """

    def __init__(self, config: PipelineConfig):
        # Initialize layers based on config
        self.capture = self._init_capture(config.capture)
        self.pose_estimator = self._init_pose(config.pose)
        self.triangulator = self._init_triangulation(config.triangulation)
        self.ik_solver = self._init_ik(config.kinematics)
        self.fault_engine = RuleEngine(config.faults)
        self.rep_counter = RepCounter(config.rep_detection)
        self.audio = AudioCueEngine(config.coaching)
        self.session = SessionState(session_id=str(uuid4()), start_time=time.time())

    def process_frame(self) -> PipelineFrame:
        """Process a single frame through the full pipeline.

        Returns PipelineFrame with all intermediate results and timing.
        Any layer failure is caught and logged — downstream layers
        receive None and skip processing.
        """
        timings = {}
        frame_result = PipelineFrame(
            frame_index=self.frame_count,
            timestamp=time.time()
        )

        # Layer 0: Capture
        t0 = time.perf_counter()
        success, raw_frame = self.capture.read()
        timings["capture"] = (time.perf_counter() - t0) * 1000
        if not success:
            return frame_result

        # Layer 1: Pose Estimation
        t0 = time.perf_counter()
        skeleton_2d = self.pose_estimator.estimate(raw_frame)
        timings["pose"] = (time.perf_counter() - t0) * 1000

        # Layer 2: Triangulation (skip if single camera — use depth prior)
        t0 = time.perf_counter()
        if self.triangulator:
            skeleton_3d = self.triangulator.triangulate(...)
        else:
            skeleton_3d = self._lift_to_3d(skeleton_2d)  # Single-cam depth estimation
        timings["triangulation"] = (time.perf_counter() - t0) * 1000

        # Layer 3: Inverse Kinematics
        t0 = time.perf_counter()
        joint_angles = self.ik_solver.solve(skeleton_3d)
        timings["ik"] = (time.perf_counter() - t0) * 1000

        # Layer 4: Fault Detection
        t0 = time.perf_counter()
        faults = self.fault_engine.evaluate(joint_angles)
        rep_data = self.rep_counter.update(joint_angles, faults)
        timings["faults"] = (time.perf_counter() - t0) * 1000

        # Layer 5: Coaching (audio cues — non-blocking)
        t0 = time.perf_counter()
        if faults:
            self.audio.queue_cue(max(faults, key=lambda f: f.severity_score))
        timings["coaching"] = (time.perf_counter() - t0) * 1000

        frame_result.latency_ms = timings
        frame_result.joint_angles = joint_angles
        frame_result.faults = faults
        frame_result.rep_data = rep_data
        self.frame_count += 1
        return frame_result

    def run(self):
        """Main loop — process frames until stopped."""
        while self.running:
            result = self.process_frame()
            self.viz.update(result)  # Non-blocking visualization update
            total = sum(result.latency_ms.values())
            if self.frame_count % 60 == 0:
                logger.info("pipeline_timing", **result.latency_ms, total_ms=total)
```

---

## 5. Configuration System (`config/`)

### `default.yaml`

```yaml
pipeline:
  target_fps: 30
  log_level: INFO

capture:
  source: webcam          # webcam | video_file | multi_cam
  device_id: 0
  resolution: [1280, 720]
  video_path: null        # Set for video_file source

pose:
  backend: mediapipe      # rtmpose | mediapipe
  model_path: biomechanics/pose/models/rtmpose_m.onnx
  confidence_threshold: 0.3

triangulation:
  enabled: false          # Set true when multi-cam available
  camera_config: config/camera_sim.yaml

kinematics:
  backend: analytical     # analytical | opensim
  opensim_model_path: config/models/rajagopal_2016/Rajagopal2016.osim
  scaled_model_path: null # Per-user scaled model

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
  audio_enabled: true
  min_cue_gap_seconds: 2.0
  llm_enabled: false      # Enable for post-session analysis
  llm_model: claude-sonnet-4-20250514

visualization:
  show_skeleton: true
  show_angles: true
  show_faults: true
  dashboard: false        # Enable web dashboard
```

---

## 6. Testing Strategy

### 6.1 Test Hierarchy

```
Unit tests (per-layer)
├── test_pose: Known images → expected keypoints
├── test_triangulation: Known 2D pairs → expected 3D points
├── test_kinematics: Known 3D points → expected angles
├── test_faults: Known angle sequences → expected faults
└── test_rep_counter: Known angle series → expected rep boundaries

Integration tests
├── test_pipeline: Video file → full pipeline → expected outputs
└── test_session: Multi-rep sequence → session state verification

Benchmark tests
├── benchmark_per_layer: Latency per layer on M2
└── benchmark_end_to_end: Total pipeline throughput
```

### 6.2 Test Fixtures

Create synthetic test data with known ground truth:

```python
# fixtures/sample_keypoints.json
# A person in a half-squat position — all 17 COCO keypoints
# with known pixel coordinates for a 1280x720 frame

# fixtures/sample_3d_points.json
# Same pose as above but in 3D world coordinates (meters)
# Used to test IK without depending on pose estimation or triangulation

# fixtures/sample_angles.json
# Known joint angles for the same pose
# Used to test fault detection without depending on upstream layers
```

### 6.3 Running Tests

```bash
# Full suite
pytest tests/ -v

# Single layer
pytest tests/test_faults/ -v

# With coverage
pytest tests/ --cov=biomechanics --cov-report=term-missing

# Benchmark
python scripts/benchmark.py --config config/default.yaml --frames 300
```

---

## 7. CLI Interface (`main.py`)

```bash
# Live webcam mode (default)
biomechanics run

# Analyze a video file
biomechanics run --source video --video-path squat_recording.mp4

# Run with web dashboard
biomechanics run --dashboard

# Benchmark pipeline latency
biomechanics benchmark --frames 300

# Calibrate cameras
biomechanics calibrate --checkerboard 9x6

# Scale model for new user
biomechanics onboard --user-id user123

# Generate session report
biomechanics report --session-id <id>
```

---

## 8. Development Priorities & Build Order

**This is the order Claude Code should build the system:**

### Phase 1: Foundation (build first)
1. Project structure, pyproject.toml, config system
2. `utils/types.py` — all shared data types
3. `utils/timing.py` — performance profiling
4. `capture/webcam.py` and `capture/video_file.py`

### Phase 2: Layer 1 — Pose Estimation
5. `pose/base.py` — abstract interface
6. `pose/mediapipe_fallback.py` — get working first (zero setup)
7. `pose/rtmpose.py` — ONNX inference
8. `viz/overlay_2d.py` — skeleton overlay for visual verification
9. Tests for pose layer

### Phase 3: Layer 3 — Inverse Kinematics (skip Layer 2 for single-cam)
10. `kinematics/base.py` — abstract interface
11. `kinematics/analytical_ik.py` — geometric angle solver
12. `kinematics/joint_angles.py` — angle extraction helpers
13. Tests for IK layer

### Phase 4: Layer 4 — Fault Detection
14. `faults/fault_types.py` — definitions
15. `faults/rep_counter.py` — rep detection
16. `faults/rule_engine.py` — rule orchestrator
17. `faults/rules/depth.py` — depth rule
18. `faults/rules/symmetry.py` — symmetry rule
19. `faults/rules/heel_rise.py` — heel rise rule
20. `faults/rules/forward_lean.py` — forward lean rule
21. `faults/rules/knee_valgus.py` — valgus rule (v1 rule-based)
22. Tests for fault layer

### Phase 5: Pipeline Integration
23. `pipeline.py` — connect all layers
24. `main.py` — CLI entry point
25. End-to-end test with video file
26. `scripts/benchmark.py` — latency profiling

### Phase 6: Coaching & Visualization
27. `coaching/audio_cues.py` — TTS feedback
28. `coaching/session.py` — session state
29. `viz/dashboard.py` — real-time metrics display
30. `coaching/llm_coach.py` — Claude integration
31. `coaching/report.py` — post-session reports

### Phase 7: Multi-Camera & Triangulation
32. `triangulation/calibration.py` — camera calibration
33. `triangulation/stereo.py` — triangulation
34. `triangulation/sim_cameras.py` — simulated multi-cam
35. `capture/multi_cam.py` — multi-camera manager

### Phase 8: Advanced (v2)
36. `kinematics/opensim_ik.py` — OpenSim integration
37. `kinematics/subject_scaling.py` — model scaling
38. `faults/tcn_model.py` — TCN architecture
39. `scripts/generate_synthetic.py` — synthetic data
40. `viz/web_ui.py` — WebSocket dashboard

---

## 9. Key Design Constraints

1. **Every layer must be independently testable.** No layer imports from another layer's internals. Communication is only through types defined in `utils/types.py`.

2. **Graceful degradation is mandatory.** If OpenSim isn't installed, use analytical IK. If RTMPose model isn't downloaded, use MediaPipe. If only one camera, skip triangulation and use 2D-to-3D lifting. The system must always produce *some* output.

3. **Performance must be measurable.** Every layer wraps its processing in timing code. The benchmark script reports per-layer latency. Target: full pipeline under 50ms per frame on M2.

4. **Configuration over code.** All thresholds, model paths, camera parameters, and feature flags live in YAML config. No magic numbers in code.

5. **The pipeline is synchronous for v1.** No async complexity. Process one frame at a time. Async/threading optimization is a v2 concern.

6. **Type safety.** Use Pydantic models for all inter-layer data. Use type hints everywhere. Run mypy in CI.

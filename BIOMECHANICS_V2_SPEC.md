# Biomechanics V2 — MuJoCo Physics-Based Pipeline

## What This Document Is

This is a complete implementation spec for a new physics-based biomechanics pipeline (`src/biomechanics_v2/`) that replaces the custom IK/FK/solver stack with MuJoCo. The existing capture, filtering, fault detection, and rep segmentation layers are reused unchanged. Everything below the filtering layer — skeleton modeling, IK, FK, what-if solving, diagnosis solver — is rebuilt on MuJoCo's physics engine.

The end deliverable is a script (like the existing `scripts/visualize_video_squats.py`) that captures squat video, runs the MuJoCo pipeline, and outputs an interactive HTML file with Three.js visualization and slider-based what-if perturbations powered by real physics.

---

## Why MuJoCo

The current V1 pipeline has:
- A **buggy custom IK** (`src/biomechanics/optimizer/ik.py`) — ankle/trunk DOFs stuck at zero, 100-475mm FK reconstruction errors (documented in `IK_FIT_BUG.md`)
- A **hand-rolled Jacobian** (`_fk_jac`) that likely has axis-mapping errors
- A **geometric torque proxy** (`costs.py:55`) that approximates what physics computes exactly
- A **what-if solver** (SLSQP + 5 cost terms + 2 constraints) that heuristically approximates what forward dynamics does naturally

MuJoCo replaces all of this with:
- **Correct FK** via Featherstone's articulated body algorithm — no hand-rolled rotation matrices
- **Correct Jacobians** via `mj_jac` — eliminates the IK bug class entirely
- **Forward dynamics** — gravity + contacts find stable poses automatically, replacing 5 cost functions
- **Inverse dynamics** — compute real joint torques from motion, replacing the geometric torque proxy
- **Contact simulation** — feet interact with the floor physically, replacing the "feet rooted" equality constraint
- **Joint limits** enforced by the physics engine, not by optimizer bounds

Key MuJoCo features we use:
- `mujoco` Python package (`pip install mujoco`) — C engine with pybind11 bindings
- MJCF XML model format — defines bodies, joints, contacts, actuators
- `mj_forward(model, data)` — forward kinematics + dynamics without integration
- `mj_step(model, data)` — full physics step with contact resolution
- `mj_jac(model, data, ...)` — analytically correct Jacobian computation
- `mj_inverse(model, data)` — inverse dynamics (motion → forces/torques)
- Mocap bodies + weld constraints — drive skeleton from external keypoints
- `data.qpos` / `data.xpos` — read/write joint angles and Cartesian positions (zero-copy numpy)
- Named access: `model.body('L_hip').id`, `data.joint('L_knee').qpos`

Third-party libraries:
- `mink` (`pip install mink`) — differential IK for MuJoCo with collision avoidance, joint limits, composable task objectives. Alternative to writing our own IK optimization loop.

---

## Architecture Overview

```
REUSED (unchanged from V1)                    NEW (biomechanics_v2)
──────────────────────                        ────────────────────
Camera capture                                
    ↓                                         
Pose estimation (MediaPipe/RTMPose)           
    ↓                                         
Triangulation (optional multi-cam)            
    ↓                                         
Pre-IK filtering chain:                       
  - Confidence blend                          
  - Velocity clamp                            
  - Bone constraints + BodyProportions        
  - Position smoothing                        
    ↓                                         
Skeleton3D (19 COCO keypoints, meters)        
    ↓                                         
    ├──────────────────────────────────→  MuJoCo MJCF model (skeleton_model.py)
    │                                         ↓
    │                                    MuJoCo IK solver (mujoco_ik.py)
    │                                      - mocap bodies + weld constraints
    │                                      - OR mink differential IK
    │                                         ↓
    │                                    q-trajectory (joint angles, radians)
    │                                         ↓
    │                                    Angle extractor → JointAngles
    ↓                                         ↓
Fault detection (RuleEngine)  ←──────── JointAngles (degrees)
Rep segmentation              ←──────── hip position from FK
Barbell tracking              ←──────── (independent, runs in parallel)
                                              ↓
                                         MuJoCo what-if solver (mujoco_whatif.py)
                                           - Modify joint limits / foot positions
                                           - Forward dynamics settle (~100-300 steps)
                                           - Read corrected q-vector
                                              ↓
                                         Diagnosis engine (reuse existing)
                                           - parameter_deltas → MuJoCo perturbations
                                           - FormSolverDriver uses MuJoCo what-if
                                              ↓
                                         HTML visualizer (visualize_v2.py)
                                           - Three.js skeleton renderer
                                           - Slider perturbations
                                           - Original vs corrected overlay
                                           - Rep scrubbing, fault annotations
```

---

## Reused Modules (DO NOT MODIFY)

These modules are imported directly from the existing `src/biomechanics/` package. Do not copy, fork, or modify them.

### Pose Estimation
- `src/biomechanics/pose/base.py` — `PoseEstimator` ABC, `COCO_KEYPOINT_NAMES` (19 keypoints)
- `src/biomechanics/pose/mediapipe_fallback.py` — `MediaPipePoseEstimator` → `(Skeleton2D, Skeleton3D)`
- `src/biomechanics/pose/rtmpose.py` — `RTMPoseEstimator` → `Skeleton2D` (2D only)

### Pre-IK Filtering
- `src/biomechanics/utils/confidence_blend.py` — `ConfidenceBlender.blend(Skeleton3D) → Skeleton3D`
- `src/biomechanics/utils/velocity_clamp.py` — `VelocityClamp.clamp(Skeleton3D) → Skeleton3D`
- `src/biomechanics/utils/bone_constraints.py` — `BoneLengthConstraints.enforce(Skeleton3D) → Skeleton3D`, produces `BodyProportions`
- `src/biomechanics/utils/position_filter.py` — `KeypointPositionSmoother.smooth(Skeleton3D) → Skeleton3D`

### Types
- `src/biomechanics/utils/types.py` — `Skeleton2D`, `Skeleton3D`, `Point3D`, `JointAngles`, `PipelineFrame`, `RepData`, `FaultEvent`, `FaultSeverity`, `BarTrackState`, `BarbellDetection`, `CocoKeypoints`, `MultiViewPose`

### Fault Detection
- `src/biomechanics/faults/fault_types.py` — `FaultType` enum (15 fault types)
- `src/biomechanics/faults/rule_engine.py` — `RuleEngine.evaluate(JointAngles, ...) → List[FaultEvent]`
- `src/biomechanics/faults/rules/` — 15 rule implementations
- The rule engine consumes `JointAngles` objects. As long as the V2 IK produces `JointAngles` with the same field names and sign conventions, all existing rules work unchanged.

### Rep Segmentation
- `src/biomechanics/analysis/rep_segmenter.py` — `segment_set(data_dict) → result_dict`

### Barbell Tracking
- `src/biomechanics/barbell_tracking/detector.py` — `BarbellDetector.detect(frame) → BarbellDetection`
- `src/biomechanics/barbell_tracking/tracker.py` — `BarPathTracker.update(detection) → BarTrackState`

### Triangulation
- `src/biomechanics/triangulation/` — `DLTTriangulator`, `MultiCameraCapture`, `TPoseCalibrator`

### Diagnosis Engine (partially reused)
- `src/biomechanics/diagnosis/engine.py` — `HypothesisEngine.diagnose(SetFeatures) → DiagnosisResult`
- `src/biomechanics/diagnosis/types.py` — `SetFeatures`, `RepKinematicSummary`, `DiagnosisResult`, `DetectedSymptom`, `HypothesizedCause`
- `src/biomechanics/diagnosis/graph/parameter_deltas.py` — delta functions (reuse the perturbation format)
- `src/biomechanics/diagnosis/graph/evidence_tests.py` — evidence scoring functions
- `src/biomechanics/diagnosis/graph/loader.py` — causal graph definition

---

## What Gets Replaced

These V1 modules are NOT used in V2. New MuJoCo-based equivalents are built from scratch.

| V1 Module | V1 File | V2 Replacement |
|-----------|---------|----------------|
| Skeleton definition | `skeleton/definition.py` | `biomechanics_v2/model/skeleton_model.py` — MJCF XML generation |
| Forward kinematics | `skeleton/forward_kin.py` | MuJoCo `mj_forward()` + `data.xpos` |
| Anthropometric scaling | `skeleton/anthropometry.py` | `biomechanics_v2/model/anthropometry.py` — scale MJCF model |
| IK solver | `optimizer/ik.py` | `biomechanics_v2/solver/mujoco_ik.py` — mocap+weld or mink |
| Landmark adapter | `optimizer/landmark_adapter.py` | `biomechanics_v2/solver/landmark_adapter.py` — same mapping, targets mocap bodies |
| What-if solver | `optimizer/whatif.py` | `biomechanics_v2/solver/mujoco_whatif.py` — forward dynamics |
| Cost functions | `optimizer/costs.py` | Eliminated — physics replaces geometric costs |
| Temporal taper | `optimizer/temporal.py` | `biomechanics_v2/solver/temporal.py` — rewrite (same math, different solver interface) |
| Angle extractor | `optimizer/angle_extract.py` | `biomechanics_v2/solver/angle_extract.py` — read from MuJoCo `data.qpos` |
| Form solver driver | `diagnosis/solver_driver.py` | `biomechanics_v2/solver/form_solver_driver.py` — calls MuJoCo what-if |

---

## New File Structure

```
src/biomechanics_v2/
├── __init__.py
├── model/
│   ├── __init__.py
│   ├── skeleton_model.py        # MJCF model generation + loading
│   ├── anthropometry.py         # Scale MJCF model from height/weight
│   └── assets/
│       └── squat_skeleton.xml   # Generated/hand-tuned MJCF file
├── solver/
│   ├── __init__.py
│   ├── mujoco_ik.py             # IK: Skeleton3D → q-trajectory
│   ├── mujoco_whatif.py         # What-if: perturbation → forward dynamics → corrected q
│   ├── mujoco_fk.py             # FK helpers: q → world positions, COM, joint torques
│   ├── landmark_adapter.py      # COCO keypoints → mocap body targets
│   ├── angle_extract.py         # q-vector → JointAngles (degrees)
│   ├── temporal.py              # Gaussian taper for trajectory warping
│   └── form_solver_driver.py    # DiagnosisResult → MuJoCo what-if → FormSolverResult
├── pipeline.py                  # V2 pipeline orchestrator (capture → filter → MuJoCo → faults)
└── visualizer/
    ├── __init__.py
    ├── capture.py               # Live capture + recording (reuses V1 components)
    ├── html_builder.py          # Build self-contained HTML with Three.js
    └── js_templates/
        └── viewer.js            # Three.js viewer with slider UI (embedded in HTML)

scripts/
└── visualize_v2.py              # Entry point: capture → V2 pipeline → HTML output

tests/
└── test_biomechanics_v2/
    ├── test_mjcf_model.py       # MJCF loads, joint count, DOF count, bounds
    ├── test_fk_match.py         # MuJoCo FK matches V1 FK for same q-vector
    ├── test_ik_accuracy.py      # IK reconstruction error < 20mm for lower body
    ├── test_whatif_physics.py   # Forward dynamics produces stable, bounded poses
    ├── test_angle_extract.py    # JointAngles sign conventions match V1
    └── test_pipeline_e2e.py     # Full pipeline: synthetic input → HTML output
```

---

## Coordinate Systems & Conventions

### MediaPipe (pose estimation output)
- X: subject's left (positive)
- Y: down (positive, gravity direction)
- Z: toward camera (positive)
- Origin: hip midpoint
- Units: meters

### MuJoCo / Skeleton model (Y-up)
- X: subject's left (negative = left)
- Y: up (positive, anti-gravity)
- Z: forward (positive, direction subject faces)
- Origin: floor beneath pelvis at neutral pose
- Units: meters

### Coordinate flip (landmark adapter)
```python
landmarks[:, 0] *= -1   # negate X
landmarks[:, 1] *= -1   # negate Y (flip to Y-up)
# Z unchanged
```

### Angle conventions (JointAngles output, degrees)
- Hip flexion: 0° standing, positive = forward
- Knee flexion: 0° extended, positive = bending
- Ankle dorsiflexion: 0° neutral, positive = shin forward
- Hip adduction: 0° sagittal plane, positive = toward midline
- Knee valgus: 0° on hip-ankle line, positive = medial
- Trunk flexion: 180° upright, decreases with forward lean
- Pelvis tilt: 0° neutral, positive = anterior

### Q-vector format (20 DOF, radians)
```
q[0:3]   = pelvis translation (tx, ty, tz) — meters
q[3:6]   = pelvis rotation (rx, ry, rz) — radians
q[6:8]   = trunk (rx, rz) — radians
q[8:11]  = L_hip (rx, ry, rz) — radians
q[11]    = L_knee (rx) — radians
q[12:14] = L_ankle (rx, ry) — radians
q[14:17] = R_hip (rx, ry, rz) — radians
q[17]    = R_knee (rx) — radians
q[18:20] = R_ankle (rx, ry) — radians
```

### Joint angle bounds (degrees, from V1 skeleton/definition.py)
```
pelvis.rx:  [-45, +45]     trunk.rx:  [-30, +60]
pelvis.ry:  [-25, +25]     trunk.rz:  [-25, +25]
pelvis.rz:  [-15, +15]
L_hip.rx:   [-15, +130]    R_hip.rx:  [-15, +130]
L_hip.ry:   [-30, +45]     R_hip.ry:  [-45, +30]
L_hip.rz:   [-30, +40]     R_hip.rz:  [-40, +30]
L_knee.rx:  [0, +150]      R_knee.rx: [0, +150]
L_ankle.rx: [-30, +40]     R_ankle.rx:[-30, +40]
L_ankle.ry: [-20, +20]     R_ankle.ry:[-20, +20]
```

---

## MJCF Model Specification

The MJCF model must encode the same 20-DOF skeleton hierarchy as the V1 `SkeletonModel`. Here is the target structure:

### Joint Hierarchy (matches V1)

```
worldbody
└── pelvis (freejoint — 6 DOF: 3 trans + 3 rot)
    ├── trunk (2 hinge joints: rx, rz)
    │   └── head (no joints, visual endpoint)
    ├── L_hip (3 hinge joints: rx, ry, rz)
    │   └── L_thigh_geom
    │   └── L_knee (1 hinge joint: rx)
    │       └── L_shin_geom
    │       └── L_ankle (2 hinge joints: rx, ry)
    │           └── L_foot_geom
    │           └── L_toe (no joints, endpoint)
    └── R_hip (3 hinge joints: rx, ry, rz)
        └── R_thigh_geom
        └── R_knee (1 hinge joint: rx)
            └── R_shin_geom
            └── R_ankle (2 hinge joints: rx, ry)
                └── R_foot_geom
                └── R_toe (no joints, endpoint)
```

### Body Offsets (at reference height 1.75m)

| Body | Parent | Offset (meters) | Direction |
|------|--------|-----------------|-----------|
| pelvis | world | (0, 0.95, 0) | Floating root above floor |
| trunk | pelvis | (0, 0.28, 0) | Upward from pelvis |
| head | trunk | (0, 0.40, 0) | Upward from trunk |
| L_hip | pelvis | (-0.10, 0, 0) | Left side of pelvis |
| R_hip | pelvis | (0.10, 0, 0) | Right side of pelvis |
| L_knee | L_hip | (0, 0, -0.45) | Thigh extends backward (-Z) |
| R_knee | R_hip | (0, 0, -0.45) | Thigh extends backward (-Z) |
| L_ankle | L_knee | (0, 0, 0.43) | Shin extends forward (+Z) |
| R_ankle | R_knee | (0, 0, 0.43) | Shin extends forward (+Z) |
| L_toe | L_ankle | (0, -0.20, 0) | Foot hangs downward |
| R_toe | R_ankle | (0, -0.20, 0) | Foot hangs downward |

**Important geometry note:** Thigh (-Z) and shin (+Z) extend in opposite directions from the knee. At neutral pose (all DOFs = 0), the leg is in a bent configuration. Knee rx opens/closes this bend.

### Segment Masses (de Leva 1996, 75 kg reference)

| Segment | Mass Fraction | Mass (75 kg) |
|---------|--------------|--------------|
| Pelvis | 10.65% | 7.99 kg |
| Trunk | 22.13% | 16.60 kg |
| Head | 5.0% | 3.75 kg |
| Thigh (each) | 9.23% | 6.92 kg |
| Shank (each) | 3.6% | 2.70 kg |
| Foot (each) | 0.9% | 0.675 kg |

### Contact Specification

- Floor: infinite plane at Y=0
- Foot geoms: capsules or boxes attached to ankle/toe bodies
- Contact friction: ~1.0 (rubber on floor)
- Self-collision: disabled (not needed for squat analysis)
- Contact parameters: use MuJoCo defaults for solref/solimp

### Mocap Bodies (for IK)

Define 11 mocap bodies corresponding to the 11 skeleton joints. These are driven by external keypoint data and pull the simulated skeleton via weld constraints.

```xml
<body name="mocap_pelvis" mocap="true"><site name="target_pelvis"/></body>
<body name="mocap_trunk" mocap="true"><site name="target_trunk"/></body>
<body name="mocap_L_hip" mocap="true"><site name="target_L_hip"/></body>
<!-- ... etc for all 11 joints -->
```

Weld constraints:
```xml
<equality>
  <weld body1="pelvis" body2="mocap_pelvis" solref="0.02 1" active="true"/>
  <weld body1="trunk_body" body2="mocap_trunk" solref="0.02 1" active="true"/>
  <!-- ... etc -->
</equality>
```

The `solref` parameter controls constraint stiffness. Tune so that the skeleton tracks keypoints without oscillation.

---

## Perturbation Format (What-If Solver)

The V1 diagnosis engine produces perturbations as:
```python
{"L_hip.rx": 0.09, "R_hip.rx": 0.09, "L_ankle.ry": 0.05, ...}  # radians
{"__foot_target_delta": [dLx, dLy, dLz, dRx, dRy, dRz]}          # meters
```

The V2 MuJoCo what-if solver translates these to:
1. **Joint angle deltas** → modify `data.qpos` for the corresponding DOFs
2. **Joint limit changes** → modify `model.jnt_range` (e.g., increase dorsiflexion limit)
3. **Foot position deltas** → move the foot body positions before settling
4. **Then forward simulate** (~100-500 steps) until kinetic energy < threshold
5. **Read corrected q-vector** from `data.qpos`

### Settling Criteria
```python
kinetic_energy = data.energy[1]   # MuJoCo tracks kinetic energy
settled = kinetic_energy < 1e-6   # Body has stopped moving
max_steps = 500                   # Safety limit
```

---

## Anthropometric Scaling

### Input
- `height_m: float` — athlete height in meters
- `weight_kg: float` — athlete weight in kg

### Scaling Logic
1. Compute `scale_factor = height_m / 1.75` (reference height)
2. Scale all body offsets by `scale_factor`
3. Scale segment masses by `weight_kg / 75.0`
4. Scale geom sizes proportionally
5. Regenerate MJCF model with scaled parameters
6. Compile new `mujoco.MjModel`

### Calibration from Observed Bone Lengths
After `BoneLengthConstraints` calibrates (first 30 standing frames), use the measured `BodyProportions` to fine-tune individual segment lengths:
- `femur_length_avg` → L_knee/R_knee offset Z component
- `tibia_length_avg` → L_ankle/R_ankle offset Z component
- `torso_length_avg` → trunk offset Y component
- `hip_width` → L_hip/R_hip offset X component

---

## Implementation Sessions

### Session 1: MJCF Model + FK Validation

**Goal:** Create the MuJoCo skeleton model and prove FK matches V1.

**Files to create:**
- `src/biomechanics_v2/__init__.py`
- `src/biomechanics_v2/model/__init__.py`
- `src/biomechanics_v2/model/skeleton_model.py`
- `src/biomechanics_v2/model/anthropometry.py`
- `src/biomechanics_v2/model/assets/squat_skeleton.xml` (generated)
- `tests/test_biomechanics_v2/test_mjcf_model.py`
- `tests/test_biomechanics_v2/test_fk_match.py`

**`skeleton_model.py` must provide:**
```python
class MujocoSkeleton:
    def __init__(self, height_m: float = 1.75, weight_kg: float = 75.0):
        """Build and compile MJCF model."""

    @property
    def model(self) -> mujoco.MjModel: ...

    @property
    def data(self) -> mujoco.MjData: ...

    def n_dof(self) -> int: ...          # 20

    def set_qpos(self, q: np.ndarray) -> None:
        """Set joint positions from 20-DOF q-vector (radians)."""

    def get_qpos(self) -> np.ndarray:
        """Get 20-DOF q-vector (radians)."""

    def forward(self) -> None:
        """Run mj_forward — compute FK + dynamics."""

    def get_body_positions(self) -> dict[str, np.ndarray]:
        """Joint name → (3,) world position after forward()."""

    def get_body_com(self) -> np.ndarray:
        """Mass-weighted center of mass (3,)."""

    def get_joint_index(self, joint_name: str, axis: str) -> int:
        """Map 'L_hip', 'rx' → index into q-vector."""

    def get_bounds(self) -> list[tuple[float, float]]:
        """Per-DOF bounds in radians, same order as q-vector."""

    def scale_from_proportions(self, proportions) -> None:
        """Re-scale model using calibrated BodyProportions. Recompiles model."""

    def to_xml(self) -> str:
        """Export current model as MJCF XML string."""
```

**`anthropometry.py` must provide:**
```python
def build_mjcf_xml(
    height_m: float = 1.75,
    weight_kg: float = 75.0,
    include_mocap_bodies: bool = True,
    include_floor: bool = True,
) -> str:
    """Generate MJCF XML string for the squat skeleton model."""

def scale_mjcf_from_proportions(
    base_xml: str,
    proportions,    # BodyProportions from bone_constraints.py
    weight_kg: float,
) -> str:
    """Adjust segment lengths in MJCF XML to match calibrated bone lengths."""
```

**Verification:**
1. `test_mjcf_model.py`:
   - Model loads without error
   - `n_dof == 20`
   - Joint names match: pelvis, trunk, L_hip, R_hip, L_knee, R_knee, L_ankle, R_ankle
   - Bounds match V1 skeleton definition (within 0.001 rad)
   - Neutral pose (q=0) produces reasonable body positions (pelvis ~0.95m, ankles near floor)

2. `test_fk_match.py`:
   - For 10 random q-vectors within bounds:
     - Run V1 `forward_kinematics(skeleton, q)` from `src/biomechanics/skeleton/forward_kin.py`
     - Run V2 `mujoco_skeleton.set_qpos(q); mujoco_skeleton.forward(); mujoco_skeleton.get_body_positions()`
     - Assert all joint positions match within 5mm
   - Test with a deep squat pose (hip flexion ~100°, knee ~140°, ankle DF ~30°)
   - Test with anthropometric scaling (height=1.885m, the user's height)

---

### Session 2: MuJoCo IK Solver

**Goal:** Replace `optimizer/ik.py` with MuJoCo-based IK that actually works (< 20mm error).

**Files to create:**
- `src/biomechanics_v2/solver/__init__.py`
- `src/biomechanics_v2/solver/mujoco_ik.py`
- `src/biomechanics_v2/solver/landmark_adapter.py`
- `tests/test_biomechanics_v2/test_ik_accuracy.py`

**Approach — Mocap bodies + weld constraints + stepping:**
1. Write COCO keypoints → mocap body positions (via landmark adapter)
2. Call `mj_step()` repeatedly — weld constraints pull skeleton to match
3. Read resulting `data.qpos` — that's the fitted q-vector
4. For trajectory: warm-start each frame from previous frame's qpos

**Alternative approach — mink differential IK:**
1. Define task-space objectives: each skeleton site tracks a target position
2. Use `mink.solve_ik()` which handles joint limits, collision avoidance
3. This may produce smoother results with less tuning

Evaluate both approaches. Use whichever produces lower reconstruction error. The mocap+weld approach is more "MuJoCo-native" and may handle contact with the floor better.

**`mujoco_ik.py` must provide:**
```python
class MujocoIKSolver:
    def __init__(self, skeleton: MujocoSkeleton):
        """Initialize with compiled MuJoCo model."""

    def fit_frame(
        self,
        landmarks: np.ndarray,          # (11, 4) [x, y, z, visibility] in skeleton coords
        q_init: np.ndarray | None = None,
        vis_threshold: float = 0.5,
        weights: np.ndarray | None = None,
        max_steps: int = 200,
    ) -> np.ndarray:
        """Fit single frame. Returns (20,) q-vector in radians."""

    def fit_trajectory(
        self,
        landmarks: np.ndarray,          # (T, 11, 4)
        q_init: np.ndarray | None = None,
        vis_threshold: float = 0.5,
        weights: np.ndarray | None = None,
        smooth_sigma: float = 1.5,
        max_steps_per_frame: int = 200,
    ) -> np.ndarray:
        """Fit trajectory with warm-starting. Returns (T, 20) q-trajectory."""
```

**`landmark_adapter.py` must provide:**
```python
def skeleton3d_to_landmarks(skeleton: Skeleton3D) -> np.ndarray:
    """Convert 19-keypoint Skeleton3D (MediaPipe Y-down) to (11, 4) array (skeleton Y-up).

    Mapping:
      0: pelvis    ← midpoint(left_hip, right_hip)
      1: trunk     ← 0.58 * midpoint(left_shoulder, right_shoulder) + 0.42 * midpoint(left_hip, right_hip)
      2: L_hip     ← left_hip
      3: R_hip     ← right_hip
      4: L_knee    ← left_knee
      5: R_knee    ← right_knee
      6: L_ankle   ← left_ankle
      7: R_ankle   ← right_ankle
      8: head      ← nose
      9: L_toe     ← left_foot_index
     10: R_toe     ← right_foot_index

    Coordinate flip: negate X, negate Y (MediaPipe Y-down → skeleton Y-up).
    """
```

This is functionally identical to V1's `optimizer/landmark_adapter.py` but targets 11 joints (including head, L_toe, R_toe which V1 mapped but V1's IK ignored).

**Verification (`test_ik_accuracy.py`):**
1. **Round-trip test:** Generate synthetic landmarks from a known q-vector via MuJoCo FK, run IK, check q recovery:
   - All joint angles within 0.05 rad (~3°) of ground truth
   - FK reconstruction error < 10mm for all joints
2. **Deep squat test:** Landmarks from a realistic deep squat pose:
   - Ankle dorsiflexion MUST be non-zero (this is the V1 bug)
   - Trunk flexion MUST be non-zero
   - Hip rz should NOT be at bounds
   - Overall FK error < 20mm for lower body joints
3. **Trajectory test:** 30-frame synthetic trajectory (standing → deep squat → standing):
   - Smooth q-trajectory (no frame-to-frame jumps > 0.15 rad)
   - All frames have FK error < 20mm
4. **Performance:** `fit_frame` < 5ms, `fit_trajectory(30 frames)` < 150ms

---

### Session 3: FK Helpers + Angle Extraction

**Goal:** MuJoCo FK utilities and q-vector → JointAngles conversion.

**Files to create:**
- `src/biomechanics_v2/solver/mujoco_fk.py`
- `src/biomechanics_v2/solver/angle_extract.py`
- `tests/test_biomechanics_v2/test_angle_extract.py`

**`mujoco_fk.py` must provide:**
```python
def joint_world_positions(skeleton: MujocoSkeleton, q: np.ndarray) -> dict[str, np.ndarray]:
    """Set q, run forward, return joint name → (3,) world position."""

def body_com_world(skeleton: MujocoSkeleton, q: np.ndarray) -> np.ndarray:
    """Mass-weighted COM (3,). Uses MuJoCo's built-in COM computation."""

def midfoot_xz(skeleton: MujocoSkeleton, q: np.ndarray) -> np.ndarray:
    """Midpoint of L/R foot centers in XZ plane (2,)."""

def inverse_dynamics(skeleton: MujocoSkeleton, q: np.ndarray, qvel: np.ndarray, qacc: np.ndarray) -> np.ndarray:
    """Compute joint torques via mj_inverse. Returns (20,) torques."""

def joint_jacobian(skeleton: MujocoSkeleton, q: np.ndarray, body_name: str) -> np.ndarray:
    """Compute 3×n_dof positional Jacobian for a body via mj_jac."""
```

**`angle_extract.py` must provide:**
```python
def q_to_joint_angles(
    skeleton: MujocoSkeleton,
    q: np.ndarray,
    timestamp: float = 0.0,
    frame_index: int = 0,
) -> JointAngles:
    """Convert 20-DOF q-vector (radians) to JointAngles (degrees).

    Sign conventions must match V1 exactly (see Coordinate Systems section).
    Key conversions:
      - hip_flexion = degrees(q[L_hip.rx])
      - knee_flexion = degrees(q[L_knee.rx])
      - ankle_dorsiflexion = degrees(q[L_ankle.rx])
      - trunk_flexion = 180.0 - degrees(trunk_from_vertical)  # 180° = upright
      - knee_valgus: computed from FK world positions (frontal plane)
      - hip_adduction: computed from FK world positions
      - stance_width_ratio: ankle distance / shoulder distance
      - toe_out_angle: from ankle ry DOF
    """
```

**Verification (`test_angle_extract.py`):**
1. Standing pose (q ≈ neutral): trunk_flexion ≈ 180°, knee_flexion ≈ 0°, hip_flexion ≈ 0°
2. Deep squat pose: knee_flexion > 100°, hip_flexion > 80°, ankle_df > 15°
3. Asymmetric pose (one ankle more dorsiflexed): L/R angles differ correctly
4. Compare against V1 `angle_extract.q_to_joint_angles()` for 5 test q-vectors — all angles within 2°

---

### Session 4: MuJoCo What-If Solver

**Goal:** Replace SLSQP what-if solver with forward dynamics.

**Files to create:**
- `src/biomechanics_v2/solver/mujoco_whatif.py`
- `src/biomechanics_v2/solver/temporal.py`
- `tests/test_biomechanics_v2/test_whatif_physics.py`

**`mujoco_whatif.py` must provide:**
```python
class MujocoWhatIfSolver:
    def __init__(self, skeleton: MujocoSkeleton):
        """Initialize with model that has floor contact enabled."""

    def solve(
        self,
        q_fitted: np.ndarray,                          # (20,) original pose, radians
        perturbation: dict[str, float],                 # {"joint.axis": delta_rad}
        foot_target_delta: np.ndarray | None = None,    # (6,) [dLx..dRz] meters
        joint_limit_overrides: dict[str, tuple[float, float]] | None = None,
        max_steps: int = 500,
        energy_threshold: float = 1e-6,
    ) -> np.ndarray:
        """Apply perturbation and forward-simulate until settled.

        Algorithm:
        1. Reset data, set qpos = q_fitted
        2. Apply perturbation: qpos[dof_idx] += delta for each joint.axis
        3. If foot_target_delta: shift ankle body positions
        4. If joint_limit_overrides: modify model.jnt_range (e.g., increase DF limit)
        5. Enable gravity, floor contact
        6. Step until kinetic_energy < threshold or max_steps reached
        7. Return settled qpos

        Returns: (20,) q_corrected in radians.
        """

    def warp_trajectory(
        self,
        q_trajectory: np.ndarray,                      # (T, 20)
        bottom_frame: int,
        perturbation: dict[str, float],
        foot_target_delta: np.ndarray | None = None,
        joint_limit_overrides: dict[str, tuple[float, float]] | None = None,
        sigma_frames: float | None = None,
    ) -> np.ndarray:
        """Apply what-if correction across trajectory with Gaussian taper.

        1. Solve at bottom_frame → q_corrected
        2. delta = q_corrected - q_trajectory[bottom_frame]
        3. taper = gaussian_taper(T, bottom_frame, sigma_frames)
        4. warped[t] = q_trajectory[t] + taper[t] * delta
        5. Clip to bounds
        6. Return (T, 20) warped trajectory.
        """
```

**`temporal.py`:**
```python
def gaussian_taper(
    n_frames: int,
    bottom_frame: int,
    sigma_frames: float | None = None,
) -> np.ndarray:
    """Gaussian weight array peaking at bottom_frame. Same as V1."""
```

**Verification (`test_whatif_physics.py`):**
1. **Stance widening:** Start from deep squat, widen stance by 10cm per side. Verify:
   - Knees track outward (knee X changes proportionally)
   - COM stays within support polygon
   - Pose is stable (kinetic energy < threshold)
   - Ankle/hip angles adjust to compensate

2. **Dorsiflexion increase:** Start from bottom squat with DF=15°. Increase DF limit to 30°, add DF perturbation. Verify:
   - Trunk becomes more upright (trunk flexion increases toward 180°)
   - This is the key cascading-chain test

3. **Asymmetric perturbation:** Add 10° DF to left ankle only. Verify:
   - Left hip and right hip respond differently
   - Pelvis tilts slightly to compensate

4. **Standing frames unaffected:** Apply taper to trajectory. Verify frames far from bottom are unchanged (taper ≈ 0).

5. **Performance:** Single solve < 50ms. Warp 150-frame trajectory < 200ms.

---

### Session 5: V2 Pipeline Orchestrator

**Goal:** Wire capture → filtering → MuJoCo IK → fault detection → rep segmentation into a single pipeline.

**Files to create:**
- `src/biomechanics_v2/pipeline.py`
- `tests/test_biomechanics_v2/test_pipeline_e2e.py`

**`pipeline.py` must provide:**
```python
class BiomechanicsV2Pipeline:
    def __init__(
        self,
        height_m: float = 1.75,
        weight_kg: float = 75.0,
        exercise_name: str = "Barbell Back Squat",
        enable_barbell: bool = True,
    ):
        """Initialize V2 pipeline.

        Components wired:
        - Pose estimation (from biomechanics.pose)
        - Pre-IK filters (from biomechanics.utils)
        - MuJoCo skeleton (from biomechanics_v2.model)
        - MuJoCo IK solver (from biomechanics_v2.solver)
        - Angle extractor (from biomechanics_v2.solver)
        - Fault detection (from biomechanics.faults)
        - Rep counter (from biomechanics.faults)
        - Barbell tracker (from biomechanics.barbell_tracking)
        """

    def process_frame(self, frame: np.ndarray, timestamp: float) -> PipelineFrame:
        """Process single video frame through V2 pipeline.

        Steps:
        1. Pose estimation → Skeleton2D, Skeleton3D
        2. Pre-IK filtering → filtered Skeleton3D
        3. Landmark adapter → (11, 4) targets
        4. MuJoCo IK → q-vector
        5. Angle extraction → JointAngles
        6. Fault detection → List[FaultEvent]
        7. Rep counting → Optional[RepData]
        8. Barbell tracking (parallel) → BarTrackState
        9. Pack into PipelineFrame

        Returns: PipelineFrame with per-layer latency_ms.
        """

    def on_bone_calibration_complete(self, proportions) -> None:
        """Called when BoneLengthConstraints finishes calibrating.
        Re-scales MuJoCo model from observed proportions.
        Re-calibrates fault detection thresholds.
        """

    def get_q_trajectory(self) -> np.ndarray:
        """Return accumulated (T, 20) q-trajectory for the current set."""

    def get_skeleton(self) -> MujocoSkeleton:
        """Return the MuJoCo skeleton model (for what-if solver)."""

    def reset(self) -> None:
        """Reset all stateful components for a new set."""
```

**Verification (`test_pipeline_e2e.py`):**
1. Feed 30 synthetic frames (Skeleton3D objects) through the pipeline
2. Verify PipelineFrame has non-None joint_angles for each frame
3. Verify fault detection runs (may produce no faults on clean synthetic data)
4. Verify q_trajectory shape is (30, 20)
5. Verify latency_ms is populated for each layer

---

### Session 6: HTML Visualizer

**Goal:** Build the interactive HTML output — Three.js skeleton, rep scrubbing, slider-based what-if perturbations.

**Files to create:**
- `src/biomechanics_v2/visualizer/__init__.py`
- `src/biomechanics_v2/visualizer/capture.py`
- `src/biomechanics_v2/visualizer/html_builder.py`
- `src/biomechanics_v2/visualizer/js_templates/viewer.js`
- `scripts/visualize_v2.py`

**`capture.py` — Live capture + recording:**
```python
class SquatCaptureSession:
    def __init__(
        self,
        pipeline: BiomechanicsV2Pipeline,
        video_source: int | str = 0,
        target_reps: int = 5,
    ):
        """Capture squat session using V2 pipeline."""

    def run(self) -> CaptureResult:
        """Run live capture with OpenCV preview.

        1. Standing gate validation (wait for calibrated standing pose)
        2. Record frames while squatting
        3. Stop after target_reps detected
        4. Return all frames, q-trajectory, reps, faults

        Returns: CaptureResult with video_path, q_trajectory, rep_boundaries, faults, skeleton_data.
        """
```

**`html_builder.py` — Self-contained HTML generation:**
```python
def build_html(
    capture_result: CaptureResult,
    skeleton: MujocoSkeleton,
    whatif_solver: MujocoWhatIfSolver,
    output_path: str,
    diagnosis: DiagnosisResult | None = None,
) -> str:
    """Build self-contained HTML file with embedded Three.js viewer.

    The HTML file contains:
    1. Embedded JSON data:
       - skeleton_def: joint hierarchy, offsets, bounds
       - q_trajectory: (T, 20) joint angles per frame
       - rep_boundaries: start/bottom/end frame indices per rep
       - faults: per-rep fault events with severity
       - athlete_stats: height, weight, body proportions

    2. Three.js 3D viewer:
       - Skeleton rendered as capsules (bones) + spheres (joints)
       - Color-coded joints (green=good, yellow=mild, red=severe)
       - Floor grid
       - Camera orbit controls

    3. Playback controls:
       - Play/pause, frame scrubber
       - Per-rep navigation
       - Speed control

    4. What-if slider panel:
       - Dorsiflexion (± degrees)
       - Stance width (± cm)
       - Toe-out angle (± degrees)
       - Knee tracking (± degrees)
       - Trunk lean (± degrees)

       Each slider triggers:
       a. Convert slider value → perturbation dict
       b. Call warp_trajectory() (pre-computed for all slider values at build time)
       c. Interpolate between original and corrected skeleton in real-time

    5. Display panels:
       - Current joint angles readout
       - Per-rep fault summary
       - Athlete stats (height, proportions, etc.)
       - If diagnosis provided: cause hierarchy with confidence scores

    The HTML must open with file:// protocol (no server needed).
    All JS/CSS is inlined. Three.js is loaded from CDN via <script> tag.
    """
```

**Pre-computation strategy for sliders:**
At build time, for each slider at its min/max values:
1. Run `whatif_solver.warp_trajectory()` → warped_q_trajectory
2. Run MuJoCo FK on warped trajectory → warped joint positions
3. Embed both original and warped position trajectories as JSON
4. In JS: interpolate between original and warped based on slider value (linear blend)

This means the HTML file is self-contained — no Python/MuJoCo needed at view time.

**`scripts/visualize_v2.py` — Entry point:**
```python
"""
Biomechanics V2 Squat Visualizer — MuJoCo Physics Pipeline

Usage:
  PYTHONPATH=src python scripts/visualize_v2.py [options]

Options:
  --height HEIGHT_CM    Athlete height in cm (default: 175)
  --weight WEIGHT_KG    Athlete weight in kg (default: 75)
  --source SOURCE       Video source: 0 (webcam), or path to video file
  --reps N              Number of reps to capture (default: 5)
  --output PATH         Output HTML path (default: session_v2_<timestamp>.html)
  --diagnose            Run diagnosis engine and include results in HTML
  --video-file PATH     Process existing video instead of live capture
"""
```

**Verification:**
1. Run `visualize_v2.py --video-file <test_video>` and verify HTML is generated
2. Open HTML in browser:
   - Skeleton renders correctly (standing pose, proportional limbs)
   - Playback scrubs through reps smoothly
   - Fault annotations appear at correct frames
   - Slider perturbations produce visible, physically plausible changes
   - "Widen stance" slider: knees move outward, trunk adjusts
   - "Increase dorsiflexion" slider: trunk becomes more upright
   - Standing frames remain unchanged when sliders are moved
3. File size: HTML < 5MB (reasonable for embedded trajectory data)
4. Three.js loads correctly (requires internet for CDN, or inline it)

---

## Dependencies

Add to `requirements.txt`:
```
mujoco>=3.5.0
mink>=0.2.0    # optional, only if using mink for IK
```

Both install via pip, no conda needed. MuJoCo is ~50MB. No GPU required — CPU is sufficient for single-body simulation.

---

## Key Design Principles

1. **MuJoCo is the single source of truth for physics.** No custom FK, no hand-rolled Jacobians, no geometric cost approximations. If MuJoCo can compute it, use MuJoCo.

2. **Reuse V1's capture/filtering stack.** Don't rewrite pose estimation, confidence blending, velocity clamping, bone constraints, or fault rules. They work. Import them.

3. **Same output types as V1.** The V2 pipeline produces `PipelineFrame` objects with `JointAngles`, `FaultEvent`, `RepData` — same types, same field names, same sign conventions. Downstream consumers (fault rules, rep counter) don't know they're running on MuJoCo.

4. **Forward dynamics replaces optimization.** The what-if solver doesn't minimize a cost function — it simulates physics. Gravity, contacts, and joint limits produce the answer.

5. **Pre-compute what-if results at build time.** The HTML viewer doesn't need MuJoCo at view time. All slider positions are pre-computed and embedded as JSON. The browser just interpolates.

6. **Match the existing q-vector format.** 20 DOFs, same order, same units (radians for angles, meters for translations). This ensures the diagnosis engine's perturbation format works unchanged.

---

## What This Does NOT Include (Future Work)

- Coaching pipeline (IPC bridge, voice agent integration)
- Muscle-level analysis (MS-Human-700 musculoskeletal model)
- Real-time inverse dynamics torque display
- Live overlay on rack screen
- MJX/GPU batch simulation
- Multi-exercise support (deadlift, row, etc. — squat only for now)

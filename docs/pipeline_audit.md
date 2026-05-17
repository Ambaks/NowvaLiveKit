# Pipeline Audit — Pre-Hypothesis Engine & Form Solver

Read-only analysis of the existing codebase to map all relevant modules, contracts, and gaps before building the hypothesis engine and form solver.

---

## Section 1: Pose Capture & Representation

### Entry Point
- **File:** `src/pose/pose_estimation_process.py` — launched as a subprocess by `src/main.py` when workout mode starts.
- **Function:** The subprocess imports `BiomechanicsPipeline` from `src/biomechanics/pipeline.py` and calls `process_frame()` in a loop.
- **Pipeline instantiation:** `src/biomechanics/pipeline.py:53-59` (`BiomechanicsPipeline.__init__`).

### Joint Count & Naming
- **19 keypoints** (COCO 17 + 2 foot index points).
- Defined in `src/biomechanics/pose/base.py:16-36` as `COCO_KEYPOINT_NAMES`:
  ```
  nose, left_eye, right_eye, left_ear, right_ear,
  left_shoulder, right_shoulder, left_elbow, right_elbow,
  left_wrist, right_wrist, left_hip, right_hip,
  left_knee, right_knee, left_ankle, right_ankle,
  left_foot_index, right_foot_index
  ```
- `NUM_KEYPOINTS = 19` (`src/biomechanics/pose/base.py:70`).

### Skeleton Topology
- Connections defined in `src/biomechanics/pose/base.py:39-54` (`COCO_SKELETON_CONNECTIONS`) — 14 limb pairs.

### Coordinate System
- **Analytical IK backend (default):** MediaPipe world coordinates — Y-down, X-left, Z-forward (toward camera). Units: **meters**. Origin at hip midpoint (per MediaPipe convention).
  - Stated explicitly in `src/biomechanics/kinematics/analytical_ik.py:35-38`.
- **Optimizer IK backend (skeleton module):** Y-up convention. The landmark adapter (`src/biomechanics/optimizer/landmark_adapter.py:54-57`) flips MediaPipe's Y-down to Y-up (`landmarks[:, 0] *= -1; landmarks[:, 1] *= -1`).
- **Units:** meters throughout (confirmed by `Skeleton3D` docstring at `src/biomechanics/utils/types.py:197`).

### Data Type / Container
- **Pydantic models** (`src/biomechanics/utils/types.py`):
  - `Skeleton2D` — list of `Keypoint2D(x, y, confidence)`.
  - `Skeleton3D` — list of `Point3D(x, y, z, confidence)`.
  - Both have `.to_numpy()` returning `(N, 3)` ndarray.
- Per-frame pipeline output is a `PipelineFrame` Pydantic model (`src/biomechanics/utils/types.py:558-600`).

### Storage Granularity
- Pose is processed **per-frame** and passed through the pipeline as a `PipelineFrame`.
- Per-rep data is aggregated into `RepData` (`src/biomechanics/utils/types.py:465-519`).
- The set-level collector (`src/biomechanics/analysis/set_finalizer.py`) accumulates hip-position and velocity time series as continuous trajectories for post-hoc analysis.

### Smoothing / Filtering
- **One Euro Filter** on joint angles: `src/biomechanics/utils/filters.py:46-153` (`OneEuroFilter`), applied via `JointAngleFilter` (`src/biomechanics/utils/filters.py:218-317`). Phase-adaptive parameters (idle/descending/bottom/ascending).
- **Keypoint position smoothing** (pre-IK): `src/biomechanics/utils/position_filter.py` (`KeypointPositionSmoother`).
- **Velocity clamping** (pre-IK): `src/biomechanics/utils/velocity_clamp.py` (`VelocityClamp`) — max 2.5 m/s per joint.
- **Bone length constraint enforcement** (pre-IK): `src/biomechanics/utils/bone_constraints.py` — projects distal keypoints onto calibrated-length spheres.
- **Confidence blending**: `src/biomechanics/utils/confidence_blend.py` — interpolates between raw and previous position based on confidence.
- **Predictive state estimator**: `src/biomechanics/utils/predictive_state.py` — 0.2s lookahead extrapolation.
- **Gaussian filter on optimizer IK trajectory**: `src/biomechanics/optimizer/ik.py:332` (`gaussian_filter1d` with sigma=1.5 frames).

---

## Section 2: Anthropometric Data

### Fields Stored Per User (Database)
From `src/db/models.py:17-29` (`User` model):
| Field | Type | Notes |
|-------|------|-------|
| `height_cm` | DECIMAL(5,2) | nullable |
| `weight_kg` | DECIMAL(5,2) | nullable |
| `age` | Integer | nullable |
| `sex` | String(10) | "male" or "female" |
| `extra_info` | Text | free-form voice-onboarding notes |

### Schema Location
- SQLAlchemy model: `src/db/models.py:16-38`.
- No Alembic migrations folder; migrations are individual scripts in `src/db/migrations/`.

### Anthropometric Fitting from Pose
- **Bone length calibration** runs during the first N standing frames: `src/biomechanics/utils/bone_constraints.py`. The `BoneLengthConstraints` class calibrates segment lengths for torso, thighs, shanks, arms.
- **Body proportions** derived post-calibration (`BodyProportions` dataclass at `src/biomechanics/utils/bone_constraints.py:34-53`): `hip_width`, `femur_length_avg`, `tibia_length_avg`, `torso_length_avg`, derived ratios, and pre-computed scale factors.
- **Skeleton scaling** (optimizer path): `src/biomechanics/skeleton/anthropometry.py:56-100` (`scale_skeleton(height_m, weight_kg)`) — scales offsets by `height_m / 1.75` and sets per-joint masses using de Leva (1996) fractions.

### Joint ROM Measurements
- **Per-user calibration** is stored in the DB: `src/db/models.py:343-356` (`UserCalibration`) — stores `movement_pattern`, `peaks` (JSONB), and `thresholds` (JSONB).
- Calibration is derived from the first clean reps via the pipeline's `CalibrationTracker` (`src/biomechanics/calibration.py`, imported in `src/pose/pose_estimation_process.py:27`).
- DB access: `src/db/calibration_utils.py` — `get_user_calibration()` and `get_user_calibration_full()`.
- **Individual ROM caps (ankle DF, hip flexion max, etc.) are NOT explicitly stored as named fields** — they exist implicitly within the `peaks` JSONB blob keyed by angle name.

---

## Section 3: Kinematic Features Already Computed

### Per-Frame Features (from `JointAngles` — `src/biomechanics/utils/types.py:227-363`)

| Feature | File | Function / Field | Units | Aggregation |
|---------|------|-----------------|-------|-------------|
| Hip flexion L/R | `analytical_ik.py` or `angle_extract.py` | `hip_flexion_l/r` | degrees | per-frame |
| Hip adduction L/R | same | `hip_adduction_l/r` | degrees | per-frame |
| Hip rotation L/R | same | `hip_rotation_l/r` | degrees | per-frame |
| Knee flexion L/R | same | `knee_flexion_l/r` | degrees | per-frame |
| Ankle dorsiflexion L/R | same | `ankle_dorsiflexion_l/r` | degrees | per-frame |
| Knee valgus L/R | same | `knee_valgus_l/r` | degrees | per-frame |
| Stance width ratio | `analytical_ik.py` | `stance_width_ratio` | ratio (ankle/shoulder) | per-frame |
| Toe-out angle L/R | `analytical_ik.py` | `toe_out_angle_l/r` | degrees | per-frame |
| Trunk flexion | same | `trunk_flexion` | degrees (180=upright) | per-frame |
| Trunk lateral flexion | same | `trunk_lateral_flexion` | degrees | per-frame |
| Trunk rotation | same | `trunk_rotation` | degrees | per-frame |
| Pelvis tilt/list/rotation | same | `pelvis_tilt/list/rotation` | degrees | per-frame |
| Shoulder flexion/abduction L/R | `analytical_ik.py` | `shoulder_flexion_l/r`, `shoulder_abduction_l/r` | degrees | per-frame |
| Elbow flexion L/R | `analytical_ik.py` | `elbow_flexion_l/r` | degrees | per-frame |
| Wrist position (relative to shoulder) | `analytical_ik.py` | `wrist_y_l/r`, `wrist_x_l/r` | cm | per-frame |

### Per-Frame Bar Tracking (from `BarTrackState` — `src/biomechanics/utils/types.py:148-166`)

| Feature | File | Units |
|---------|------|-------|
| Bar center (smoothed) | `barbell_tracking/tracker.py` | pixels |
| Bar tilt | same | degrees |
| Bar velocity | same | m/s (2D) |
| Bar acceleration | same | m/s² |
| Bar path history | same | list of (x,y) |

### Per-Rep Features (from `RepData` — `src/biomechanics/utils/types.py:465-519`)

| Feature | Units |
|---------|-------|
| `max_depth_angle` / `min_depth_angle` | degrees |
| `descent_time` / `ascent_time` | seconds |
| `peak_descent_velocity_cm_s` / `peak_ascent_velocity_cm_s` | cm/s |
| `avg_descent_velocity_cm_s` / `avg_ascent_velocity_cm_s` | cm/s |
| `depth_class` (0-4 from BiLSTM) | integer |
| `asymmetry` dict | degrees, keyed by joint |
| `faults` list | `FaultEvent` objects |

### Per-Rep Features (from `rep_segmenter.py`)
- Post-hoc segmentation: hip_position_cm time series, hip_velocity_cm_s, phase durations, pause detection.

### Downstream Consumption
- Frame data is sent to the voice agent via IPC every 10 frames (`src/biomechanics/coaching/ipc_bridge.py:62-78`).
- Faults and reps are sent over IPC as JSON messages to the coaching service.
- The `CoachingOrchestrator` consumes rep and fault events (see Section 7).

---

## Section 4: IK and Skeleton Infrastructure

### What the IK Code Actually Does

**Two independent IK paths exist:**

1. **Analytical IK** (`src/biomechanics/kinematics/analytical_ik.py`) — vector-geometry solver. Computes joint angles directly from 3D keypoint positions using dot products and cross products. No kinematic chain; operates on individual joints. This is the **default production path** (set in `config/biomechanics.yaml:21` → `backend: analytical`).

2. **Optimizer IK** (`src/biomechanics/optimizer/ik.py`) — L-BFGS-B optimizer fitting a 20-DOF articulated skeleton model to 3D landmarks. Minimizes positional error between FK-solved joint positions and observed landmarks, with joint limit bounds and optional knee-angle priors. This is the path used by the what-if solver / viewer module.

### File Paths

| Module | Path |
|--------|------|
| Analytical IK (production) | `src/biomechanics/kinematics/analytical_ik.py` |
| IK base class | `src/biomechanics/kinematics/base.py` |
| Optimizer IK (L-BFGS-B) | `src/biomechanics/optimizer/ik.py` |
| Skeleton model definition | `src/biomechanics/skeleton/definition.py` |
| Forward kinematics | `src/biomechanics/skeleton/forward_kin.py` |
| Anthropometric scaling | `src/biomechanics/skeleton/anthropometry.py` |
| Landmark adapter (COCO→skeleton) | `src/biomechanics/optimizer/landmark_adapter.py` |
| DOF→JointAngles converter | `src/biomechanics/optimizer/angle_extract.py` |
| What-if solver (SLSQP) | `src/biomechanics/optimizer/whatif.py` |
| Cost functions (5 terms) | `src/biomechanics/optimizer/costs.py` |
| Temporal Gaussian taper | `src/biomechanics/optimizer/temporal.py` |

### Rotation Representation
- **Euler angles** internally (intrinsic, per-joint axis order defined in `JointDef.dof_axes`).
- Converted to rotation matrices via `scipy.spatial.transform.Rotation.from_euler()` in `src/biomechanics/skeleton/forward_kin.py:33-35`.
- DOF values stored in radians in the `q` vector; joint limits defined in degrees in `definition.py` and converted to radians in `bounds()`.

### Kinematic Chain Root
- **Pelvis-rooted.** The pelvis is the root joint (parent=None) with 6 DOF (tx, ty, tz, rx, ry, rz). Defined at `src/biomechanics/skeleton/definition.py:19-22`.

### Forward Kinematics — Standalone Callable
- **Yes.** `src/biomechanics/skeleton/forward_kin.py:39` — `forward_kinematics(skeleton, q)` returns `dict[str, np.ndarray]` of 4×4 transforms.
- Also: `joint_world_position()`, `body_com_world()`, `load_reference_point()`, `midfoot_xz()`.

### Optimization Libraries in Dependencies
- **scipy** (>=1.10.0) — used for `minimize` (L-BFGS-B, SLSQP), `Rotation`, `gaussian_filter1d`, `find_peaks`.
- **OpenSim** — commented out in `requirements.txt` (`# conda install -c opensim-org opensim`). Referenced in `biomechanics/__init__.py` docstring as "week6_moco" but no actual OpenSim code in the active pipeline.
- No casadi, pinocchio, pyroki, or jaxopt in the repo.

---

## Section 5: Spine Modeling

### Torso Segmentation
- **Two segments:** pelvis + trunk.
- **Pelvis joint** (root): 6 DOF — 3 translational + 3 rotational. Defined at `src/biomechanics/skeleton/definition.py:19-22`.
- **Trunk joint** (child of pelvis): 2 DOF (rx, rz) — flexion/extension and lateral flexion. Offset (0.0, 0.28, 0.0) from pelvis. Defined at `src/biomechanics/skeleton/definition.py:23-25`.
- There is **no** separate lumbar vs. thoracic joint. The trunk is a single rigid segment above the pelvis.

### Connection
- Trunk is parented to pelvis with a fixed offset of 28 cm upward (at reference height 1.75 m, scaled by anthropometry).

---

## Section 6: Existing Fault Detection

### CNN-GRU Squat Fault Classifier
- **Not present.** No CNN-GRU model exists in the codebase. Fault detection is entirely **rule-based** via the `RuleEngine` (`src/biomechanics/faults/rule_engine.py`).

### BiLSTM Depth Classifier
- **File:** `src/biomechanics/ml/bilstm_model.py`
- **Architecture:** 2-layer BiLSTM (hidden=128, bidirectional) → FC(256→64→ReLU→Dropout→num_classes). Input dim=14, output=5 classes.
- **Output classes (5):** Standing (0), Quarter (1), Half (2), Parallel (3), Deep (4). Defined at `src/biomechanics/utils/types.py:429-443`.
- **Inference wrapper:** `src/biomechanics/ml/inference.py` (`BiLSTMInference.process_skeleton()`).
- **Feature extractor:** `src/biomechanics/ml/feature_extractor.py` — 14-dimensional vector (4 angles + 6 normalized bone lengths + 4 normalized y-diffs).
- **Model path:** `models/bilstm_rep_counter.pt` (from config).

### Inference Latency Target
- Pipeline target: 30 FPS (`config/biomechanics.yaml:2` → `target_fps: 30`), i.e., ~33ms total budget per frame.
- BiLSTM runs on CPU (config `device: cpu`), window size 30 frames.
- No explicit latency measurement for the BiLSTM sub-step alone; total pipeline latency is tracked per-layer in `PipelineFrame.latency_ms`.

### Classifier Output Structure
- BiLSTM outputs **per-frame logits** `(1, 30, 5)` → softmax → last-frame probabilities → fed into `BiLSTMRepCounter` for phase detection and rep counting.
- Result: per-frame `depth_class` (int 0-4) and `class_probabilities` (5 floats).
- On rep completion, `depth_class` is attached to `RepData`.

### Rule-Based Fault Detection (Primary System)
- **Engine:** `src/biomechanics/faults/rule_engine.py` (`RuleEngine`)
- **14 fault types** (enum at `src/biomechanics/faults/fault_types.py:17-33`):
  - DEPTH, RANGE_OF_MOTION, BILATERAL_ASYMMETRY, HEEL_RISE, FORWARD_LEAN, KNEE_VALGUS, BACK_ROUNDING, LOCKOUT, ELBOW_FLARE, BAR_PATH, SHOULDER_STABILITY, TRUNK_STABILITY, TEMPO, LIMITED_DORSIFLEXION, BAR_DRIFT
- **15 rule implementations** in `src/biomechanics/faults/rules/` (one file per rule).
- Output: `List[FaultEvent]` per frame, with `fault_type`, `severity` (none/mild/moderate/severe), `severity_score` (0-3), `message`, frame/rep metadata.

### Downstream Consumption of Fault Detections
- Faults → `IPCBridge.send_fault()` → JSON over UNIX socket → `CoachingService` → `CoachingOrchestrator.on_fault()` → cached audio cue dispatch.
- Faults accumulated per-rep in `RepData.faults`.
- Per-set fault summary computed by orchestrator for LLM set/exercise recaps.

---

## Section 7: Coaching Orchestrator

### File Path
- `src/services/coaching_orchestrator.py`

### Fault → Cue Mapping
- **Rule-based mapping** via `CueCache` (`src/biomechanics/coaching/cue_cache.py`):
  - Each fault type maps to a `cue_key` string (e.g., `"knee_valgus"` → `"knees_out"`).
  - `cue_cache.get_cue_for_fault(fault_type, timestamp)` returns the cue key with rate-limiting.
  - Exercise-specific cue dictionaries: `SQUAT_CUES`, `DEADLIFT_CUES`, `DEFAULT_CUES` (defined in `src/biomechanics/coaching/cue_cache.py:27-60`).

### Audio Cue Selection
- Cues are indexed by `cue_key` string.
- Pre-cached at exercise start via `IPCBridge.prepare_exercise()` which calls `cue_cache.prepare_for_exercise(exercise_name)`.
- The `AudioCueService` (referenced in `CoachingService`) pre-generates TTS audio for each cue key and stores them for instant playback.
- Selection: fault cues are deterministic (fault_type → cue_key); positive cues are randomly chosen from a configurable list.

### Latency: Fault Detection → Cue Dispatch
- IPC message sent immediately on fault detection (pipeline → bridge → UNIX socket).
- `CoachingOrchestrator` rate-limits to **8 seconds** between fault cues (`_min_fault_cue_gap`).
- Stale cues (>1.0s in queue) are dropped (`_dispatch_cached_cue`, line 567).
- LLM audio is ducked while cached cue plays.
- Effective latency: ~1 IPC frame interval (every 10 frames @ 30fps ≈ 333ms for frame_data; faults are sent immediately when detected).

---

## Section 8: Voice Agent Integration

### Agents That Consume Fault Detection
1. **WorkoutAgent** (`src/agents/workout_agent.py`) — active during working sets. Delegates biomechanics handling to `CoachingService`.
2. **TeachingAgent** (`src/agents/teaching_agent.py`) — active during beginner onboarding. Receives `frame_data`, `fault`, and `rep_complete` events directly via `on_biomechanics_event()` (forwarded by `CoachingService` in teaching mode).

### Data Contract (Vision Pipeline → Agents)
- **Transport:** UNIX domain socket IPC (`src/core/ipc_communication.py`). 4-byte length-prefix framing + JSON payload.
- **Message types** sent by `IPCBridge`:
  - `{"type": "frame_data", "joint_angles": {...}, "fps": float, "frame_index": int}` — every 10 frames.
  - `{"type": "fault", "fault_type": str, "severity": str, "severity_score": float, "message": str, "cue": str|null, "rep_number": int}` — on detection.
  - `{"type": "rep_complete", "rep_number": int, "max_depth_angle": float, "depth_category": str, "faults_in_rep": [...], "rep_duration_ms": int, "descent_time_s": float, "ascent_time_s": float, ...}` — on rep completion.
  - `{"type": "rep_count", "value": int}` — backward compat.
  - `{"type": "set_complete", ...}` — on set end.
  - `{"type": "pipeline_status", "status": str, "latency_ms": {...}}` — health.
  - `{"type": "cache_cues", "exercise_name": str, "cues": {...}}` — pre-set cue list.

### Structured Event Push Mechanism
- **Yes.** The IPC bridge already pushes structured JSON events. Any new event type (e.g., `"type": "hypothesis"`) can be added by sending through `ipc_client.send_message({...})` on the pipeline side and handling it in `CoachingService._handle_ipc_message()`.

---

## Section 9: Rendering / Visualization

### Live Skeleton Rendering on Rack Screen
- **Not present in production.** There is no live 3D skeleton overlay running on the rack's display during workouts.
- The `src/biomechanics/viz/overlay_2d.py` draws a 2D skeleton on OpenCV frames (for debugging / the `visualize_video_squats.py` script), not on a live display.

### Offline Viewer (Desktop, Not Production)
- **PyWebView + Three.js** viewer: `src/biomechanics/viewer/app.py` and `src/biomechanics/viewer/api.py`.
  - Launches a native desktop window via `pywebview`.
  - Three.js renders the skeleton in the browser context.
  - Python `KinodynamicsAPI` exposes `warp_rep()` (what-if solve + gaussian taper) to JS via `window.pywebview.api`.
  - This is an **offline replay/analysis tool**, not a live production overlay.

### Frontend Demo (Web App)
- `frontend_demo/` — React + TypeScript web app.
- **No 3D rendering.** No Three.js, react-three-fiber, or WebGL dependencies in `package.json`. The frontend is for program management/scheduling, not pose visualization.

### Display Target
- Not specified in code. The rack's physical screen specs are not defined in the codebase.

---

## Section 10: Storage Schema

### Database
- **PostgreSQL** (production). `psycopg2-binary` in requirements. Connection via SQLAlchemy.
- Schema defined in `src/db/models.py`.

### Per-User Record (`User`)
`height_cm`, `weight_kg`, `age`, `sex`, `extra_info`, `username`, `name`, `email`, `password_hash`, `created_at`, `updated_at`.

### Per-User Calibration (`UserCalibration`)
`user_id`, `movement_pattern`, `peaks` (JSONB), `thresholds` (JSONB), `calibration_reps`, `created_at`, `updated_at`.

### Per-Session Record
- **Not present as a database model.** Session state is tracked in-memory by `SessionState` (`src/biomechanics/utils/types.py:522-551`) and `WorkoutSession` (`src/core/workout_session.py`). No persistent "session" table exists.
- Agent state is persisted to a JSON file (`.agent_state_*.json`) for crash recovery but not to the DB.

### Per-Rep Record
- **Not present as a database model.** `RepData` is a Pydantic model (`src/biomechanics/utils/types.py:465-519`) held in memory during the set, used for IPC messages and set reports, then discarded.
- `ProgressLog` (`src/db/models.py:186-203`) stores completed set data (`performed_reps`, `performed_weight`, `rpe`, `measured_velocity`, `velocity_loss`) but NOT per-rep biomechanics.

### Per-Rep Fields (In-Memory `RepData`)
`rep_number`, `start_time`, `end_time`, `start_frame`, `end_frame`, `max_depth_angle`, `min_depth_angle`, `descent_time`, `ascent_time`, `peak_descent_velocity_cm_s`, `peak_ascent_velocity_cm_s`, `avg_descent_velocity_cm_s`, `avg_ascent_velocity_cm_s`, `faults` (list), `asymmetry` (dict), `depth_class`, `depth_class_name`, `max_depth_class`.

---

## Section 11: Existing Code That Looks Like Hypothesis-Engine or Form-Solver Logic

### Rule-Based Diagnosis / Corrective Recommendations
- **Partial — fault-to-cue mapping only.** The `CueCache` maps fault types to corrective cue keys (e.g., knee_valgus → "knees_out"). This is a shallow 1:1 lookup, not a causal graph or multi-hypothesis diagnosis.
- The `TeachingAgent` (`src/agents/teaching_agent.py:59-83`, function `_trunk_flexion_fix`) contains a **small decision tree** that maps stance ratio + toe-out angle to a specific corrective recommendation string. This is the closest thing to diagnosis logic.
- No module exists that maps faults to candidate *causes* (e.g., "forward lean could be due to limited ankle dorsiflexion OR weak quads OR high bar position").

### Corrected / Ideal Reference Pose Generation
- **Yes — the what-if solver.** `src/biomechanics/optimizer/whatif.py` (`whatif_solve()`) takes a fitted pose (`q_fitted`), a `perturbation` dict (joint deltas), and produces a `q_corrected` via constrained SLSQP optimization with:
  - Feet-rooted equality constraint (ankles don't move).
  - COM-inside-support-polygon inequality constraint.
  - 5 soft cost terms (pose deviation, torque proxy, load-over-midfoot, knee tracking, balance margin).
- The viewer's `warp_rep()` (`src/biomechanics/viewer/api.py:49-117`) applies the corrected pose across the rep trajectory using a Gaussian taper centered on the bottom frame.
- **This is precisely the "form solver" substrate.** The missing piece is automated perturbation selection (currently manual via sliders in the Three.js viewer).

### OpenSim / Stability Optimizer
- **OpenSim is NOT in the active codebase.** It's referenced as a comment in `requirements.txt` and in a docstring in `biomechanics/__init__.py` ("week6_moco"). No OpenSim Python code exists.
- The `complete_pipeline.py` file references a `SimpleLowerBodyIK` and a `muscle_predictor` model, but this is a **legacy/prototype file** that imports from non-existent paths (`week1_pose`, `week2_stereo`, etc.) and is not wired into the production pipeline.

---

## Section 12: Gaps & Open Questions

### Blockers for Hypothesis Engine

1. **No causal knowledge graph exists.** The fault rules detect symptoms but do not reason about causes. Building the hypothesis engine requires authoring the symptom→cause→evidence→modifiability graph from scratch.

2. **Per-user ROM is stored as opaque JSONB, not structured fields.** The hypothesis engine needs to query specific values (e.g., "max ankle dorsiflexion for this user") programmatically. The current `peaks` blob likely contains this, but the schema is implicit and undocumented. You'll need to inspect actual stored values to confirm field names.

3. **No user anthropometric segment lengths are persisted to DB.** `BodyProportions` is computed fresh each session from bone calibration. If the hypothesis engine needs femur/tibia ratios across sessions, these need to be persisted.

4. **No "modifiability tier" concept exists.** The system doesn't distinguish structural limitations (short tibias) from mobility limitations (tight ankles) from motor control issues (poor bracing). This classification is entirely new.

### Blockers for Form Solver

1. **The what-if solver already exists** (`whatif_solve`) — it just lacks an automated front-end. The main gap is connecting hypothesis engine output (parameter deltas) to `whatif_solve()`'s `perturbation` dict.

2. **Live overlay rendering does not exist.** The viewer is an offline desktop tool (PyWebView). Morphing the corrected pose onto a live video feed on the rack screen requires a new rendering pipeline (WebSocket-fed Three.js overlay or OpenGL).

3. **Optimizer IK and Analytical IK produce different representations.** The what-if solver operates on the 20-DOF `q` vector from the optimizer IK path. The production pipeline uses the analytical IK path which produces `JointAngles` directly. To use the form solver in real-time, either:
   - Run the optimizer IK in production (heavier, ~3-5ms per frame for `fit_frame`), or
   - Build a `JointAngles → q` converter (inverse of `q_to_joint_angles`).

4. **No foot-placement optimization.** The what-if solver fixes feet. If the hypothesis engine recommends "widen stance by 5 cm," the solver needs `foot_target_delta` support — which exists (`whatif_solve` accepts it) but has no logic to compute it from a coaching recommendation.

### Surprising / Notable Findings

1. **Two completely independent IK systems** coexist: analytical (production) and optimizer-based (offline viewer). They produce compatible `JointAngles` output but follow different code paths with different coordinate conventions.

2. **The `complete_pipeline.py` is dead code.** It imports from non-existent module paths (`week1_pose`, `week2_stereo`, etc.) and is never imported by any live module. It appears to be a legacy prototype from an earlier development phase.

3. **Per-rep data is ephemeral.** Despite computing rich per-rep biomechanics (depth, velocity, faults, asymmetry), none of it is persisted to the database. Only aggregate set stats (`ProgressLog`: reps performed, weight, RPE, velocity) survive beyond the session.

4. **The BiLSTM is a depth classifier, not a fault classifier.** It classifies squat depth into 5 bins (Standing→Deep). All actual fault detection is rule-based. There is no learned fault model.

### Convention Mismatches

1. **Coordinate flip between pipelines:** Analytical IK uses MediaPipe Y-down; optimizer skeleton uses Y-up. The `landmark_adapter.py` handles this, but any new module bridging both must be aware.

2. **Trunk flexion sign convention:** Analytical IK outputs `trunk_flexion` where 180° = upright, decreasing with forward lean. The optimizer's `trunk.rx` DOF is 0° = upright, positive = flexion. `q_to_joint_angles()` handles this (line 63: `180.0 - trunk_from_vertical`), but direct comparisons between raw `q` values and `JointAngles` fields need care.

3. **Joint naming:** COCO uses `left_hip`, `right_hip`; skeleton model uses `L_hip`, `R_hip`. The landmark adapter maps between them.

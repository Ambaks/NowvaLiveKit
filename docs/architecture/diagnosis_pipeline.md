# Diagnosis Pipeline: Raw Data to Outputs

Complete technical reference for the Nowva biomechanics diagnosis pipeline. Covers every processing step from raw camera frames to structured coaching outputs.

The system has two layered pipeline paths:

1. **Real-time pipeline** (`src/biomechanics/pipeline.py`) — runs frame-by-frame during a workout at ~30 FPS
2. **Post-set diagnosis engine** (`src/biomechanics/diagnosis/engine.py`) — runs causal analysis after a set completes

The real-time pipeline produces the data the diagnosis engine consumes.

---

## Part 1: Real-Time Pipeline

Each call to `BiomechanicsPipeline.process_frame()` runs one full iteration and returns a `PipelineFrame` with all results and per-layer timing.

### Step 0: Configuration & Initialization

**Files**: `src/biomechanics/config.py`, `src/biomechanics/profiles/squat.py`

All tuning knobs are loaded from a YAML file into typed Python objects before anything runs. `config.py` defines ~20 nested Pydantic `BaseModel` classes — one per subsystem. `load_pipeline_config()` reads `config/biomechanics.yaml`, parses it section by section, and returns a `BiomechanicsConfig` instance. Every downstream component receives this config at construction time.

The exercise profile is loaded from the registry (e.g. `SquatProfile`). The profile is a strategy object that bundles together which fault rules to activate, how to compute the rep-counting signal, and how to calibrate thresholds to the specific user. This is how the system supports different exercises without changing pipeline code.

### Step 1: Frame Capture

The camera produces frames at its own rate (typically 30 FPS). A background daemon thread runs `_capture_loop()`, which calls `cv2.VideoCapture.read()` in a tight loop, storing each new frame under a mutex lock. When `process_frame()` is called, it grabs the latest frame under the same lock. This takes microseconds — the "capture latency" is just the lock acquisition time. If no frame has arrived yet, the method returns an empty `PipelineFrame`.

This design ensures the pipeline always processes the freshest available frame, rather than queuing up stale frames when processing takes longer than one frame period.

### Step 2: Barbell Detection + Tracking (Optional)

**Files**: `src/biomechanics/barbell_tracking/detector.py`, `src/biomechanics/barbell_tracking/kalman.py`

A YOLO11n-pose model runs on the raw frame and outputs a bounding box plus 2 keypoints: the left and right endpoints of the barbell. This gives both position and tilt angle in a single inference pass.

Each endpoint is fed into a **constant-velocity Kalman filter** that maintains a state estimate `[x, y, vx, vy]`, predicts where the endpoint should be based on velocity, then corrects using the measurement. This produces smooth, continuous tracking even through detection dropouts.

Output: `BarTrackState` containing bar center position, tilt angle in degrees, lateral deviation from the centerline, and a rolling path history (120 frames ~ 4 seconds).

This runs independently of pose estimation — it's a parallel branch that only joins the main pipeline when fault rules evaluate.

### Step 3: Pose Estimation

**Files**: `src/biomechanics/pose/mediapipe_fallback.py`, `src/biomechanics/pose/rtmpose.py`

Detects the human body in the image and outputs the 3D positions of 19 body landmarks.

The frame is converted from BGR to RGB and passed to MediaPipe's `PoseLandmarker`. MediaPipe internally runs a two-stage pipeline: a person detector finds the bounding box, then a pose model estimates 33 BlazePose landmarks within that box. It outputs two sets of landmarks:

1. **Normalized 2D landmarks**: x,y coordinates normalized to [0,1] relative to the image, plus a visibility score per keypoint
2. **World landmarks**: x,y,z coordinates in meters, centered at the hip midpoint, with Y pointing downward (gravity direction)

MediaPipe uses 33 landmarks (BlazePose format), but the rest of the pipeline uses COCO 17 format (plus 2 foot indices = 19 total). Conversion functions remap using a hardcoded lookup table (`BLAZEPOSE_TO_COCO`). Any keypoint with confidence below threshold (default 0.3) is zeroed out.

Output: `Skeleton2D` (pixel coordinates for visualization) and `Skeleton3D` (meters for computation). If no person is detected, both are None and the pipeline returns early.

### Step 4: BiLSTM Depth Classification (Optional)

**Files**: `src/biomechanics/ml/inference.py`, `src/biomechanics/ml/bilstm_counter.py`

A BiLSTM neural network classifies each frame into one of 5 depth classes: standing / quarter / half / parallel / deep. It operates on a window of skeleton features extracted from the raw `Skeleton3D` before any filtering, and outputs class probabilities via softmax.

A rep is counted when the depth class rises above `min_depth_class` (default: parallel) and then returns to standing. When both BiLSTM and rule-based systems are active, the BiLSTM's rep boundaries are used as primary, but enriched with the rule-based system's fault data and timing metrics.

### Step 5: Standing Pose Gate (Unconditional)

**File**: `src/biomechanics/utils/standing_gate.py`

Validates that the camera can see a human standing upright before allowing any analysis to begin. Runs every frame and checks:

1. **Keypoint visibility**: All 8 major keypoints (both shoulders, hips, knees, ankles) must have confidence >= 0.5
2. **Knee extension**: Both knees nearly straight (flexion < 20°). Computed as `180° - joint_angle(hip, knee, ankle)`
3. **Torso upright**: Trunk angle from vertical < 25°. Handles both Y-up and Y-down coordinate systems by taking `min(angle, 180° - angle)`
4. **Distance plausibility**: Torso length (shoulder-to-hip distance) between 0.25m and 0.80m

All 4 must pass. A single failure resets the consecutive-pass counter to 0. After 5 consecutive passing frames, the gate latches open permanently for the session. Diagnostic logging fires every 30 failing frames with details about which check failed.

### Step 6: Readiness Gate (Per-Set)

Identical mechanism to the standing gate (same `StandingPoseGate` class) but with more lenient thresholds: 35° knee/trunk tolerance, 0.15–1.00m torso length range, 30 consecutive frames required. Resets between sets so each set starts with clean data.

**All downstream processing is gated on this.** If not ready, `process_frame()` returns early with only skeleton data. No IK, no faults, no rep counting.

### Step 7: Pre-IK Skeleton Filtering (Optional, 5-Stage Chain)

**Files**: `src/biomechanics/utils/confidence_blend.py`, `src/biomechanics/utils/velocity_clamp.py`, `src/biomechanics/utils/bone_constraints.py`, `src/biomechanics/utils/position_filter.py`

Cleans up the raw 3D skeleton before computing joint angles. Enabled via `ENABLE_PREIK_FILTERS=true`.

#### 7a. Confidence Blending

For each keypoint, computes a blend weight from its confidence score (linearly mapped between `min_confidence` and `max_confidence` to [0, 1]). High-confidence keypoints are used as-is. Low-confidence keypoints are blended toward their previous position. This prevents sudden jumps when a keypoint becomes partially occluded.

#### 7b. Velocity Clamping

Computes the velocity of each keypoint (position change / time delta) and caps it at 2.5 m/s. Movement faster than that is physically impossible during a squat, so it's clamped. This kills single-frame impulse noise where a keypoint teleports.

#### 7c. Bone Length Constraints (First Pass)

During the first 30 standing frames, measures anatomical segment lengths (thigh, shin, torso) and averages them. After calibration, enforces these lengths: if hip-to-knee distance is longer than calibrated, the knee is pulled back toward the hip. Also computes `BodyProportions` (femur/torso ratio, tibia/femur ratio, hip width) used for personalized fault thresholds.

#### 7d. Position Smoothing

One Euro Filter runs independently on each keypoint's x, y, z coordinates. Adaptive: heavy smoothing when stationary, lighter smoothing when moving. Parameters: `min_cutoff=0.8`, `beta=4.0`, `d_cutoff=1.0`.

#### 7e. Bone Length Constraints (Second Pass)

The position smoother can cause small bone length violations (smoothing hip and knee independently may stretch the thigh). This second enforcement pass corrects those violations.

After bone calibration completes, body proportions propagate to the IK solver (pelvis tilt coupling) and fault rules (threshold scaling).

### Step 8: Inverse Kinematics

**File**: `src/biomechanics/kinematics/analytical_ik.py`

Converts 3D keypoint positions into 22 joint angles using vector geometry. No neural network or musculoskeletal model — pure trigonometry.

**Lower body angles**:
- **Knee flexion**: `180° - joint_angle(hip, knee, ankle)`. 0° = straight leg, 90° = deeply bent.
- **Hip flexion**: Angle between thigh vector (hip→knee) and downward vertical. 0° standing, increases with flexion.
- **Hip adduction**: Medial/lateral deviation of thigh from the sagittal plane. Positive = adduction, negative = abduction.
- **Knee valgus**: Frontal-plane deviation of knee from hip→big-toe reference line. Positive = valgus (knee inward), negative = varus (knee outward). Uses 2D cross product for sign determination.
- **Ankle dorsiflexion**: Shank tilt from vertical. 0° = shin perfectly vertical.

**Trunk angles**:
- **Trunk flexion**: `180° - angle(trunk_vector, vertical)`. 180° = upright, decreasing with forward lean.
- **Trunk lateral flexion**: Side-to-side lean in the frontal plane.
- **Trunk rotation**: Axial rotation in the transverse plane.

**Pelvis angles**:
- **Pelvis tilt**: Approximated from trunk angle scaled by a coupling factor (default 0.4, updated by body proportions). True pelvis tilt requires ASIS/PSIS markers that pose estimation can't see.
- **Pelvis list**: Lateral hip hiking from height difference between hips.
- **Pelvis rotation**: Axial rotation from hip line vector.

**Upper body angles**:
- **Elbow flexion L/R**: `180° - joint_angle(shoulder, elbow, wrist)`.
- **Shoulder flexion L/R**: Angle between upper arm and trunk vector.
- **Shoulder abduction L/R**: Lateral deviation of upper arm from trunk in frontal plane.
- **Wrist positions**: Relative to shoulder midpoint, in centimeters.

Output: `JointAngles` dataclass with all angles in degrees plus derived properties (`avg_knee_flexion`, `knee_asymmetry`, `hip_asymmetry`).

### Step 9: Temporal Filtering

**Files**: `src/biomechanics/utils/filters.py`, `src/biomechanics/utils/derivatives.py`

- **One Euro Filter on angles**: Applied to each joint angle independently. Phase-aware: tightens smoothing during bottom holds (for stable depth measurement), loosens during ascent/descent (to track fast changes without lag).

- **Derivative Tracker**: For each angle, computes velocity as `(current - previous) / dt` smoothed with EMA (alpha=0.3). Acceleration is the derivative of velocity. Prevents derivative blowup from frame-to-frame noise.

### Step 10: Rep Signal Computation

**File**: `src/biomechanics/profiles/squat.py`

The exercise profile produces a single number per frame that tells the rep counter where the user is in the movement.

For squats: `(hip_mid_y - ankle_mid_y) * 100.0` — hip vertical position in centimeters relative to ankles. In MediaPipe's Y-down coordinate system, this value is negative when standing and becomes less negative / more positive as the user squats deeper. Different exercises use different signals (trunk flexion for deadlifts, elbow flexion for curls).

### Step 11: Predictive State Estimation (Optional)

**File**: `src/biomechanics/utils/predictive_state.py`

Extrapolates joint angles 200ms ahead: `predicted = current + velocity * horizon_seconds`. Clamped to ±15° from current value. Used only for fault evaluation — not for rep counting or display.

This compensates for system latency: by the time a fault is detected and a voice cue delivered, the user may have already moved past the problematic position. Predictive estimation detects faults slightly before they fully manifest.

### Step 12: Fault Detection

**File**: `src/biomechanics/faults/rule_engine.py`

The `RuleEngine` maintains a rolling history of 90 frames (~3 seconds at 30 FPS) and evaluates each rule every frame.

**Squat fault rules** (from `SquatProfile`):

| Rule | What it checks | When it fires |
|------|---------------|---------------|
| **DepthRule** | Max knee flexion vs. thresholds (quarter <60°, half <90°, parallel <100°) | At rep completion |
| **ForwardLeanRule** | `trunk_flexion` vs. mild/moderate/severe thresholds (135°/125°/115°) | During reps |
| **KneeValgusRule** | Max of abs(knee_valgus L/R) vs. thresholds (8°/13°/18°) | During reps |
| **SymmetryRule** | Max of knee/hip flexion L-R difference vs. thresholds | During reps |
| **BarTiltAsymmetryRule** | Bar tilt angle and endpoint height difference | When bar detected |

Each rule returns a `FaultEvent` with: fault type, severity (MILD/MODERATE/SEVERE), severity score (0-1), human-readable message, timestamp, frame index, and rep number. Consecutive same-fault frames are deduplicated with a 15-frame minimum gap.

### Step 13: Baseline Calibration

**File**: `src/biomechanics/profiles/squat.py`

During the first rep, `record_calibration_frame()` tracks peak angle values:
- Peak trunk flexion (minimum `trunk_flexion`, since lower = more lean)
- Peak hip adduction and knee valgus per rep
- Peak bilateral asymmetry
- Peak dorsiflexion drop from standing baseline

After the first clean rep completes, `apply_baseline()` adjusts thresholds:
- **Forward lean**: thresholds shift to peak - 10/15/20°
- **Knee valgus**: thresholds become peak + 5/10/15°
- **Symmetry**: thresholds become peak + 5/10/15°

This means the system only flags things significantly worse than the user's natural pattern, reducing false alarms.

### Step 14: Rep Counting

**File**: `src/biomechanics/faults/hip_position_counter.py`

A 4-state machine driven by the rep signal and its causal velocity:

```
IDLE → DESCENDING → BOTTOM → ASCENDING → IDLE
```

| Transition | Condition |
|-----------|-----------|
| IDLE → DESCENDING | velocity > 3 cm/s |
| DESCENDING → BOTTOM | abs(velocity) < 5 cm/s (after min 3 frames) |
| BOTTOM → ASCENDING | velocity < -3 cm/s (after min 2 frames) |
| ASCENDING → IDLE | position returns within 3 cm of baseline (after min 3 frames) |

**Rep validation** (on ASCENDING → IDLE):
- Total frame count >= 15 (~0.5s at 30 FPS)
- Depth displacement >= 10 cm

Valid rep → increment count, create `RepData`. Invalid → feedback ("go_deeper").

**Metrics tracked during reps**: max/min depth angle, bottom time, accumulated faults, running knee/hip asymmetry averages. Packaged into `RepData` on completion.

### Step 15: Pipeline Output

Returns `PipelineFrame` dataclass with: frame index, timestamp, skeleton 2D/3D, joint angles, fault list, rep data (if completed), BiLSTM predictions, barbell tracking state, and per-layer latency dictionary. Every field is optional.

---

## Part 2: Post-Set Analysis

### Step 16: Set Data Collection

**File**: `src/biomechanics/analysis/set_finalizer.py`

`SetDataCollector` accumulates every frame's data during a set into arrays: timestamps, hip midpoint Y, knee/hip/trunk angles (both raw 3D and pipeline-IK versions), hip adduction L/R, bilateral asymmetry, rep events, fault events, and raw 3D keypoint positions.

### Step 17: Set Finalization

After a set ends, `finalize_set()` processes accumulated data:

1. **Smoothing**: Median filter (window=5) kills impulse noise, then simple moving average (window=2-3) for smoothness. SMA starts 1.5 seconds into the set to avoid boundary effects.

2. **Plot generation**: 5-6 matplotlib figures per set — hip position, velocity, raw joint angles, pipeline joint angles, hip adduction, bilateral asymmetry.

3. **Data export**: Two JSON files per set — raw frame data and smoothed plot data with all time series.

4. **Rep segmentation**: `segment_set()` uses scipy peak-finding on smoothed hip position to identify rep boundaries post-hoc. More accurate than real-time counting with full context. Generates a segmentation plot and markdown report.

5. **HTML dashboard**: `generate_set_dashboard()` creates an interactive HTML page with all plots, rep metrics, and fault timeline.

The collector resets after finalization.

---

## Part 3: Diagnosis Engine (Post-Set Causal Analysis)

### Step 18: Bridge — Frame Data to Engine Input

**File**: `src/biomechanics/diagnosis/bridge.py`

Transforms per-rep bottom-frame data into the structured format the diagnosis engine expects.

- `find_bottom_frame()`: Returns the frame with maximum knee flexion (most informative for fault analysis).

- `build_rep_kinematic_summary()`: From the bottom frame, extracts:
  - Trunk pitch: `180° - trunk_flexion` (0 = upright, positive = lean)
  - Knee valgus L/R, ankle dorsiflexion L/R (directly from angles)
  - Hip Y and Knee Y at bottom (centimeters, for parallel depth check)
  - Stance width ratio: ankle-to-ankle XZ distance / shoulder width
  - Foot direction angle: ankle→big-toe vector angle from straight ahead (toe-out)
  - Depth class: 0=quarter, 1=half, 2=above-parallel, 3=parallel, 4=below-parallel

- `build_anthro_dict()`: Creates anthropometry dictionary from calibrated body measurements — femur/torso ratio, hip width, shoulder width, segment lengths.

- `build_rom_dict()`: Creates range-of-motion dictionary from baseline peak values — maximum dorsiflexion demonstrated, maximum depth achieved. These are the user's demonstrated capacity, not population norms.

- `build_set_features()`: Combines per-rep kinematics + anthropometry + ROM into `SetFeatures`.

### Step 19: Symptom Detection

**File**: `src/biomechanics/diagnosis/engine.py`

Scans the set for observable symptoms — things that look wrong compared to what's expected for this specific person's body.

The engine iterates through `SYMPTOM_GRAPH` (from `symptoms.yaml`). Each symptom definition contains:

- **Feature name**: which kinematic measurement to check
- **Aggregation**: how to combine across reps (max/mean/last)
- **Expected value function**: computes the personalized baseline from anthropometry. Example: `expected_trunk_lean_geometric(anthro)` returns `30 + (femur_torso_ratio - 1) * 120`. A user with 1.1 ratio should lean ~42°.
- **Threshold**: tolerable deviation before it counts as a symptom
- **Severity scoring**: `relative_excess` or `zscore`

For each symptom, the engine:
1. Extracts the feature value from each rep
2. Aggregates across reps
3. Computes expected value from anthropometry
4. Computes severity from excess over expected + threshold
5. If severity > 0: records which reps contributed
6. Creates `DetectedSymptom` with ID, severity, and contributing reps

### Step 20: Cause Scoring (Bayesian Posterior)

**Files**: `src/biomechanics/diagnosis/engine.py`, `src/biomechanics/diagnosis/graph/evidence_tests.py`

For each detected symptom, identifies candidate root causes and scores them using Bayesian reasoning.

First, picks a **representative rep** — the one with median trunk pitch (not worst, not best).

For each candidate cause:
1. Looks up `prior` from the symptom definition (how likely this cause is in general)
2. Runs the **evidence test function** on the representative rep. Examples:
   - `test_narrow_stance()`: checks stance width vs. dorsiflexion-adjusted ideal AND symptom presence
   - `test_bracing_failure()`: checks excess lean while ruling out mechanical explanations
   - `test_limited_ankle_df()`: checks dorsiflexion utilization > 85% of capacity
3. Computes `posterior = prior * evidence_score`
4. Normalizes across candidates for each symptom

If a cause is implicated by multiple symptoms, posteriors aggregate via **noisy-OR**: `aggregate = 1 - product(1 - p_i)`. Multiple independent evidence pieces for the same cause compound.

Causes with aggregate score <= 0.25 are filtered out.

### Step 21: Hypothesis Building

**Files**: `src/biomechanics/diagnosis/engine.py`, `src/biomechanics/diagnosis/graph/parameter_deltas.py`

Packages each surviving cause into a structured hypothesis:

**Tier assignment**:
| Tier | Category | Examples |
|------|----------|----------|
| 1 | Immediate cues (fix now) | "Widen stance", "Push knees out", "Shift weight left" |
| 2 | Session-level (work on today) | "Focus on bracing before descending" |
| 3 | Long-term (weeks/months) | "Hip abductor strengthening", "Ankle mobility work" |
| 0 | Contextual notes | "Long femurs mean more forward lean is expected" |

**Parameter delta** (tier 1 only): The `parameter_delta_fn` computes exact corrections based on the user's dorsiflexion capacity and anthropometry. Output is a dictionary of joint-level deltas (stance width shift, toe-out angle, knee push-out, pelvis shift).

**Explanation**: Template filled with concrete numbers from the rep data.

Hypotheses are sorted by tier (descending) then by score (descending).

### Step 22: Perturbation Merging

Combines all tier-1 parameter deltas into a single correction vector. Scalar values are summed. Foot target deltas (6-element arrays for ankle position shifts) are element-wise summed. String values are kept as-is.

### Step 23: Rep Scoring

**File**: `src/biomechanics/diagnosis/rep_scoring.py`

Scores each rep on 5 dimensions (all [0, 1] where 1.0 = perfect):

| Dimension | Weight | Perfect score when | Decay |
|-----------|--------|-------------------|-------|
| **Depth** | 30% | Below parallel (class 4) + hips below knees | By depth class (0.1 → 1.0) |
| **Trunk control** | 25% | Deviation from expected lean <= 3° | Linear over 20° range |
| **Knee tracking** | 20% | Worst valgus deviation <= 4° | Linear over 12° range |
| **Symmetry** | 15% | Hip Y asymmetry <= 1 cm | Linear over 5 cm range |
| **Ankle utilization** | 10% | 50-85% of dorsiflexion capacity used | Decay below 50% or above 85% |

**Composite score**: Weighted sum of all 5 dimensions.

**Set summary**: Mean composite, best/worst rep, trend slope (linear regression over rep index). Negative slope = degrading quality (fatigue). Positive = improving.

### Step 24: Keypoint Correction

**File**: `src/biomechanics/diagnosis/keypoint_corrector.py`

Generates a corrected 3D skeleton showing what the squat should look like. Applied in sequence:

1. **Stance width + toe-out via delta-FK**: `bottom_up_build()` rebuilds the lower body from grounded feet. Anchors ankles, scales stance width, rotates shin/thigh by toe-out and dorsiflexion deltas. Hip positions fall out of leg geometry; rigid pelvis reconciled by averaging. Correction applied as a delta (build with identity params, build with corrected params, subtract, add to observed).

2. **Knee push-out**: Nudges knees laterally along hip axis by `thigh_length * sin(delta_angle)`.

3. **Weight centering**: Shifts pelvis + upper body laterally.

4. **Bone length enforcement**: 2-link IK (`solve_knee()`) re-solves knee positions using law of cosines to maintain original thigh/shin lengths.

5. **Dorsiflexion cap**: If shin angle exceeds calibrated max, iteratively raises hips (5 iterations, 0.3 damping) and re-solves knees.

6. **Regrounding**: Shifts lower body up if any ankle went below Y=0.

7. **Depth lowering**: For "depth unfamiliarity" diagnosis, drops hips to `hip_mid_y == knee_mid_y` (parallel), re-solves knees via IK.

8. **Bilateral symmetry enforcement**: Mirrors R leg bone vectors to L orientation, averages, FK-rebuilds both legs.

9. **Balance solve** (Newton-Raphson): Tilts trunk so whole-body COM projects onto mid-foot balance target. Uses biomechanics literature mass fractions (head=8.1%, trunk=49.7%, thigh=10% each, etc.). Balance target is 35% of foot length from heel. Converges in ~5 iterations.

**Morph frame generation**: `build_morph_frames()` produces 60 frames of Gaussian-tapered interpolation between observed and corrected skeletons for smooth animation.

### Step 25: Coaching Delivery

**File**: `src/biomechanics/coaching/ipc_bridge.py`

Sends diagnosis results to the conversational voice agent as structured JSON messages over IPC:

- **Exercise preparation**: Pre-caches audio cues for zero-latency playback.
- **Frame data**: Sent every Nth frame (default: 10) to keep voice agent aware without flooding.
- **Fault events**: Per-fault-type cooldown (default 3 seconds) prevents repetitive alerts.
- **Rep completion**: Triggers between-rep cues with depth category and fault summary.
- **Set completion**: Full diagnosis sent for post-set conversational summary.

---

## End-to-End Data Flow

```
Camera frame
  --> Barbell detection (YOLO11n) --> Kalman tracking
  --> Pose estimation (MediaPipe/RTMPose) --> Skeleton2D + Skeleton3D
  --> Standing gate --> Readiness gate
  --> Pre-IK filters (confidence --> velocity --> bones --> position --> bones)
  --> Analytical IK --> 22 joint angles
  --> One Euro filter + derivatives
  --> Rep signal (hip height for squats)
  --> Predictive state estimation
  --> Fault rules (depth, symmetry, bar tilt, forward lean, knee valgus)
  --> Baseline calibration (after 1st clean rep)
  --> Rep counter (4-state machine) --> RepData
  --> PipelineFrame output
  --> Set data collection
  --> Set finalization (plots, segmentation, HTML dashboard)
  --> Diagnosis bridge --> RepKinematicSummary + SetFeatures
  --> Symptom detection (personalized baselines from anthropometry)
  --> Bayesian cause scoring (prior x evidence, noisy-OR aggregation)
  --> Hypothesis building (tier 1/2/3 + parameter deltas)
  --> Rep scoring (5 dimensions, weighted composite)
  --> Keypoint correction (delta-FK + IK + COM balance)
  --> Morph frame generation
  --> IPC --> Voice agent cues
```

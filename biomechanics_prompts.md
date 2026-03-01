# Biomechanics Pipeline — Claude Code Prompts

## How to Use This Document

Feed these prompts to Claude Code **sequentially**. Each prompt builds on the previous one. Wait for each prompt to complete and verify it works before moving to the next.

**Before starting:** Place the `biomechanics_implementation.md` file in your project root so Claude Code can reference it as context. Also place the original `squat_rack_implementation.md` in the project root for architectural context.

**Convention:** Each prompt is in a fenced block. Copy the entire block as your Claude Code input.

---

## PROMPT 0 — Project Bootstrap

```
Read the files `biomechanics_implementation.md` and `squat_rack_implementation.md` in the project root. These are the implementation spec and architectural design for a real-time biomechanics coaching pipeline.

Create the project foundation in a `biomechanics/` directory (unless it already exists):

1. Create the full directory structure as specified in Section 1 of the implementation doc. Create all __init__.py files, all directories, and placeholder .gitkeep files in empty directories.

2. Create `pyproject.toml` with all dependencies from Section 2.2. Use the exact dependency versions specified. Set up the project as an installable package with the CLI entry point `biomechanics = "biomechanics.main:app"`.

3. Create `config/default.yaml` with the full default configuration from Section 5.

4. Create `biomechanics/config.py` — a Pydantic Settings class that loads from YAML config and environment variables. It should:
   - Load config/default.yaml by default
   - Allow override via BIOMECHANICS_CONFIG env var pointing to a different YAML
   - Allow individual env var overrides (e.g. BIOMECHANICS_POSE_BACKEND=rtmpose)
   - Validate all config values
   - Expose typed sub-configs: CaptureConfig, PoseConfig, TriangulationConfig, KinematicsConfig, FaultConfig, CoachingConfig, VizConfig

5. Create `biomechanics/utils/types.py` with ALL the shared data types from Section 3 of the implementation doc. Include every Pydantic model: Keypoint2D, Skeleton2D, MultiViewPose, Point3D, Skeleton3D, JointAngles, FaultSeverity, FaultEvent, RepData, SessionState, PipelineFrame. Include the to_numpy() methods and all helper methods shown.

6. Create `biomechanics/utils/timing.py` with:
   - A `@timed` decorator that records execution time of any function
   - A `LayerTimer` context manager that accumulates timing per layer name
   - A `PipelineProfiler` class that tracks per-layer latency over time and can report mean/p50/p95/p99 stats

7. Create `biomechanics/utils/logging.py` with structlog setup: JSON output in production, pretty console output in dev mode. Include a `get_logger(name)` function.

8. Create `biomechanics/utils/geometry.py` with common geometric utilities:
   - `angle_between_vectors(v1, v2) -> float` — angle in degrees
   - `project_to_plane(point, plane_normal, plane_point) -> np.ndarray`
   - `rotation_matrix_from_vectors(v1, v2) -> np.ndarray`
   - `midpoint(p1, p2) -> np.ndarray`

9. Create a basic `biomechanics/main.py` using Typer with stub commands: run, benchmark, calibrate, onboard, report. Each command should just print a message for now.

10. Create `tests/conftest.py` with shared pytest fixtures that load test data from `tests/fixtures/`.

11. Create `tests/fixtures/sample_keypoints.json` — a realistic set of COCO 17 keypoints for a person in a half-squat position (1280x720 frame). Make the coordinates anatomically plausible.

12. Create `tests/fixtures/sample_3d_points.json` — the same pose in 3D world coordinates (meters). Person standing ~2m from origin, realistic human proportions.

13. Create `tests/fixtures/sample_angles.json` — expected joint angles for the half-squat pose. Approximately: hip flexion ~70°, knee flexion ~80°, ankle dorsiflexion ~25°, trunk flexion ~30°.

After creating everything, install the project in dev mode (`pip install -e ".[dev]"`) and verify:
- `python -c "from biomechanics.utils.types import JointAngles; print('types OK')"` works
- `python -c "from biomechanics.config import PipelineConfig; print('config OK')"` works
- `pytest tests/conftest.py` runs without errors
```

---

## PROMPT 1 — Capture Layer

```
Build the camera capture layer in `biomechanics/capture/`. Reference the implementation spec in biomechanics_implementation.md Section 4.1.

1. Create `biomechanics/capture/base.py` with the abstract `CaptureSource` class:
   - `read() -> tuple[bool, np.ndarray]` — returns (success, BGR frame)
   - `get_camera_matrix() -> np.ndarray` — 3x3 intrinsic matrix
   - `get_distortion_coeffs() -> np.ndarray`
   - `fps` property, `resolution` property
   - `release()` method for cleanup
   - Context manager support (__enter__/__exit__)

2. Create `biomechanics/capture/webcam.py`:
   - Wraps cv2.VideoCapture(device_id)
   - Uses reasonable default intrinsics for a MacBook M2 webcam (focal length ~1000px for 720p, principal point at image center)
   - Configurable resolution and FPS
   - Handles camera open failures gracefully with clear error messages

3. Create `biomechanics/capture/video_file.py`:
   - Wraps cv2.VideoCapture(filepath)
   - Supports frame-by-frame stepping (for offline analysis)
   - `loop` parameter to repeat the video indefinitely
   - `seek(frame_number)` method
   - Reports actual video FPS and resolution
   - Inherits intrinsics from a config or uses defaults

4. Write tests in `tests/test_capture/`:
   - `test_video_file.py`: Create a small synthetic video (10 frames, solid colors) using OpenCV, test that VideoFileCapture reads all frames correctly, test looping, test seek
   - `test_webcam.py`: Test that WebcamCapture initializes (mark as skip if no camera available with `@pytest.mark.skipif`)

Verify: Run `pytest tests/test_capture/ -v` and all tests pass.
```

---

## PROMPT 2 — Pose Estimation (MediaPipe)

```
Build the pose estimation layer in `biomechanics/pose/`. Start with MediaPipe as the primary backend since it requires zero model downloads. Reference implementation spec Section 4.2.

1. Create `biomechanics/pose/base.py` with abstract `PoseEstimator`:
   - `estimate(frame: np.ndarray, camera_id: int = 0) -> Skeleton2D`
   - `estimate_batch(frames: list[np.ndarray]) -> list[Skeleton2D]` (default: sequential)
   - Class-level `KEYPOINT_NAMES: list[str]` for the COCO 17 keypoint names

2. Create `biomechanics/pose/mediapipe_fallback.py`:
   - Uses mediapipe.solutions.pose with model_complexity=1 for a good speed/accuracy tradeoff
   - Maps MediaPipe's 33 BlazePose landmarks to COCO 17 format. The mapping is:
     * nose → nose (0)
     * left_eye → left_eye_inner or left_eye (2)
     * right_eye → right_eye_inner or right_eye (5)
     * left_ear → left_ear (7)
     * right_ear → right_ear (8)
     * left_shoulder → left_shoulder (11)
     * right_shoulder → right_shoulder (12)
     * left_elbow → left_elbow (13)
     * right_elbow → right_elbow (14)
     * left_wrist → left_wrist (15)
     * right_wrist → right_wrist (16)
     * left_hip → left_hip (23)
     * right_hip → right_hip (24)
     * left_knee → left_knee (25)
     * right_knee → right_knee (26)
     * left_ankle → left_ankle (27)
     * right_ankle → right_ankle (28)
   - Converts MediaPipe normalized coordinates (0-1) to pixel coordinates
   - Uses MediaPipe's visibility score as the confidence value
   - Filters out keypoints below the configured confidence threshold (default 0.3)

3. Create `biomechanics/viz/overlay_2d.py`:
   - Function `draw_skeleton(frame: np.ndarray, skeleton: Skeleton2D, ...) -> np.ndarray`
   - Draws keypoints as colored circles (green if confidence > 0.5, yellow if 0.3-0.5)
   - Draws limb connections as lines between appropriate keypoints
   - COCO skeleton connections: (5,6), (5,7), (7,9), (6,8), (8,10), (5,11), (6,12), (11,12), (11,13), (13,15), (12,14), (14,16)
   - Shows confidence values next to keypoints if a flag is set
   - Shows FPS counter in top-left corner

4. Create a quick visual test script `scripts/test_pose_live.py`:
   - Opens webcam
   - Runs MediaPipe pose estimation on each frame
   - Draws skeleton overlay
   - Shows frame with cv2.imshow
   - Prints FPS to console
   - Press 'q' to quit
   This isn't a pytest test — it's a manual visual verification tool.

5. Write unit tests in `tests/test_pose/test_mediapipe.py`:
   - Test that MediaPipePoseEstimator returns a valid Skeleton2D
   - Test that output has exactly 17 keypoints in COCO order
   - Test that keypoint names match expected COCO names
   - Test with a synthetic image (e.g., blank frame — should return low-confidence keypoints)
   - Test confidence threshold filtering

Verify: Run `python scripts/test_pose_live.py` — you should see your webcam feed with a skeleton overlay. Also run `pytest tests/test_pose/ -v`.
```

---

## PROMPT 3 — Analytical Inverse Kinematics

```
Build the analytical IK solver in `biomechanics/kinematics/`. This is the lightweight geometric solver that computes joint angles directly from 3D landmark positions. Reference implementation spec Section 4.4.

Since we're working with a single webcam for now (no real 3D triangulation), we need a way to get approximate 3D coordinates from 2D pose. MediaPipe actually provides 3D world landmarks — use those.

1. Update `biomechanics/pose/mediapipe_fallback.py`:
   - Add a method `estimate_3d(frame: np.ndarray) -> Skeleton3D` that uses MediaPipe's `pose_world_landmarks` (the 3D output in meters, centered at hip midpoint)
   - Map the 3D landmarks to COCO 17 format just like the 2D ones
   - Return as Skeleton3D using the Point3D type

2. Create `biomechanics/kinematics/base.py` with abstract `IKSolver`:
   - `solve(skeleton: Skeleton3D) -> JointAngles`
   - `get_available_angles() -> list[str]` — which angles this solver computes

3. Create `biomechanics/kinematics/joint_angles.py` with helper functions:
   - `compute_flexion_angle(proximal: np.ndarray, joint: np.ndarray, distal: np.ndarray) -> float`
     Computes the angle at the `joint` point formed by the proximal-joint-distal chain. Returns degrees.
   - `compute_abduction_angle(joint: np.ndarray, distal: np.ndarray, reference_plane_normal: np.ndarray) -> float`
     Projects the joint-distal vector onto a reference plane and computes the angle from the plane.
   - `compute_trunk_angle(shoulder_mid: np.ndarray, hip_mid: np.ndarray, vertical: np.ndarray) -> float`
     Angle of the trunk vector from vertical.
   - `compute_lateral_bend(left_shoulder: np.ndarray, right_shoulder: np.ndarray, left_hip: np.ndarray, right_hip: np.ndarray) -> float`
     Lateral deviation of trunk from vertical in the frontal plane.

4. Create `biomechanics/kinematics/analytical_ik.py`:
   - `AnalyticalIKSolver` class implementing IKSolver
   - Uses the geometry helpers from joint_angles.py and utils/geometry.py
   - Computes ALL angles in JointAngles:
     * hip_flexion_r/l: angle at hip between trunk and thigh vectors
     * hip_adduction_r/l: medial/lateral angle of thigh from sagittal plane
     * knee_flexion_r/l: angle at knee between thigh and shank
     * ankle_dorsiflexion_r/l: angle at ankle between shank and foot (if foot keypoints available, otherwise estimate)
     * trunk_flexion: angle of trunk from vertical (sagittal plane)
     * trunk_lateral_bend: lateral deviation (frontal plane)
     * pelvis_tilt: angle of pelvis from horizontal

   - Landmark-to-body-segment mapping:
     * trunk: midpoint(left_shoulder, right_shoulder) → midpoint(left_hip, right_hip)
     * right thigh: right_hip → right_knee
     * left thigh: left_hip → left_knee
     * right shank: right_knee → right_ankle
     * left shank: left_knee → left_ankle
     * pelvis: left_hip → right_hip

   - Handle missing landmarks gracefully — if a required landmark has low confidence, return 0.0 for that angle and log a warning

5. Write thorough tests in `tests/test_kinematics/test_analytical_ik.py`:
   - Test with the sample_3d_points.json fixture (half-squat) — angles should approximately match sample_angles.json
   - Test standing pose (all flexion angles near 0°)
   - Test deep squat (hip and knee flexion > 90°)
   - Test bilateral symmetry — symmetric pose should give symmetric angles
   - Test edge cases: missing landmarks, zero-length segments
   - Test that angle ranges are physically plausible (no angles > 180° or < -180°)

6. Create a visual test script `scripts/test_ik_live.py`:
   - Opens webcam
   - Runs MediaPipe 3D pose
   - Runs AnalyticalIKSolver
   - Overlays joint angles as text on the video frame (show hip, knee, ankle flexion for both sides)
   - Also show trunk flexion
   - Press 'q' to quit

Verify: Run `scripts/test_ik_live.py` — do some squats in front of your webcam and verify the angles change plausibly (hip/knee flexion should increase as you squat down). Run `pytest tests/test_kinematics/ -v`.
```

---

## PROMPT 4 — Fault Detection & Rep Counting

```
Build the fault detection system in `biomechanics/faults/`. Reference implementation spec Sections 4.5 and the fault detection table.

1. Create `biomechanics/faults/fault_types.py`:
   - FaultType enum (DEPTH, BILATERAL_ASYMMETRY, HEEL_RISE, FORWARD_LEAN, KNEE_VALGUS, BACK_ROUNDING)
   - DEFAULT_THRESHOLDS dict from the implementation spec
   - FaultRule abstract base class with: `evaluate(angles: JointAngles, history: deque[JointAngles]) -> Optional[FaultEvent]`

2. Create `biomechanics/faults/rep_counter.py`:
   - RepCounter class with the state machine described in the spec:
     * States: IDLE, IN_REP
     * Transition to IN_REP when hip flexion (max of L/R) exceeds entry_threshold (30°)
     * Transition to IDLE when hip flexion drops below entry_threshold
     * Minimum rep duration filter (20 frames) to reject noise
   - On rep completion, return RepData with:
     * rep_number (incrementing)
     * start/end frame and time
     * max_depth_angle (peak hip flexion during rep)
     * All accumulated faults during that rep
     * The full joint angle series for the rep
   - `update(angles: JointAngles, faults: list[FaultEvent]) -> Optional[RepData]`
     Returns RepData when a rep completes, None otherwise

3. Create `biomechanics/faults/rules/depth.py` — DepthRule:
   - Only fires when a rep is completing (needs rep context) OR continuously monitors depth
   - For real-time: report current depth category continuously
   - For rep summary: report if rep didn't reach parallel
   - Categories: quarter (<60°), half (60-90°), parallel (90-100°), below parallel (>100°)

4. Create `biomechanics/faults/rules/symmetry.py` — SymmetryRule:
   - Compare left vs right hip flexion and left vs right knee flexion
   - Severity based on difference: mild (5-10°), moderate (10-15°), severe (>15°)
   - Should consider which side is higher — include in the message (e.g., "right knee 8° more flexed than left")

5. Create `biomechanics/faults/rules/heel_rise.py` — HeelRiseRule:
   - Track ankle vertical position relative to its position at rep start
   - If ankle rises more than threshold (2cm = 0.02m in 3D coords) during the descent phase, flag heel rise
   - Needs history to compare current vs start-of-rep position

6. Create `biomechanics/faults/rules/forward_lean.py` — ForwardLeanRule:
   - Use trunk_flexion angle directly
   - Thresholds: mild (35°), moderate (45°), severe (55°)
   - Only fire during active rep (hip flexion > 30°) — some lean is normal

7. Create `biomechanics/faults/rules/knee_valgus.py` — KneeValgusRule:
   - v1: rule-based using hip_adduction angle
   - If knee tracks medially (hip adduction increases beyond threshold during descent), flag valgus
   - Thresholds from config
   - Include a comment/docstring about the v2 TCN upgrade path

8. Create `biomechanics/faults/rule_engine.py`:
   - RuleEngine class that orchestrates all rules
   - Maintains the history deque (maxlen=90 frames)
   - Runs all rules on each frame and collects results
   - Deduplicates: if the same fault type fires on consecutive frames, only report it once until it clears

9. Write comprehensive tests in `tests/test_faults/`:
   - `test_rep_counter.py`:
     * Feed a synthetic angle sequence that simulates 3 reps (rise to 80°, back to 0°, repeat)
     * Verify rep counter detects exactly 3 reps
     * Verify min duration filter rejects short spikes
     * Verify max_depth_angle is correct per rep
   - `test_depth.py`: Test all depth categories with known angles
   - `test_symmetry.py`: Test symmetric and asymmetric angle pairs
   - `test_rule_engine.py`: Feed a sequence with multiple fault types, verify all are detected
   - Use synthetic JointAngles sequences — don't depend on camera or pose estimation

Verify: `pytest tests/test_faults/ -v` — all tests should pass.
```

---

## PROMPT 5 — Pipeline Integration & Live Demo

```
Connect all layers into the pipeline orchestrator and create the live demo. Reference implementation spec Section 4.7.

1. Create `biomechanics/pipeline.py`:
   - BiomechanicsPipeline class that wires together all layers
   - Constructor takes PipelineConfig, initializes each layer based on config
   - `process_frame() -> PipelineFrame` method that runs the full pipeline:
     * Capture frame
     * Pose estimation (2D + 3D via MediaPipe)
     * IK solve (analytical)
     * Fault detection
     * Rep counting
     * Return PipelineFrame with all results and per-layer timing
   - `run()` method — main loop that calls process_frame() in a loop, updates visualization
   - `stop()` method — graceful shutdown
   - The pipeline should handle errors gracefully in any layer — if pose fails, skip downstream. Log errors, don't crash.

2. Create `biomechanics/viz/dashboard.py`:
   - A real-time OpenCV-based dashboard that shows:
     * Main camera view with skeleton overlay (left side, ~70% of window)
     * Joint angle readout panel (right side): current hip, knee, ankle, trunk angles for both sides
     * Rep counter display: "Rep 3 | Depth: Parallel | Faults: none"
     * Active faults highlighted in red text
     * Per-layer latency bar at the bottom (thin colored bars showing ms per layer)
     * FPS counter
   - All rendering via OpenCV drawing functions (putText, rectangle, line)
   - Takes a PipelineFrame and renders the full dashboard into a single window

3. Update `biomechanics/main.py`:
   - Implement the `run` command fully:
     * Load config from YAML
     * Initialize BiomechanicsPipeline
     * Call pipeline.run()
     * Handle Ctrl+C gracefully
   - Implement the `benchmark` command:
     * Run pipeline for N frames (default 300)
     * Report per-layer latency stats (mean, p50, p95, p99)
     * Report total pipeline FPS
   - Add `--source`, `--video-path`, `--config`, `--no-viz` CLI flags

4. Create `scripts/run_on_video.py`:
   - Analyze a video file offline
   - Run full pipeline on every frame
   - Print rep-by-rep summary at the end
   - Optionally save annotated video with skeleton overlay

5. Write integration test `tests/test_pipeline/test_end_to_end.py`:
   - Create a synthetic test video (20 frames) using OpenCV — draw a simple stick figure that simulates a squat motion
   - Run pipeline on this video
   - Verify we get PipelineFrames with populated joint_angles and timing data
   - Don't test for specific angle values (synthetic stick figure won't match real anatomy) — just test that the pipeline runs without errors and produces valid output types

Verify:
- `biomechanics run` opens webcam with full dashboard overlay
- Do some squats — verify rep counter increments, angles change, faults appear when appropriate
- `biomechanics run --source video --video-path <some_squat_video.mp4>` works on a video
- `biomechanics benchmark --frames 100` reports latency stats
- `pytest tests/test_pipeline/ -v` passes
```

---

## PROMPT 6 — Audio Coaching & Session Management

```
Build the coaching output layer in `biomechanics/coaching/`. Reference implementation spec Section 4.6.

1. Create `biomechanics/coaching/audio_cues.py`:
   - AudioCueEngine class using pyttsx3 for text-to-speech
   - CUE_MAP dictionary mapping fault types to short spoken cues:
     * knee_valgus → "knees out"
     * forward_lean → "chest up"
     * depth → "deeper"
     * heel_rise → "heels down"
     * bilateral_asymmetry → "even it out"
   - Rate limiting: minimum 2-second gap between any cues
   - Priority system: severity_score determines which cue fires if multiple faults active
   - The TTS should run in a background thread so it doesn't block the pipeline
   - `queue_cue(fault: FaultEvent)` — non-blocking, adds to queue
   - `_speaker_thread()` — background thread that processes the queue
   - Include an `enabled` flag to easily disable audio in testing
   - On macOS, pyttsx3 uses NSSpeechSynthesizer — test this works on your M2

2. Create `biomechanics/coaching/session.py`:
   - SessionManager class that tracks the full training session:
     * Accumulates RepData as reps complete
     * Tracks set boundaries (pause > 30 seconds between reps = new set)
     * Maintains per-set and per-session statistics:
       - Average depth per set
       - Most common fault per set
       - Depth consistency (std dev of max hip flexion across reps)
       - Symmetry trend (is asymmetry getting worse over sets?)
     * `add_rep(rep: RepData)` — called when rep counter emits a rep
     * `get_set_summary() -> dict` — summary of current set
     * `get_session_summary() -> dict` — full session summary
     * `export_session() -> dict` — all data for LLM analysis or report

3. Create `biomechanics/coaching/llm_coach.py`:
   - LLMCoach class using the Anthropic Python SDK
   - System prompt from the implementation spec — the LLM is a COMMUNICATION layer only
   - `analyze_set(reps: list[RepData]) -> str` — generates coaching feedback for a set
   - `generate_session_report(session: dict) -> str` — comprehensive post-session report
   - The structured data sent to the LLM should include:
     * Number of reps, average depth, depth per rep
     * Faults detected with severity and frequency
     * Symmetry metrics
     * Comparison to previous session if available
   - Include good error handling — if API key is missing or call fails, return a fallback message
   - Make this async-compatible (but can be called synchronously for now)

4. Create `biomechanics/coaching/report.py`:
   - SessionReport class that generates a structured report
   - `generate_text_report(session_data: dict, llm_analysis: str | None) -> str`
     * Plaintext report with sections: Overview, Rep Analysis, Faults, Recommendations
     * If LLM analysis is available, include it in Recommendations
     * If not, provide rule-based recommendations from fault patterns
   - `generate_json_report(session_data: dict) -> dict`
     * Machine-readable format for dashboard consumption

5. Integrate coaching into the pipeline:
   - Update BiomechanicsPipeline to include AudioCueEngine and SessionManager
   - Audio cues fire in real-time during sets
   - When a set ends (detected by SessionManager), optionally run LLM analysis
   - Update the dashboard to show set summaries between sets

6. Update the `report` CLI command:
   - `biomechanics report --session-file <path>` — load a saved session JSON and generate a report
   - Print the report to console

7. Write tests in `tests/test_coaching/`:
   - Test AudioCueEngine rate limiting with synthetic fault events
   - Test SessionManager set detection and statistics
   - Test report generation with known session data
   - Mock the Anthropic API for LLM coach tests

Verify:
- `biomechanics run` now speaks audio cues when you squat with bad form
- After a set (pause for 30+ seconds), a set summary appears in the console
- `biomechanics run --no-audio` works without audio
```

---

## PROMPT 7 — Triangulation & Multi-Camera Simulation

```
Build the 3D triangulation layer in `biomechanics/triangulation/`. This enables proper multi-camera 3D reconstruction. For testing, we simulate 4 cameras from a single webcam. Reference implementation spec Section 4.3.

1. Create `biomechanics/triangulation/calibration.py`:
   - CameraParams dataclass: intrinsic (3x3), rotation (3x3), translation (3x1), distortion (5x1)
   - `generate_simulated_cameras(num_cameras: int = 4) -> list[CameraParams]`
     * Creates 4 virtual cameras in a ring around a capture volume centered at origin
     * Positions at the azimuth angles from the implementation spec (±45°, ±135°)
     * All cameras at 15° elevation, 2.5m distance from center
     * Reasonable intrinsic params (focal length ~800px for 720p)
   - `calibrate_from_checkerboard(images: list[np.ndarray], pattern_size: tuple) -> CameraParams`
     * Standard OpenCV checkerboard calibration for real cameras
   - `save_calibration(params: list[CameraParams], path: str)`
   - `load_calibration(path: str) -> list[CameraParams]`

2. Create `biomechanics/triangulation/stereo.py`:
   - StereoTriangulator class:
     * Takes list[CameraParams] in constructor
     * Precomputes projection matrices: P = K @ [R|t]
     * `triangulate(multi_view: MultiViewPose) -> Skeleton3D`
       - For each keypoint, collect observations from all camera views
       - Use cv2.triangulatePoints() with DLT when 2+ views available
       - Compute reprojection error for quality assessment
       - Filter out points with reprojection error above threshold
     * `triangulate_pair(kp1: Keypoint2D, kp2: Keypoint2D, cam1_idx: int, cam2_idx: int) -> Point3D`
       - Triangulate a single point from two views
     * Include robust handling:
       - What if only 1 camera sees a keypoint? Use depth prior from previous frame
       - What if all cameras have low confidence? Mark point as uncertain

3. Create `biomechanics/triangulation/sim_cameras.py`:
   - SimulatedMultiCam class for testing triangulation from a single webcam:
     * Takes a real 2D skeleton (from the webcam) and the real camera params
     * Uses MediaPipe's 3D world landmarks as a "pseudo ground truth"
     * Projects these 3D points through each of the 4 simulated cameras to get 4 sets of 2D keypoints
     * Adds realistic Gaussian noise to the 2D projections (σ = 2-5 pixels)
     * Returns MultiViewPose with all 4 views
   - This creates a closed-loop test: we know the 3D points, we generate 2D observations, then triangulation should recover the 3D points within the noise margin

4. Update `biomechanics/capture/multi_cam.py`:
   - MultiCameraManager class that manages multiple CaptureSource instances
   - For testing: wraps a single webcam + SimulatedMultiCam to produce multi-view data
   - `read_synchronized() -> list[tuple[bool, np.ndarray]]` — returns frames from all cameras

5. Write tests in `tests/test_triangulation/`:
   - `test_stereo.py`:
     * Create known 3D points
     * Project them to 2D through known camera matrices
     * Triangulate back to 3D
     * Verify RMSE < 1cm (for noiseless case)
     * Add noise, verify RMSE < 5cm
   - `test_sim_cameras.py`:
     * Generate simulated multi-view data from known 3D points
     * Verify projections are geometrically consistent
   - `test_calibration.py`:
     * Test that simulated camera params produce valid projection matrices

6. Create `scripts/test_triangulation_live.py`:
   - Opens webcam
   - Runs MediaPipe 3D to get "ground truth" 3D points
   - Generates simulated 4-camera 2D observations
   - Triangulates back to 3D
   - Compares triangulated 3D to MediaPipe 3D
   - Prints per-joint RMSE in real-time
   - This validates the triangulation pipeline end-to-end

Verify:
- `pytest tests/test_triangulation/ -v` passes
- `python scripts/test_triangulation_live.py` shows low RMSE
- The pipeline can now optionally use multi-camera triangulation (config: triangulation.enabled = true)
```

---

## PROMPT 8 — Web Dashboard

```
Build a real-time web dashboard using FastAPI + WebSocket. This replaces the OpenCV-only dashboard with a richer browser-based UI. Reference implementation spec Section 4.7 visualization.

1. Create `biomechanics/viz/web_ui.py`:
   - FastAPI application with:
     * GET / — serves the main dashboard HTML page
     * WebSocket /ws — streams real-time pipeline data to the browser
     * GET /api/session — returns current session state as JSON
     * GET /api/session/history — returns historical session data
   - The WebSocket should send PipelineFrame data (serialized as JSON) at the pipeline's frame rate
   - Include CORS middleware for local development
   - Run with uvicorn on a configurable port (default 8420)

2. Create `biomechanics/viz/templates/dashboard.html` (or inline in web_ui.py):
   - A single-page HTML/JS application (no framework needed — vanilla JS or use a CDN for a lightweight lib)
   - Layout:
     * Left panel (60%): Live camera feed with skeleton overlay (rendered on canvas via WebSocket frame data — send keypoint coordinates, not video frames)
     * Right panel (40%):
       - Current joint angles as a real-time updating table
       - Rep counter: large number display
       - Active faults: cards with severity color coding (green/yellow/orange/red)
       - Per-layer latency sparkline or bar chart
       - Set history: list of completed sets with summaries
   - The skeleton should be drawn on an HTML canvas using the 2D keypoint coordinates
   - Use CSS for styling — dark theme, clean and readable
   - Auto-reconnect WebSocket on disconnect

3. Update BiomechanicsPipeline:
   - When `config.visualization.dashboard = true`, start the FastAPI server in a background thread
   - Pipeline pushes each PipelineFrame to the WebSocket broadcaster
   - The OpenCV window still works alongside (or can be disabled)

4. Update `main.py`:
   - `biomechanics run --dashboard` starts the web dashboard
   - Print the dashboard URL to console: "Dashboard available at http://localhost:8420"

5. Add a simple REST endpoint for session reports:
   - POST /api/session/analyze — triggers LLM analysis of current session (if API key configured)
   - Returns coaching feedback as JSON

Verify:
- `biomechanics run --dashboard` starts the system
- Open http://localhost:8420 in browser — see live skeleton, angles, rep counter
- Do some squats — dashboard updates in real-time
- Faults appear with appropriate color coding
```

---

## PROMPT 9 — RTMPose ONNX Integration

```
Add RTMPose as the production-quality pose estimator. Reference implementation spec Section 4.2.

1. Create `scripts/download_models.py`:
   - Downloads the RTMPose-m ONNX model for COCO 17-keypoint detection
   - Source: the official MMPose model zoo — the ONNX export of rtmpose-m_simcc-body7_pt-body7_420e-256x192
   - Download URL: check https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose for the latest ONNX export link. If direct ONNX isn't available, download the PyTorch checkpoint and export to ONNX.
   - Save to biomechanics/pose/models/rtmpose_m.onnx
   - Also download a simple person detection model (YOLOX-nano or similar lightweight detector) for bounding box cropping — RTMPose is a top-down model that needs a person crop
   - Print download progress and verify file integrity

2. Create `biomechanics/pose/rtmpose.py`:
   - RTMPoseEstimator class implementing PoseEstimator
   - ONNX Runtime inference with CoreMLExecutionProvider for M2 acceleration
   - Full preprocessing pipeline:
     * Person detection (YOLOX or use full-frame center crop for v1)
     * Crop and resize to 256x192
     * Normalize with ImageNet mean/std
   - SimCC decoding:
     * RTMPose uses SimCC (Simple Coordinate Classification) head
     * Output is two 1D heatmaps (x and y) per keypoint
     * Decode by finding argmax of each, then convert to coordinates
   - Postprocessing:
     * Map coordinates back to original image space
     * Apply confidence thresholding
   - Include proper error handling for model loading failures

3. Update config.py and default.yaml:
   - `pose.backend` can now be "rtmpose" or "mediapipe"
   - Add `pose.detector` config for person detection model

4. Write tests in `tests/test_pose/test_rtmpose.py`:
   - Test model loading (skip if model not downloaded)
   - Test inference on a test image
   - Test output format matches COCO 17 keypoint spec
   - Compare RTMPose vs MediaPipe on the same frame (they should roughly agree)

5. Add a benchmark comparison:
   - Update scripts/benchmark.py to compare RTMPose vs MediaPipe latency and keypoint agreement

Verify:
- `python scripts/download_models.py` downloads the model
- `biomechanics run --pose-backend rtmpose` works with RTMPose
- Benchmark shows RTMPose latency on M2
```

---

## PROMPT 10 — TCN Fault Detection (Scaffold + Synthetic Training)

```
Build the Temporal Convolutional Network infrastructure for dynamic fault detection (v2). This prompt scaffolds the architecture and creates the synthetic data generation pipeline. Reference implementation spec Sections 4.5.1 and 4.1.

1. Implement `biomechanics/faults/tcn_model.py` fully:
   - TemporalConvNet class (PyTorch nn.Module):
     * Input shape: (batch, num_angles, seq_length) — e.g., (32, 11, 90)
     * 3 temporal conv blocks, each with:
       - 1D causal convolution (kernel_size=7, padding to maintain length)
       - BatchNorm1d
       - ReLU
       - Dropout(0.2)
       - Residual connection (1x1 conv if channel mismatch)
     * Global average pooling over time dimension
     * Linear head → num_fault_types outputs (sigmoid activation for multi-label)
     * Output: severity scores (0-3) for each fault type
   - TCNPredictor class (inference wrapper):
     * Loads trained model weights
     * Maintains a rolling buffer of the last 90 frames of joint angles
     * `predict(angles: JointAngles) -> list[FaultEvent]`
     * Converts severity scores to FaultEvent objects
     * Falls back gracefully if no trained weights available (returns empty list)

2. Create `scripts/generate_synthetic.py`:
   - Generates synthetic training data for the TCN using parameterized squat simulations
   - SyntheticSquatGenerator class:
     * Parameters: body height, squat depth, descent speed, stance width
     * Fault parameters: valgus_degrees, trunk_flexion_offset, asymmetry_degrees
     * Generates a time series of JointAngles representing one rep
     * Uses simple kinematic equations (not OpenSim — that's for v2)
     * Adds realistic noise (Gaussian, σ=1-2°)
   - Generate balanced datasets:
     * 1000 clean reps (no faults)
     * 1000 mild valgus reps (5-10° knee adduction)
     * 1000 moderate valgus reps (10-15°)
     * 1000 severe valgus reps (>15°)
     * 1000 forward lean reps
     * 1000 mixed fault reps
   - Save as a PyTorch dataset:
     * Features: (num_samples, num_angles, seq_length)
     * Labels: (num_samples, num_fault_types) severity scores
     * Save to data/synthetic/train.pt and data/synthetic/val.pt (80/20 split)

3. Create `scripts/train_tcn.py`:
   - Training script for the TCN:
     * Load synthetic dataset
     * Train with AdamW, lr=1e-3, weight_decay=1e-4
     * MSE loss on severity scores
     * Train for 50 epochs, save best model by validation loss
     * Log training metrics with rich progress bars
     * Save model to biomechanics/faults/models/tcn_valgus_v1.pt
   - Use MPS backend on M2 for GPU acceleration

4. Update RuleEngine to optionally use TCN:
   - If TCN model weights are available and config enables it, run TCN alongside rule-based detection
   - TCN predictions override rule-based for the fault types it covers (valgus, back rounding)
   - Rule-based detectors remain as fallback

5. Write tests:
   - Test TCN model forward pass with random input
   - Test synthetic data generator produces valid angle ranges
   - Test TCN training loop runs for 2 epochs without errors (on tiny dataset)

Verify:
- `python scripts/generate_synthetic.py` creates training data
- `python scripts/train_tcn.py` trains to convergence (loss should decrease clearly on synthetic data)
- The trained model loads and produces predictions in the pipeline
```

---

## PROMPT 11 — Polish, Error Handling & Documentation

```
Final polish pass. Make everything production-ready for demo and continued development.

1. Error handling audit:
   - Go through every layer and ensure all exceptions are caught and handled gracefully
   - No unhandled exceptions should crash the pipeline — log and continue
   - Specific checks:
     * Camera not available → clear error message with troubleshooting
     * Model file not found → clear message with download instructions
     * OpenSim not installed → fall back to analytical IK automatically
     * API key missing for LLM → disable LLM features, log warning
     * WebSocket client disconnects → handle cleanly, allow reconnect

2. Create `biomechanics/CLAUDE.md`:
   - Project-level instructions for Claude Code when working on this project
   - Include: project structure overview, how to run, testing commands, architecture summary, common tasks

3. Create `README.md` at the biomechanics/ root:
   - Project description
   - Quick start guide (install, configure, run)
   - Architecture overview with the 5-layer diagram
   - Configuration reference
   - Development setup
   - Testing instructions
   - Troubleshooting common issues

4. Create `.env.example`:
   - ANTHROPIC_API_KEY=your-key-here
   - BIOMECHANICS_CONFIG=config/default.yaml
   - BIOMECHANICS_LOG_LEVEL=INFO

5. Add comprehensive docstrings to all public classes and methods. Every module should have a module-level docstring explaining its role in the architecture.

6. Run ruff check and fix any linting issues across the entire codebase.

7. Run mypy and fix any type errors. The codebase should be fully type-annotated.

8. Verify the full test suite passes: `pytest tests/ -v --tb=short`

9. Run the benchmark and include sample output in the README:
   `biomechanics benchmark --frames 300`

10. Create a short demo script `scripts/demo.py` that:
    - Checks all dependencies are installed
    - Downloads models if needed
    - Runs the pipeline on webcam for 30 seconds
    - Generates a session report
    - Prints the report to console
    - This is the "one command to see everything working" script
```

---

## Tips for Using These Prompts

**If a prompt fails or produces errors:**
- Tell Claude Code: "The previous step produced errors. Here's the error output: [paste]. Fix these issues before moving on."

**If you want to skip a prompt:**
- Prompts 0–5 are the core path. These get you a working live demo.
- Prompts 6–8 add coaching and visualization polish.
- Prompts 9–10 add production pose estimation and ML training.
- Prompt 11 is final polish.

**If you want to test incrementally:**
- After each prompt, run `pytest` and try the live scripts
- The system should be functional (with increasing capability) after every prompt

**Adjusting for your setup:**
- If you don't have a webcam, focus on video file testing. Download a squat video from YouTube and use: `biomechanics run --source video --video-path squat.mp4`
- If pyttsx3 doesn't work on your M2, disable audio: `biomechanics run --no-audio`
- If OpenCV display doesn't work (SSH, etc.), use the web dashboard: `biomechanics run --dashboard --no-viz`

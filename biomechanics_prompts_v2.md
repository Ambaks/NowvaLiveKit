# Biomechanics Pipeline — Claude Code Prompts v2

## Integrated with NowvaLiveKit

### Before Starting

1. Place `biomechanics_implementation_v2.md` and `squat_rack_implementation.md` in your project root
2. Your project root is the `NowvaLiveKit/` directory
3. The existing codebase includes: voice agent (`src/agents/`), IPC system (`src/core/ipc_communication.py`), workout session (`src/core/workout_session.py`), main orchestrator (`src/main.py`), existing pose process (`src/pose/`), and existing biomechanics prototype (`src/biomechanics/`)

Feed these prompts to Claude Code **sequentially**. Each builds on the previous.

---

## PROMPT 0 — Foundation & Integration Setup

```
Read the files `biomechanics_implementation_v2.md` and `squat_rack_implementation.md` in the project root. These are the implementation spec and architectural design for a real-time biomechanics coaching pipeline.

IMPORTANT: This project already has a working voice agent, IPC system, workout session management, and main orchestrator. Read and understand these existing files before creating anything:
- `src/agents/voice_agent.py` — the existing LiveKit voice agent (DO NOT modify)
- `src/core/ipc_communication.py` — the existing UNIX socket IPC system (DO NOT modify)
- `src/core/workout_session.py` — existing workout tracking (DO NOT modify yet)
- `src/core/agent_state.py` — existing state management (DO NOT modify)
- `src/main.py` — the main orchestrator (we will modify this later)
- `src/pose/pose_estimation_process.py` — the OLD pose process (we will REPLACE this later)
- `src/biomechanics/complete_pipeline.py` — existing biomechanics prototype (reference for refactoring)

Now create the biomechanics pipeline foundation under `src/biomechanics/`. The existing `src/biomechanics/` directory has some old files — preserve `complete_pipeline.py` and the week folders as reference, but create the new modular structure alongside them.

1. Create the directory structure under `src/biomechanics/` as specified in Section 1 of the v2 implementation doc. Create all `__init__.py` files. The directories to create are:
   - `src/biomechanics/pose/`
   - `src/biomechanics/triangulation/`
   - `src/biomechanics/kinematics/`
   - `src/biomechanics/faults/`
   - `src/biomechanics/faults/rules/`
   - `src/biomechanics/coaching/`
   - `src/biomechanics/viz/`
   - `src/biomechanics/utils/`

2. Create `src/biomechanics/utils/types.py` with ALL shared Pydantic data types from the v2 spec Section 7 (same as v1 Section 3): Keypoint2D, Skeleton2D, MultiViewPose, Point3D, Skeleton3D, JointAngles, FaultSeverity, FaultEvent, RepData, SessionState, PipelineFrame. Include to_numpy() methods and all helpers.

3. Create `src/biomechanics/utils/timing.py`:
   - `@timed` decorator that records execution time
   - `LayerTimer` context manager
   - `PipelineProfiler` class for per-layer latency tracking (mean/p50/p95/p99)

4. Create `src/biomechanics/utils/geometry.py`:
   - `angle_between_vectors(v1, v2) -> float` (degrees)
   - `project_to_plane(point, plane_normal, plane_point) -> np.ndarray`
   - `midpoint(p1, p2) -> np.ndarray`

5. Create `config/biomechanics.yaml` with the full configuration from the v2 spec Section 10.

6. Create `src/biomechanics/config.py`:
   - `PipelineConfig` Pydantic model that loads from `config/biomechanics.yaml`
   - `load_pipeline_config(path: str = None) -> PipelineConfig`
   - Sub-configs for each layer: CaptureConfig, PoseConfig, etc.

7. Create test fixtures:
   - `tests/test_biomechanics/conftest.py` with shared fixtures
   - `tests/test_biomechanics/fixtures/sample_keypoints.json` — COCO 17 keypoints for a half-squat (1280x720)
   - `tests/test_biomechanics/fixtures/sample_3d_points.json` — same pose in 3D meters
   - `tests/test_biomechanics/fixtures/sample_angles.json` — expected joint angles (~70° hip, ~80° knee, ~25° ankle, ~30° trunk)

8. Add biomechanics dependencies to the existing `requirements.txt` (append, don't overwrite):
   - onnxruntime>=1.17
   - mediapipe>=0.10.9
   - pydantic>=2.5
   - pyyaml>=6.0
   (torch is likely already in requirements — check first)

Verify:
- `python -c "import sys; sys.path.insert(0, 'src'); from biomechanics.utils.types import JointAngles; print('types OK')"` works
- `python -c "import sys; sys.path.insert(0, 'src'); from biomechanics.config import load_pipeline_config; print('config OK')"` works
```

---

## PROMPT 1 — Pose Estimation (MediaPipe)

```
Read `biomechanics_implementation_v2.md` for context.

Build the pose estimation layer in `src/biomechanics/pose/`. Start with MediaPipe as the zero-setup backend.

1. Create `src/biomechanics/pose/base.py` with abstract `PoseEstimator`:
   - `estimate(frame: np.ndarray, camera_id: int = 0) -> Skeleton2D`
   - `estimate_3d(frame: np.ndarray) -> Skeleton3D` — for single-camera 3D (MediaPipe provides this)
   - Class-level `KEYPOINT_NAMES` for COCO 17

2. Create `src/biomechanics/pose/mediapipe_fallback.py`:
   - Uses mediapipe.solutions.pose with model_complexity=1
   - Maps MediaPipe's 33 BlazePose landmarks to COCO 17 format:
     * 0→nose, 2→left_eye, 5→right_eye, 7→left_ear, 8→right_ear
     * 11→left_shoulder, 12→right_shoulder, 13→left_elbow, 14→right_elbow
     * 15→left_wrist, 16→right_wrist, 23→left_hip, 24→right_hip
     * 25→left_knee, 26→right_knee, 27→left_ankle, 28→right_ankle
   - `estimate()` returns 2D pixel coords using MediaPipe's `pose_landmarks`
   - `estimate_3d()` returns 3D world coords using MediaPipe's `pose_world_landmarks`
   - Filters keypoints below confidence threshold (default 0.3)

3. Create `src/biomechanics/viz/overlay_2d.py`:
   - `draw_skeleton(frame, skeleton_2d, ...)` — draws keypoints + limb connections
   - COCO skeleton connections: (5,6), (5,7), (7,9), (6,8), (8,10), (5,11), (6,12), (11,12), (11,13), (13,15), (12,14), (14,16)
   - Green circles for high confidence, yellow for low
   - FPS counter in top-left

4. Create `scripts/test_pose_live.py`:
   - Opens webcam via OpenCV
   - Runs MediaPipe pose on each frame
   - Draws skeleton overlay
   - Shows with cv2.imshow, press 'q' to quit
   - This is a manual visual verification tool, NOT a pytest test

5. Write tests in `tests/test_biomechanics/test_pose.py`:
   - Test MediaPipePoseEstimator returns valid Skeleton2D with 17 keypoints
   - Test keypoint names match COCO order
   - Test estimate_3d returns Skeleton3D

Verify: `python scripts/test_pose_live.py` shows skeleton overlay on webcam.
```

---

## PROMPT 2 — Analytical Inverse Kinematics

```
Read `biomechanics_implementation_v2.md` for context.

Build the analytical IK solver in `src/biomechanics/kinematics/`. Also look at the existing IK code in `src/biomechanics/complete_pipeline.py` (the `SimpleLowerBodyIK` reference) for context on what angles are already being computed.

1. Create `src/biomechanics/kinematics/base.py`:
   - Abstract `IKSolver` with `solve(skeleton: Skeleton3D) -> JointAngles`

2. Create `src/biomechanics/kinematics/analytical_ik.py`:
   - `AnalyticalIKSolver` implementing IKSolver
   - Computes ALL JointAngles fields from 3D landmarks using vector math:
     * hip_flexion_r/l: angle between trunk and thigh vectors at hip joint
     * hip_adduction_r/l: medial/lateral angle of thigh from sagittal plane
     * knee_flexion_r/l: angle at knee between thigh and shank
     * ankle_dorsiflexion_r/l: angle at ankle between shank and foot
     * trunk_flexion: trunk angle from vertical (sagittal)
     * trunk_lateral_bend: lateral deviation (frontal)
     * pelvis_tilt: pelvis angle from horizontal
   - Uses the geometry utilities from `utils/geometry.py`
   - Handles missing/low-confidence landmarks gracefully (return 0.0, log warning)

3. Write tests in `tests/test_biomechanics/test_kinematics.py`:
   - Test with sample_3d_points.json fixture — angles should roughly match sample_angles.json
   - Test standing pose (all angles near 0°)
   - Test bilateral symmetry — symmetric input gives symmetric output
   - Test ranges are physically plausible (no angles > 180°)

4. Create `scripts/test_ik_live.py`:
   - Opens webcam
   - MediaPipe 3D pose → AnalyticalIKSolver
   - Overlays angle values on frame (hip, knee, ankle, trunk for both sides)
   - Press 'q' to quit

Verify: `python scripts/test_ik_live.py` — squat in front of webcam, verify hip/knee flexion increases as you descend. `pytest tests/test_biomechanics/test_kinematics.py -v` passes.
```

---

## PROMPT 3 — Fault Detection & Rep Counting

```
Read `biomechanics_implementation_v2.md` for context. Look at the fault detection table in `squat_rack_implementation.md` Section 3.5.

Build the fault detection system in `src/biomechanics/faults/`.

1. Create `src/biomechanics/faults/fault_types.py`:
   - FaultType enum: DEPTH, BILATERAL_ASYMMETRY, HEEL_RISE, FORWARD_LEAN, KNEE_VALGUS, BACK_ROUNDING
   - DEFAULT_THRESHOLDS dict from config
   - Abstract `FaultRule` base: `evaluate(angles: JointAngles, history: deque[JointAngles]) -> Optional[FaultEvent]`

2. Create `src/biomechanics/faults/rep_counter.py`:
   - RepCounter with IDLE/IN_REP state machine
   - Transition on hip flexion crossing 30° threshold
   - Minimum rep duration filter (20 frames)
   - On rep complete: return RepData with max_depth_angle, faults, angle series
   - `update(angles, faults) -> Optional[RepData]`

3. Create fault rules in `src/biomechanics/faults/rules/`:
   - `depth.py` — DepthRule: quarter (<60°), half (60-90°), parallel (90-100°), below parallel (>100°)
   - `symmetry.py` — SymmetryRule: compare L/R hip and knee flexion, severity by difference
   - `heel_rise.py` — HeelRiseRule: track ankle vertical position vs rep start
   - `forward_lean.py` — ForwardLeanRule: trunk_flexion thresholds, only during rep
   - `knee_valgus.py` — KneeValgusRule: v1 rule-based on hip_adduction angle

4. Create `src/biomechanics/faults/rule_engine.py`:
   - RuleEngine orchestrates all rules
   - History deque (maxlen=90)
   - Deduplicates consecutive same-fault frames

5. Write tests in `tests/test_biomechanics/`:
   - `test_rep_counter.py`: synthetic angle sequence simulating 3 reps → verify count, depth, timing
   - `test_faults.py`: test each rule with known angle values

Verify: `pytest tests/test_biomechanics/test_rep_counter.py tests/test_biomechanics/test_faults.py -v`
```

---

## PROMPT 4 — Coaching & IPC Integration

```
Read `biomechanics_implementation_v2.md` Sections 4, 5, and 6 carefully. This is the integration layer that connects the biomechanics pipeline to the existing NowvaLiveKit voice agent.

IMPORTANT: Read `src/core/ipc_communication.py` to understand the existing IPC system. We are USING it, not replacing it.

1. Create `src/biomechanics/coaching/cue_cache.py`:
   - Implement the full CueCache class from the spec Section 4.2
   - SQUAT_CUES, DEADLIFT_CUES, DEFAULT_CUES dictionaries
   - EXERCISE_CUE_MAP for matching exercise names to cue sets
   - `prepare_for_exercise(exercise_name) -> Dict[str, str]` — returns cues to cache
   - `get_cue_for_fault(fault_type, timestamp) -> Optional[str]` — rate-limited cue lookup
   - `get_rep_cue(rep_number) -> Optional[str]` — rep count cue key
   - `get_positive_cue() -> Optional[str]` — random positive reinforcement
   - Pre-cache rep count strings 1-20

2. Create `src/biomechanics/coaching/ipc_bridge.py`:
   - Implement the full IPCBridge class from the spec Section 5
   - Takes an IPCClient instance (from existing `core.ipc_communication`)
   - `prepare_exercise(exercise_name)` — sends cache_cues message via IPC
   - `send_frame_data(frame: PipelineFrame)` — throttled frame data
   - `send_fault(fault: FaultEvent)` — deduplicated, rate-limited, includes cue key
   - `send_rep_complete(rep: RepData)` — sends rep data + legacy rep_count + plays rep cue + positive cue for clean reps
   - `send_set_complete(set_number, reps)` — computes summary stats and sends
   - `send_pipeline_status(status, latency)` — health status
   - Maintains backward compatibility with old message format (still sends "type": "rep_count" messages)

3. Create `src/biomechanics/coaching/session_tracker.py`:
   - SessionTracker class that detects set boundaries
   - Set boundary = pause > `coaching.set_timeout_seconds` (default 30s) between reps
   - Accumulates reps per set
   - When set ends, triggers `ipc_bridge.send_set_complete()`
   - Tracks session-level stats: total reps, total sets, avg depth across session

4. Write tests:
   - Test CueCache returns correct cues for "Barbell Back Squat" (should get SQUAT_CUES)
   - Test CueCache rate limiting (same fault within 2s returns None)
   - Test IPCBridge with a mock IPCClient — verify message format matches spec
   - Test SessionTracker set boundary detection with timed rep sequence

Verify: `pytest tests/test_biomechanics/ -v` — all tests pass.
```

---

## PROMPT 5 — Pipeline Assembly & Live Demo

```
Read `biomechanics_implementation_v2.md` Section 6 for the pipeline entry point.

Connect all layers into the pipeline and create the live demo. This is the moment everything comes together.

1. Create `src/biomechanics/pipeline.py`:
   - BiomechanicsPipeline class wiring all layers:
     * Webcam capture (OpenCV)
     * Pose estimation (MediaPipe fallback)
     * IK solve (analytical)
     * Fault detection (rule engine)
     * Rep counting
   - `process_frame() -> PipelineFrame` with per-layer timing
   - `release()` for cleanup
   - Handles errors gracefully — if pose fails, skip downstream layers
   - In single-camera mode (default): use MediaPipe's estimate_3d() directly, skip triangulation

2. Create `src/biomechanics/viz/dashboard.py`:
   - OpenCV-based debug dashboard showing:
     * Camera view with skeleton overlay (left side)
     * Joint angles text panel (right side)
     * Rep counter display
     * Active faults in red
     * Per-layer latency bars at bottom
     * FPS counter

3. Replace `src/pose/pose_estimation_process.py` with the new version from the spec Section 6:
   - Imports BiomechanicsPipeline and IPCBridge
   - Connects to existing IPCClient
   - Pre-caches cues for the exercise
   - Runs pipeline loop, sends data to voice agent via bridge
   - Handles graceful shutdown
   - Accepts cam IDs and exercise name as command-line args
   - **IMPORTANT: Back up the old file as `pose_estimation_process.py.bak` before replacing**

4. Update `src/main.py` to:
   - Pass exercise name to the new pose estimation subprocess (get from workout session data)
   - Handle new IPC message types (cache_cues, fault, rep_complete, set_complete, play_cue, pipeline_status)
   - Print structured logs for each new message type
   - Keep backward compatibility with old message types

5. Create `scripts/benchmark_pipeline.py`:
   - Run pipeline for N frames (default 300)
   - Report per-layer latency: mean, p50, p95, p99
   - Report total FPS

6. Write `tests/test_biomechanics/test_pipeline.py`:
   - Create a synthetic test video (20 frames)
   - Run pipeline on it
   - Verify PipelineFrame has populated joint_angles and timing
   - Don't test exact values — just verify types and that pipeline completes

Verify:
- `python scripts/test_pose_live.py` still works (standalone test)
- `python -c "import sys; sys.path.insert(0, 'src'); from biomechanics.pipeline import BiomechanicsPipeline; print('pipeline OK')"` works
- `python scripts/benchmark_pipeline.py --frames 100` reports latency stats
- `pytest tests/test_biomechanics/test_pipeline.py -v` passes
```

---

## PROMPT 6 — Voice Agent Cache Integration

```
This prompt wires up the pre-cached audio cue system on the voice agent side. The biomechanics pipeline sends "cache_cues" and "play_cue" messages via IPC. The voice agent needs to handle them.

Read `src/agents/voice_agent.py` to understand the existing architecture. Read `src/core/ipc_communication.py` for the IPC protocol.

The challenge: the OpenAI Realtime API (used by the voice agent) streams audio in real-time. For pre-cached cues, we need a different approach. The options:

**Option A (Recommended): OpenAI TTS API pre-generation**
Before each set, call OpenAI's standard TTS API (not Realtime) for each cue text, store the audio bytes in a dict. When a "play_cue" message arrives, inject the audio into the LiveKit audio track.

**Option B: Pre-recorded audio files**
Ship a set of pre-recorded coaching cue audio files. On "play_cue", play the file. Zero latency, but less flexible.

**Option C: Let the Realtime agent speak the cues**
When a "fault" message arrives, inject the cue text into the voice agent's conversation context as a system message, causing it to speak the cue. This has the most natural voice but adds ~200-400ms latency.

Implement **Option A** with **Option C as fallback**:

1. Create `src/services/audio_cue_service.py`:
   - AudioCueService class that manages cached TTS audio
   - `async cache_cues(cues: Dict[str, str])` — generate TTS for each cue using OpenAI TTS API:
     ```python
     from openai import AsyncOpenAI
     client = AsyncOpenAI()
     response = await client.audio.speech.create(
         model="tts-1",
         voice="nova",  # Fast, clear voice
         input=cue_text,
         response_format="pcm",
         speed=1.1  # Slightly fast for coaching urgency
     )
     audio_bytes = response.read()
     ```
   - Store in `self.cache: Dict[str, bytes]`
   - `get_cue_audio(cue_key: str) -> Optional[bytes]` — retrieve cached audio
   - Cache generation should be async and run concurrently for all cues (use asyncio.gather)
   - Include TTL — cache expires after 30 minutes (regenerate on next set)
   - Log cache generation time (should be <5s for ~25 cues)

2. Update `src/main.py` IPC message handler:
   - On "cache_cues": call AudioCueService.cache_cues() with the cue dict
   - On "play_cue": retrieve audio from cache, send to audio output
   - On "fault": if cue key present, play cached audio. If cache miss, fall back to Option C (inject into voice agent context)

3. Update `src/agents/prompts/workout_prompt.py`:
   - Add the "Real-Time Data Feed" section from the v2 spec Section 9.3
   - This tells the voice agent how to interpret biomechanics data it receives

4. Test the cue caching:
   - Write a test that generates cues for a squat exercise
   - Verify all cue audio files are generated
   - Verify playback latency is <10ms from cache

Note: If the OpenAI TTS API is not available (no API key, rate limited, etc.), the system should fall back to Option C automatically. The biomechanics pipeline continues working regardless — it just sends "fault" messages with cue keys, and if the audio isn't cached, the voice agent speaks the cue text naturally.
```

---

## PROMPT 7 — RTMPose Integration (Refactor Existing Code)

```
The existing project already has RTMPose working in `src/biomechanics/complete_pipeline.py` and the week1_pose folder. Refactor this into the new modular structure.

1. Examine the existing RTMPose code:
   - Look at `src/biomechanics/complete_pipeline.py` line that imports `RTMPoseEstimator`
   - Find the actual implementation — it's likely in a `week1_pose` subfolder
   - Understand the model format, preprocessing, and postprocessing

2. Create `src/biomechanics/pose/rtmpose.py`:
   - Refactor the existing RTMPoseEstimator into the new PoseEstimator interface
   - Use ONNX Runtime with CoreMLExecutionProvider for M2 acceleration
   - Must return Skeleton2D with COCO 17 keypoint format
   - Include proper error handling for model loading failures

3. Create `scripts/download_models.py`:
   - Download the RTMPose ONNX model (same one the existing code uses)
   - Save to a consistent location under `src/biomechanics/pose/models/`

4. Update `src/biomechanics/config.py` and `config/biomechanics.yaml`:
   - Add rtmpose model path config
   - `pose.backend` can be "rtmpose" or "mediapipe"

5. Update `src/biomechanics/pipeline.py`:
   - When config says rtmpose, use RTMPoseEstimator; otherwise MediaPipe

6. Benchmark comparison: add to `scripts/benchmark_pipeline.py`:
   - Compare RTMPose vs MediaPipe latency on M2
```

---

## PROMPT 8 — Triangulation (Refactor Existing Stereo Code)

```
The existing project has stereo triangulation working in `src/biomechanics/complete_pipeline.py` with `StereoReconstructor`. Refactor into the new structure.

1. Examine existing stereo code in the week2_stereo folder.

2. Create `src/biomechanics/triangulation/stereo.py`:
   - Refactor StereoReconstructor into the new module
   - OpenCV triangulatePoints with DLT
   - Accept calibration parameters from config

3. Create `src/biomechanics/triangulation/calibration.py`:
   - Camera calibration utilities
   - Load/save calibration from npz files
   - Generate simulated camera params for testing

4. Create `src/biomechanics/triangulation/sim_cameras.py`:
   - SimulatedMultiCam for testing with single webcam
   - Uses MediaPipe 3D as pseudo ground truth
   - Projects through virtual cameras, adds noise
   - Triangulates back — should recover original within noise margin

5. Update pipeline to use triangulation when `config.triangulation.enabled = true`

6. Tests: verify triangulation recovers known 3D points from 2D projections (RMSE < 5cm with noise)
```

---

## PROMPT 9 — End-to-End Integration Test

```
This is the final integration test. Run the FULL system: voice agent + biomechanics pipeline + IPC.

1. Create `scripts/test_full_integration.py`:
   - Start the IPC server (like main.py does)
   - Launch the biomechanics pipeline subprocess
   - Verify IPC messages flow correctly:
     * pipeline_status: initialized
     * cache_cues message arrives with cue dict
     * frame_data messages arrive at expected rate
     * When doing squats: rep_complete messages fire
     * Faults fire when form is bad
   - Print all received messages for verification
   - Run for 30 seconds then shut down cleanly

2. Create `scripts/demo_standalone.py`:
   - Run the biomechanics pipeline WITHOUT the voice agent
   - Opens webcam, runs full pipeline, shows OpenCV dashboard
   - Prints rep counts, faults, and timing to console
   - Useful for testing the pipeline in isolation

3. Update the README at project root:
   - Add a "Biomechanics Pipeline" section
   - Quick start: how to run standalone demo
   - How it integrates with the voice agent
   - Architecture diagram (text)
   - Configuration reference

4. Final verification checklist:
   - [ ] `python scripts/demo_standalone.py` — webcam with live angles and rep counting
   - [ ] `python scripts/benchmark_pipeline.py --frames 300` — full latency report
   - [ ] `pytest tests/test_biomechanics/ -v` — all tests pass
   - [ ] Pipeline sends correct IPC messages
   - [ ] Cue cache generates correct cues for different exercises
   - [ ] Rep counter works on actual squats
   - [ ] Fault detection fires on bad form
```

---

## Tips

**If Claude Code asks about the voice agent:**
The voice agent is already built and working. The biomechanics pipeline communicates with it via IPC — it does NOT import from or modify the voice agent code directly.

**If dependencies conflict:**
The existing project uses Python 3.11. MediaPipe, ONNX Runtime, and PyTorch all work on M2 with Python 3.11. If there's a conflict, prioritize the existing project's dependencies.

**For testing without cameras:**
Use `--source video --video-path <file>` to test with recorded video. Download any squat video from YouTube for testing.

**Build order priority:**
Prompts 0–5 get you a working pipeline integrated with the voice agent. Prompts 6–8 add refinements. Prompt 9 is the integration test.

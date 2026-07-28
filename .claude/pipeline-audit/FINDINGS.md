# Biomechanics Pipeline Audit — Consolidated Findings

Consolidated from two independent audits (Opus 5 + Fable 5), 2026-07-27. Findings both
audits reached independently are marked **[both]** — treat those as highest-confidence.
Work through top to bottom; check off as fixed.

---

## Tier 0 — The pipeline corrupts its own data (fix before anything else)

### [x] F1. ROMClamp folds the legs on 100% of frames  **[both]**
`rom_clamp.py` runs unconditionally in the pre-IK chain (`pipeline.py:515`,
`ENABLE_PREIK_FILTERS=true` is the shipping default). Two independent bugs:

1. **Interior angle vs. flexion mixup** — `_clamp_joint` receives
   `_joint_angle_deg(hip, knee, ankle)` (interior angle, 180° = straight) but compares
   it against flexion bounds (`KNEE_FLEXION_MAX_DEG = 160`, hip 140, elbow 155). A
   straight standing leg (~178°) is "out of range" and gets rotated. 
2. **Y-sign inversion** — `rom_clamp.py:93-97` computes `vert = -shin[1]` assuming Y-up;
   the pipeline is Y-down. `vert` is always negative, pinned to 1e-9, so shin tilt
   returns exactly 90° every frame and the dorsiflexion clamp fires unconditionally.

Measured on a perfect standing skeleton: ankle moved ~89-91 cm, 180° knee → 23°, tibia
stretched 28% (0.450 → 0.575 m), legs cross. On real squat video: ankle-above-knee on
309/309 frames with the clamp, 0/309 without; knee flexion range compressed from
17°-125° to 109°-150°.

**This is the true generator of the folded-leg corruption** — the GroundClamp
leg-extension validator is correctly rejecting ROMClamp output forever, which is why
`[GROUND CLAMP] Calibration rejected` fires and ground calibration never completes.
`rom_clamp.py` is the only filter with no test file.

**Fix:** delete the call today (one line). Reintroduce later only with corrected
conventions, per-user calibrated ROM (not population constants), and tests.

### [x] F2. Standing gate advances up to 3× per frame; calibration never completes
`BoneLengthConstraints.enforce()` calls `standing_gate.check()` as a side effect
(`bone_constraints.py:150`), and `enforce()` runs twice per frame (`pipeline.py:514`
and `:518`) on top of the pipeline's own check at `:493`. So
`required_consecutive_frames: 5` latches in ~2 frames, and bone calibration completes
in 15 frames instead of 30, with half the samples pre-smoothing and half post.

Net effect in production (with F1): bone-length and ground calibration **never finish**,
so `apply_body_proportion_scaling()` / `set_body_proportions()` never run. Every fault
threshold silently sits at population defaults — personalization is dead.

**Fix:** remove the gate side-effect from `enforce()`, delete the duplicate `enforce()`
call, then add one integration test that drives the full filter chain in pipeline order
over synthetic standing frames and asserts both calibrators complete. That single test
catches F1 and F2 together (existing `test_ground_clamp.py` tests the clamp in
isolation, which is exactly why this shipped).

Verified end-to-end over 200 standing frames:
```
AS SHIPPED (rom on, double enforce)   gate=False  bone_cal=False  ground_cal=False
rom clamp REMOVED, double enforce     gate=True   bone_cal=True   ground_cal=True
rom on, single enforce                gate=True   bone_cal=True   ground_cal=False
```

### [x] F3. No single source of truth for the coordinate frame  **[both, different symptoms]**
The IK solver mixes conventions: `_compute_trunk_lateral_flexion` and
`_compute_pelvis_tilt` use `_VERTICAL_UP` while `_compute_trunk_flexion` and
`_compute_ankle_dorsiflexion` use `_VERTICAL_DOWN`. On an upright pose in the
production (Y-down) frame: trunk_lateral_flexion reads 180° and pelvis_tilt 72°
(both should be 0°). Every IK test fixture is Y-up (`test_kinematics.py:38` says so),
so the entire suite validates the solver in the opposite frame from production —
which is why two angles have been wrong without a test failing. The same bug class
produced F1's shin tilt and the choreographer sending live poses to the viewer in raw
MediaPipe axes (upside-down and mirrored).

**Fix:** one shared vertical constant; regenerate every fixture from real Y-down
output. Until tests run in the production frame, no angle-level fix is verifiable.

---

## Tier 1 — Diagnosis engine (the core IP) computes wrong answers

### [x] F4. `dorsiflexion_drop` is circular, and the live path has a sign error
- `rom["dorsiflexion_drop"]` is fed from `peakDorsi` — the max dorsiflexion actually
  *used* in the baseline set — then consumed as ROM *capacity* by four evidence tests.
  Working set ≈ baseline set → utilization ≈ 1.0 → `limited_ankle_df` fires at
  evidence 1.0 for essentially every athlete, `bracing_failure` is permanently
  discounted ×0.3, `depth_cue_unfamiliar` drops 0.8 → 0.1.
- Live path: `drop = baseline - current`, but dorsiflexion *increases* during a squat,
  so the value stays pinned at its 0.0 initializer → `dorsi_factor = 1.0` → every
  athlete gets the maximum prescribed stance (2.0× shoulder width) and toe-out.

**Fix:** replace with a real measured capacity and fix the sign. Unblocks four evidence
tests, both corrector ROM guards, and the heel-rise threshold.

### [x] F5. Prescription layer overrides its own measurements
- `foot_angle_target_deg` computes a personalized 15-40° target then discards the
  bottom half with `max(30.0, ...)`. Natural toe-out is 5-15°, so `narrow_foot_angle`
  fires for nearly everyone — and is then force-surfaced past Bayesian competition as
  "a safe, universally beneficial cue." 30-40° forced toe-out is not universally safe,
  and hip external-rotation ROM is never measured anywhere.
- Stance delta always widens: `target_ratio = max(dorsi_target, current + 0.15, 1.0)`
  recommends ≥0.15 shoulder-widths of widening regardless of measurement, while the
  evidence test that justified the cue uses a different target and would return zero.
- Correction floors fire below the detection threshold: 4.1° of valgus still gets a
  4° knees-out push (≈3 cm lateral knee displacement per side), with no ROM check.

### [x] F6. Sign and normalization bugs in fault measurement
- `hip_adduction`'s two sign branches are algebraically identical, so the left side is
  inverted relative to the right; downstream `abs()` makes knees-out (the correction
  the engine itself prescribes) indistinguishable from knee cave.
- Single-camera FPPA is normalized by hip-to-ankle vertical span, which collapses with
  depth: identical knee cave reads ~1.6× larger at parallel, ~3× at the bottom — and
  the valgus rule samples only at the bottom, i.e. at maximum inflation.

**Fix:** correct both signs, replace the depth-dependent normalization, then re-derive
the valgus thresholds.

---

## Tier 2 — What the athlete sees (choreographer / visualizer)

### [x] F7. Corrected-pose morphs are anatomically impossible
`build_morph_frames` (`keypoint_corrector.py:989`) linearly interpolates joint
positions; interpolating a rotating limb cuts the chord, so bones shrink mid-morph.
Measured on a realistic knees-out + depth correction: torso −9.7 cm (19.8%), thighs
~8%. Also the Gaussian taper starts at weight 0.044, so frame 0 isn't the observed
pose. **Fix:** slerp bone *directions* down the kinematic chain — cheap, exact by
construction.

### [x] F8. No anatomical joint-limit gate on synthesized poses
Nothing validates the choreographer's output — no knee-flexion max, no hyperextension
check, no varus/valgus ceiling, no hip ROM check — and these poses are shown to the
user as a movement target. **Fix:** add a `validate_pose()` hard gate before any
synthesized pose reaches a user. Highest-value single addition in this tier.

### [x] F9. The "before" pose is bilaterally symmetrized
`pose_stack[0]` — shown while narration says "this is you at the bottom" — erases the
asymmetry fault being diagnosed; `weight_shift_cue` renders a near-zero shift for the
very fault it explains.

### [ ] F10. Depth-to-parallel forced past the ankle budget
When ankle ROM can't support parallel depth, the choreographer commits an
ROM-violating pose silently, with no flag to the narration.

### [ ] F11. Bone-length leaks around an otherwise sound core
- Viewer-side `enforceBoneLengths` is a single non-convergent pass over conflicting
  constraints (fixing [5,6] re-breaks [6,8]); head and foot segments aren't in the
  constraint list at all, so they visibly stretch during every morph.
- `bottom_up_build`'s pelvis reconciliation averages two disagreeing hip estimates,
  breaking femur length by 0.3-0.5 cm.

**Keep:** `KeypointCorrector.correct()`'s canonicalize-then-lock-lengths invariant and
the FK core (real kinematic chain from grounded feet, lengths regression-tested to
1e-4, Python/JS 2-link IK ports agree). Both audits called this genuinely well-built.

---

## Tier 3 — Accuracy ceiling and backend strategy

### [ ] F12. Monocular MediaPipe is the accuracy ceiling; the fix is built but off
`backend: mediapipe`, `NOWVA_MULTI_CAMERA=false`, no `.onnx` models downloaded — all
3D comes from monocular world-landmark regression. Swapping only model complexity
changes measured knee flexion by 8.3° mean / 20° p95 / 34° max while each model is
individually smooth (0.4-0.8°/frame): systematic bias, not noise. The 3-camera DLT
stack in `src/biomechanics/triangulation/` is complete and unused. Enabling it is the
single largest accuracy win available.

### [ ] F13. RTMPose backend defects to fix before enabling  **[both]**
- `src/biomechanics/pose/models/` doesn't exist; `download_models.py:49` writes to
  `scripts/src/biomechanics/pose/models/` (one parent short).
- No person detection or bbox crop: `rtmpose.py:167` squashes the full 1280×720 frame
  to 192×256 (2.37× horizontal compression; the lifter occupies ~37 px). Top-down
  models need a crop + aspect-preserving affine warp. Fix: detect once, track bbox from
  the previous frame's pose.
- Plain argmax SimCC decode (`rtmpose.py:207`), no sub-pixel refinement: ~1.7 px
  staircase noise that the One Euro filters then smooth away at the cost of lag.
- `confidences = sigmoid(max_logit)` (`rtmpose.py:214`) floors every keypoint at 0.5
  including undetected ones; with all confidence gates at 0.1, hallucinated keypoints
  pass everywhere. mmpose uses the max value directly — verify against real logit
  distributions.

### [ ] F14. The Jetson 3D path is a now-decision
MediaPipe's CPU delegate cannot touch the DLA/tensor cores — the 40 TOPS is currently
unreachable. Measured 14.2 ms/frame (heavy, M-series CPU core) extrapolates to
35-55 ms on an Orin Nano: an 18-28 FPS ceiling before anything else runs. Decide now:
RTMPose-TensorRT + triangulation vs. an accelerated monocular lifter.

---

## Tier 4 — Performance (after correctness; guardrail #4)

### [ ] F15. Pose inference is ~98% of the frame budget  **[both]**
Filter chain + IK: 0.52 ms. MediaPipe complexity 2: 64.1 ms/frame in one audit's
measurement; the other measured ~18 ms total `process_frame` with MediaPipe heavy at
14.2 ms — different configs/conditions; reconcile with the replay harness (F21). Either
way, do NOT micro-optimize the filter chain for speed. Levers: RTMPose ONNX, and
batching the 3 camera views into one inference call instead of the sequential loop at
`multi_camera.py:184-189`.

### [ ] F16. Free wins, no accuracy trade
| Change | Δ/frame (Mac) |
|---|---|
| resize-then-`cvtColor` instead of `frame[:,:,::-1].copy()` at full res | −2.7 ms (50× penalty removed) |
| BiLSTM at stride 2-3, or ONNX export | −0.7 to −1.3 ms |
| Deadline-based FPS pacing (throttle currently excludes viz/IO) | recovers 3-8 ms of period |
| Skip pose/BiLSTM during rest periods | −16 ms during rest |
| `finalize_set` (6× matplotlib savefig) → subprocess | removes 1-4 s in-loop stall (3-10 s on Orin) |
| ndarray-native filter chain + vectorized One Euro | −0.9 ms |

### [ ] F17. Four smoothing layers fighting each other
ConfidenceBlender (EMA) → KeypointPositionSmoother (One Euro, positions) →
JointAngleFilter (One Euro, angles) → PredictiveStateEstimator extrapolating 0.2 s to
undo the lag the first three added. Net: ±9° phase-lag error at peak velocity (~3
frames) on synthetic ground truth. ConfidenceBlender blends toward the previous
position with weight 1−confidence while MediaPipe reports high confidence almost
everywhere — mostly pure lag. Consider dropping it and smoothing bone directions
instead of positions, which also removes the need for the second
`BoneLengthConstraints.enforce()` at `pipeline.py:518`.

### [ ] F18. Triangulation quality and cost (matters once F12 lands)
- No robust view selection: one bad view above 0.3 confidence drags the least-squares
  fit. Leave-one-out + lowest-reprojection subset = 3 solves/keypoint, cheap.
- Unweighted, unnormalized DLT: no confidence weighting, no Hartley normalization, no
  iterative depth reweighting — all standard, all cheap.
- Per-keypoint Python loop with dict/Point3D construction: one stacked (19, 2N, 4)
  SVD is ~50× faster.
- `MultiViewPose(frame_index=0)` hardcoded at `multi_camera.py:197` — every
  triangulated skeleton reports frame 0.

### [ ] F19. Ground plane is the ankle plane
`bridge.py:34` grounds each frame by subtracting `min(ankle_y)`; ankles sit ~7-8 cm
above the floor, so "ground" is off by that much while
`compute_balance_target_ground` uses `HEEL_OFFSET_M = 0.06` against a true floor —
the COM/balance solver works with a systematically wrong foot model. Per-frame
re-grounding also turns 2 cm of ankle jitter into whole-skeleton shifts, injecting
noise into `hip_y_at_bottom` (a depth feature). **Fix:** session-fixed floor plane
calibrated during standing.

### [ ] F20. Pydantic round-trips: ~240 µs/frame
Every filter stage does `to_numpy()` → work → `Skeleton3D.from_numpy()` (~8×/frame,
100× overhead per call). Immaterial on a Mac, 3-5× worse on Jetson. Pass (19,3)
arrays through the chain; construct `Skeleton3D` once at the boundary.

### [ ] F21. No working benchmark / deterministic replay harness
`pipeline_e2e` silently skips on missing fixtures (has never produced a number);
`bench_bilstm` errors on a constructor signature. A replay harness is a prerequisite
for measuring any perf change and for reconciling the F15 discrepancy.

---

## Status — 2026-07-27

F1-F9 are fixed and covered by tests. The biomechanics suite is at 491 passing,
including `test_kinematics.py::TestPhysicalPlausibility`, which had been failing
before this work. 20 failures elsewhere in `tests/` (coaching orchestrator,
demo narration, v6 verification) and 4 collection errors pre-date these changes
and were verified against a clean checkout.

New files: `src/biomechanics/utils/preik_chain.py` (the filter order, in one
place, so a test can drive the real chain), `src/biomechanics/diagnosis/pose_validation.py`
(the anatomical gate), plus `test_preik_chain.py`, `test_rom_clamp.py`,
`test_morph_frames.py`, `test_pose_validation.py`.

Two decisions deviated from what the audits proposed, both because the
measurement disagreed:

- **F6 FPPA.** The proposal was the standard clinical angle-at-the-knee, on the
  claim that a joint angle is depth-invariant. Modelling a real squat showed
  the opposite: the angle measure inflates 2.43x from standing to the bottom,
  worse than the 1.76x it was meant to replace, because both limb segments
  foreshorten in projection. Only a fixed anatomical denominator is invariant.
  Shipped: knee deviation over pelvis width, measured at 1.00x across depth and
  also invariant to camera distance. **This rescales valgus roughly 1.7x at the
  sampling point** — per-user thresholds re-derive on the next calibration, but
  the population defaults in `config/biomechanics.yaml` should be reviewed.
- **F9 asymmetry.** Preserving the athlete's asymmetry in the "before" pose
  works, but `bottom_up_build`'s pelvis reconciliation damps it (3.9 cm of hip
  drop renders as 1.0 cm). That averaging is F11, still open — until it is
  fixed the rendered hip drop understates the real one.

Also worth knowing:

- `rom_clamp.py` is no longer wired into anything. Its two bugs are fixed and it
  now has tests, so it is not a landmine, but it stays out of the chain until it
  has per-user calibrated ROM. `test_preik_chain.py` asserts it stays out.
- The duplicate `BoneLengthConstraints.enforce()` at `pipeline.py:514` was kept.
  The harm was the gate side-effect, now removed; the second pass genuinely
  repairs the length drift the position smoother introduces. It goes away with
  F17 (smooth bone directions instead of positions).
- The `rom` dict key `dorsiflexion_drop` is now `peak_dorsiflexion` everywhere,
  since it was always the observed peak and never a drop.
- `StandingPoseGate` still has deliberately frame-agnostic checks (the
  `min(angle, 180 - angle)` trick and the sign-product leg test). Those were
  left alone — they are gates, not measurements — but they are the last place
  where the coordinate frame is ambiguous.
- The choreographer works in a grounded **Y-up** frame while the pipeline is
  **Y-down**. Both are now documented at their boundaries; they are genuinely
  different frames, not a bug.

## Suggested attack order

1. **F1 + F2 today**: delete the ROMClamp call, remove the gate side-effect, delete
   the duplicate `enforce()`, add the full-chain integration test. One line of
   deletion unblocks GroundClamp, bone calibration, and personalization at once.
2. **F3**: single coordinate constant + regenerate IK fixtures in the production
   frame. Nothing angle-level is verifiable before this.
3. **F8 + F7**: `validate_pose()` gate, then slerp morphs — small, and directly
   serves the demo.
4. **F4, then F5 + F6**: the diagnosis-engine fixes, in that order (F4 unblocks the
   most downstream consumers).
5. **F12 + F13 + F15**: enable multi-camera and bring up RTMPose (fixing its defects
   first) — accuracy and speed are the same piece of work here. Decide F14 as part
   of this.
6. **F21 + F16**: replay harness first, then bank the free perf wins against it.
7. **F17-F20** as follow-on cleanup.

Where the audits disagreed: one wanted ROMClamp killed first, the other wanted the
coordinate frame fixed first ("nothing is verifiable until tests run in the real
frame"). Resolution above: the ROMClamp *deletion* is safe and frame-independent, so
it goes first; every fix that touches angle math waits for F3.

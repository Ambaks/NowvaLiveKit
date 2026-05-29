# Squat Visualizer Balance System — Full Architecture Summary

## File Layout

- **Python generator**: `scripts/visualize_video_squats.py` (~2223 lines)
  - Captures webcam squats via MediaPipe, detects reps, computes angles
  - Generates a self-contained HTML file with embedded Three.js, all JS inline
  - Can re-generate HTML from saved session data (`--refit` flag)
- **Output HTML**: `recordings/squat_refit_*.html`
  - Static self-contained file; all JS is embedded (no external dependencies except Three.js CDN)
  - Since the JS is generated from the Python f-string, fixes must go in the Python source and a `--refit` regenerates

## Two View Modes

### Replay Mode
Plays back the captured 3D keypoints frame-by-frame as-is. Computes COM/BOS from the raw captured skeleton. No FK or balance solving. Shows angles, fault classification (lean/valgus severity), and a green/red BOS polygon.

### Sandbox Mode (the balance system lives here)
The user switches to "Squat Video Replay" tab. In sandbox mode:
- The captured per-frame keypoints are loaded but can be modified
- Sliders control stance width, toe-out, dorsiflexion delta, barbell weight, body mass
- A **"Balance" button** triggers the trunk lean balance solver

## Coordinate System

The Three.js scene uses:
- **X** = forward (sagittal direction, toward toes)
- **Y** = up (vertical)
- **Z** = lateral (left-right)

The Python `extract_frame_data()` function (line ~104) transforms MediaPipe world landmarks:
```
vis_x = mp_z    (MP depth → scene forward)
vis_y = -mp_y   (MP down → scene up)
vis_z = -mp_x   (MP right → scene left)
```

Captured keypoints are then grounded (ankle Y = 0) and centered (hip midpoint X,Z = 0) by `ground_and_center()`.

## 19-Keypoint Model

Indices:
- 0: nose, 1-2: eyes, 3-4: ears
- 5: left shoulder, 6: right shoulder
- 7: left elbow, 8: right elbow
- 9: left wrist, 10: right wrist
- 11: left hip, 12: right hip
- 13: left knee, 14: right knee
- 15: left ankle, 16: right ankle
- 17: left toe (foot index), 18: right toe (foot index)

Bone connections: `[0,1],[0,2],[1,3],[2,4],[0,5],[0,6],[5,6],[5,7],[7,9],[6,8],[8,10],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16],[15,17],[16,18]`

## Segment Mass Model

Used for COM computation. Fractions sum to 1.0:
- head: 0.081, trunk: 0.497
- upper_arm (L+R): 0.056, forearm (L+R): 0.044
- thigh (L+R): 0.200, shank (L+R): 0.094, foot (L+R): 0.028

## Athlete Parameters (from calibration)

Computed by `compute_athlete_params()` from bone constraint calibration during capture:
- `bodyScale`: average ratio of (torso + thigh + shin) to reference lengths
- `torsoRatio`, `thighRatio`, `shinRatio`: per-segment ratios relative to bodyScale
- `stanceWidth`: hip-width multiplier (e.g. 1.2 = 120% of reference hip width)
- `toeOut`: degrees of toe-out angle
- `dorsiRatio`: how much dorsiflexion tracks knee flexion
- `forwardLean`: peak trunk forward lean in degrees
- `maxKneeFlex`: peak knee flexion in degrees
- Actual bone lengths in meters: `torso_avg_m`, `femur_avg_m`, `tibia_avg_m`, `shoulder_width_m`, `hip_width_m`

## Foot Geometry Constants

```
FOOT_LEN_M = measured from shoe size (EU 46 → ~29.37 cm). This is ankle-to-toe distance.
HEEL_OFFSET = 0.06 m (heel extends behind ankle)
BALANCE_FRAC = 0.35 (balance target is 35% along the ankle-to-toe length, minus heel offset)
```

`balancePointAlongFoot(footLen)` returns `BALANCE_FRAC * footLen - HEEL_OFFSET` — the distance along the foot forward direction from the ankle to the balance target. For EU 46: ~0.043 m ahead of ankle.

## Key Functions (all in the embedded JS inside the Python f-string)

### `buildSandboxKpts(fd)` — Main entry point for sandbox rendering

Takes a frame data object `fd` with `fd.kpts` (19-element array of [x,y,z]) and `fd.angles`.

**When `_balanceLocked` is false (normal sandbox):**
- Copies captured keypoints into a Float64Array
- Returns them unchanged with angle metadata from the captured angles

**When `_balanceLocked` is true (after Balance button clicked):**
- Copies captured keypoints (lower body stays as-is: hips, knees, ankles, toes)
- Computes the trunk lean offset: new lean angle = captured lean + `_balanceLeanOffsetDeg`
- Shifts upper body (shoulders 5,6 → head 0-4 → arms 7-10) by the delta between new and old shoulder midpoint
- Lower body keypoints (indices 11-18) are **untouched** — this is the key design: "pose remains constant, only trunk moves"

### `solveBalanceLeanOffsetDeg(frameData)` — Balance solver

Called when the user clicks "Balance". Computes how many degrees of trunk lean adjustment are needed to move the COM over the midfoot balance target.

**Algorithm:**
1. Copy captured keypoints into a flat array
2. Compute current COM via `computeCOM()` and balance target via `computeBalanceTargetGround()`
3. Compute the gap between COM ground projection and balance target
4. Project the gap onto the sagittal direction (perpendicular to hip lateral axis)
5. Using the upper body moment arm formula, solve for a new trunk lean angle:
   ```
   sinArg = sin(currentLean) + gapSagittal / upperMomentArm
   newLean = asin(sinArg)
   deltaDeg = newLean - currentLean (in degrees)
   ```
6. If barbell weight > 0, iterate 3x to refine with barbell position feedback
7. If |deltaDeg| > 50°, reject as "clamped" (unreasonable correction)
8. Store result in `_balanceLeanOffsetDeg` (degrees)

The `upperMomentArm` is the mass-weighted distance of upper body segments (trunk, head, arms) from the hip, normalized by total upper body mass fraction.

### `computeBalanceTargetGround(kpts, footLen)` — Balance target position

Computes the XZ ground position where COM should land for balance. For each foot:
1. If toe keypoint exists: foot forward direction = `(toe - ankle)` normalized on XZ plane
2. Fallback: foot forward = `(cos(toeOut), ±sin(toeOut))`
3. Target = `ankle + footForward * balancePointAlongFoot(footLen)`
4. Returns average of left and right foot targets

**Bug fixed (2026-05-27):** Direction was `(ankle - toe)` (backward). Fixed to `(toe - ankle)` (forward). This was causing the midfoot target disc to render ~8cm behind the ankle instead of ahead, making COM and target appear non-convergent.

### `buildSegmentCOMs(kpts, footLen)` — Segment center-of-mass positions

Computes the COM position for each body segment:
- **trunk**: midpoint of shoulder-midpoint and hip-midpoint
- **head**: nose keypoint (index 0)
- **limb segments** (upper_arm, forearm, thigh, shank): midpoint of the two joint endpoints
- **feet**: `ankle + footForward * balancePointAlongFoot(footLen)` where footForward = ground projection of (knee - ankle) direction

**Bug fixed (2026-05-27):** `footFwd()` used `(ankle - knee)` (backward). Fixed to `(knee - ankle)` (forward). Impact was ~2.4mm on total COM (foot mass is only 2.8% of body).

### `computeCOM(kpts, barbellWeight, bodyMass, footLen)` — Full-body COM

Sums `segmentCOM * segmentMassFraction` across all segments. If barbell weight > 0, blends barbell position contribution by mass ratio `barWeight / (bodyMass + barWeight)`.

Returns `{x, y, z, groundX, groundZ}` where groundX/groundZ are the XZ projection.

### `computeBOS(kpts, toeOutRad, footLen)` — Base of Support polygon

For each foot, constructs a rectangle from ankle position using the shin direction projected on ground:
- Forward direction (fx, fz) = normalized `(knee - ankle)` on XZ plane
- Heel edge: `ankle - fwd * HEEL_OFFSET`
- Toe edge: `ankle + fwd * (footLen - HEEL_OFFSET)`
- Lateral width: ±0.05 m perpendicular to forward direction
- Convex hull of all 8 corners (4 per foot) forms the BOS polygon

**Bug fixed (2026-05-27):** `footRect()` used `(ankle - knee)` (backward). Fixed to `(knee - ankle)` (forward). This was causing the BOS polygon to be shifted ~17cm backward on the ground.

### `isBalanced(com, bos)` — Balance check

Point-in-polygon test: is the COM ground projection inside the BOS convex hull? Returns `{inside: bool, marginRatio: float}` where marginRatio is the distance from COM to nearest BOS edge divided by average BOS radius. Positive when inside, negative when outside.

`BALANCE_MARGIN_MIN = 0.10` — threshold for "OK" vs "UNSTABLE" display.

### `computeSquatPose(phase, params, lockedShoulder)` — Full FK squat synthesis

Builds a complete synthetic squat skeleton from parameters (not from captured data). Used for the replay-style FK visualization. Builds bottom-up:
1. Place ankles at ground level, spread by stanceWidth
2. Place toes by foot length and toe-out angle
3. Build legs: shin tilt by dorsiflexion, valgus shift, thigh direction from knee flexion
4. Compute trunk lean analytically to balance COM over midfoot (or from locked shoulder reference)
5. Place shoulders, head, arms from trunk lean

### `balanceSandbox()` — Button handler

1. Checks `_balanceLocked` (prevents re-solving)
2. Gets current frame data
3. Calls `solveBalanceLeanOffsetDeg(frameData)`
4. If successful, sets `_balanceLocked = true` and `_balanceLeanOffsetDeg = result.leanDeg`
5. Verifies by building the sandbox pose and checking if COM is inside BOS
6. Updates UI status text

### `updateSandbox(fd)` — Per-frame sandbox render

Called every animation frame when in sandbox mode:
1. `buildSandboxKpts(fd)` → get adjusted keypoints + angle metadata
2. Position all 19 joint spheres in Three.js
3. Update bone cylinders between connected joints
4. Compute COM, BOS, balance check from the keypoints
5. Update COM/BOS/midfoot target visuals
6. Update angle readouts and fault classification in the sidebar

## Visual Elements in the Three.js Scene

- **Joint spheres** (19): green (normal) or red (fault). 0.018m radius.
- **Bone cylinders**: blue (normal) or red-tinted (fault). 0.006m radius, length computed from joint positions.
- **COM sphere**: red, 0.012m radius, at 3D COM position
- **COM disc**: red circle on ground plane at COM XZ projection
- **COM dashed line**: vertical line from ground disc to 3D sphere
- **BOS polygon**: green line loop on ground plane (convex hull of foot rectangles)
- **Midfoot target disc**: orange circle on ground at balance target XZ position
- **Midfoot target line**: orange dashed vertical line at target position
- **Ghost torso line**: cyan dashed line (used for trunk lean reference)
- **Barbell group**: bar mesh + 4 plate meshes, positioned relative to shoulder midpoint and trunk lean

## Data Flow Summary

```
Webcam → MediaPipe 3D → AnalyticalIKSolver (angles) → extract_frame_data()
  → coordinate transform (MP→scene) → ground_and_center() → phase tagging
  → compute_baseline() (rep 1) → compute_athlete_params() (bone proportions)
  → JSON embedded in HTML f-string → self-contained HTML output

In the browser:
  Replay mode: raw captured keypoints → joint positioning → bone rendering
  Sandbox mode: captured keypoints → buildSandboxKpts() → balance adjustment
    → joint positioning → COM/BOS computation → visual updates
```

## Bug Fixes Applied (2026-05-27)

Three functions had the foot forward direction reversed — computing `(ankle - reference)` instead of `(reference - ankle)`:

| Function | Old direction | Fixed direction | Impact |
|---|---|---|---|
| `computeBalanceTargetGround` | `ankle - toe` (backward) | `toe - ankle` (forward) | Midfoot target visual was ~8cm behind ankle; COM and target couldn't visually converge |
| `buildSegmentCOMs.footFwd` | `ankle - knee` (backward) | `knee - ankle` (forward) | Foot segment COM was behind ankle instead of ahead; ~2.4mm total COM error |
| `computeBOS.footRect` | `ankle - knee` (backward) | `knee - ankle` (forward) | BOS polygon was shifted ~17cm backward on ground |

The fallback branch in `computeBalanceTargetGround` (when no toe keypoint exists) correctly used `cos(toeOut)` (forward), confirming the primary branch was a simple sign error.

All three fixes are in `scripts/visualize_video_squats.py` (the Python source that generates the JS). Running `--refit` regenerates the HTML with correct code. The latest recording `recordings/squat_refit_20260526_225646.html` was also patched directly for immediate testing.

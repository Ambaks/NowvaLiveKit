# Balance Correction MVP — Implementation Prompt

## What This Project Is

A squat biomechanics visualizer (`scripts/visualize_video_squats.py`) that captures a user's squat via webcam + MediaPipe, then generates an interactive HTML/Three.js visualization. The HTML has two modes: **Replay** (scrub through captured frames) and **Sandbox** (adjust parameters and see the skeleton change). You are replacing the current Sandbox mode with a cleaner, guided correction flow.

The file is ~2583 lines. The HTML/JS/CSS is embedded in a Python f-string starting around line 700. Because it's an f-string, every `{` in the JS must be `{{` and every `}` must be `}}`. Only Python interpolation points like `{json.dumps(data)}` use single braces. **This is the #1 source of bugs when editing this file — be extremely careful.**

## The Core Idea

When someone squats with bad form, the root cause is usually **balance**. Long femurs and poor ankle mobility force the torso to lean forward to keep COM over mid-foot. The fix: widen stance, turn toes out, improve dorsiflexion — all of which allow the hips to stay further forward, so the trunk doesn't need to compensate.

The system works by **locking COM over mid-foot** and making **trunk lean the dependent variable**. When the user adjusts lower body parameters (stance width, toe-out, dorsiflexion), the lower body geometry changes where the hips sit. Since COM is locked, the trunk lean automatically recalculates to maintain balance. The user sees cause and effect: spread feet wider → trunk comes up.

## The Correction Cascade (User Flow)

The user clicks the Sandbox tab and sees a guided correction flow:

### Step 1: Depth Check (shown immediately on entering sandbox)
- Display the user's max knee flexion from `baselineData.peakKneeFlex` (already available in JS as `baselineData.peakKneeFlex`)
- Show whether they hit parallel: ~90° knee flex = parallel, >90° = below parallel
- If insufficient: amber text "Depth: 72° — parallel is ~90°"
- If sufficient: green text "Depth: 95° — below parallel ✓"
- This is informational only

### Step 2: Balance Button
- User clicks the existing "Balance" button (element `sb-balance-btn`)
- System locks the COM target over mid-foot — the target point is already computed by `computeBalanceTargetGround(kpts, FOOT_LEN_M)` (~line 1594)
- System solves for the initial trunk lean using the existing `solveBalanceLeanOffsetDeg()` (~line 1383) — this sets `_balanceLocked = true` and `_balanceLeanOffsetDeg` to the solved value
- Display the resulting trunk lean angle with severity classification using the existing `LEAN_T` thresholds (compare `180 - trunkAngleDeg` against `LEAN_T.mild`, `LEAN_T.moderate`, `LEAN_T.severe`)
- If trunk lean is acceptable (below `LEAN_T.mild`): green "Trunk lean: 18° ✓"
- If excessive: amber/red "Trunk lean: 32° — adjust parameters below to reduce"
- Enable the parameter sliders (the existing `setSandboxParamsEnabled(true)` call already does this)

### Step 3: Parameter Adjustment (sliders enabled after balance lock)
- Three parameter sliders: **stance width**, **toe-out angle**, **dorsiflexion delta**
- The animation loop already calls `updateSandbox(fd)` every frame when `viewMode === 'sandbox'` (~line 2466). This means slider changes are automatically reflected — **no new event bindings are needed for re-rendering**
- What DOES need to change: when `_balanceLocked === true`, `buildSandboxKpts()` must:
  1. Read current slider values (stance width, toe-out, dorsi delta)
  2. Build the lower body from scratch using FK (not deltas on captured keypoints)
  3. Solve trunk lean analytically to keep COM on the locked target
  4. Return the complete pose
- The user drags sliders and sees the skeleton update in real-time at 60fps

## Data Available in JavaScript

These are the key data sources already embedded in the HTML:

### `baselineData` (from rep 1)
- `baselineData.peakKneeFlex` — max knee flexion angle in degrees (depth metric)
- `baselineData.peakTrunkOffset` — peak forward lean in degrees (180 - trunk_flexion)
- `baselineData.peakDorsi` — peak dorsiflexion in degrees
- `baselineData.peakValgus` — peak valgus angle in degrees

### `AP` (athlete params — may be null if calibration failed)
- Body proportions: `AP.bodyScale`, `AP.torsoRatio`, `AP.thighRatio`, `AP.shinRatio`
- Segment lengths in meters: `AP.hip_width_m`, `AP.femur_avg_m`, `AP.tibia_avg_m`, `AP.torso_avg_m`, `AP.foot_avg_m`, `AP.shoulder_width_m`, `AP.upper_arm_avg_m`, `AP.forearm_avg_m`
- Stance: `AP.stanceWidth` (multiple of hip width), `AP.toeOut` (degrees)
- Peak angles: `AP.maxKneeFlex`, `AP.forwardLean`, `AP.dorsiRatio`

### Per-frame data (`fd` from `reps[curRep][curFrame]`)
- `fd.kpts` — array of 19 keypoints, each `[x, y, z]` (Y-up, X-forward, Z-lateral)
- `fd.angles` — object with:
  - `knee_flex`, `knee_flex_l`, `knee_flex_r` — knee flexion in degrees
  - `dorsi_l`, `dorsi_r` — ankle dorsiflexion in degrees
  - `trunk_flexion` — trunk angle (180° = upright, lower = more forward lean)
  - `knee_valgus_l`, `knee_valgus_r` — knee valgus in degrees
  - `hip_flex_l`, `hip_flex_r` — hip flexion in degrees
- `fd.phase` — normalized depth (0 = standing, 1 = max depth)

### Threshold constants
- `LEAN_T` — `{ mild, moderate, severe }` in degrees (forward lean offset)
- `VALG_T` — `{ mild, moderate, severe }` in degrees (knee valgus)

### Reference dimensions
- `REF` object: `{ hip_width: 0.22, thigh_len: 0.42, shin_len: 0.40, torso_len: 0.50, shoulder_width: 0.36, upper_arm: 0.30, forearm: 0.26, head_offset: 0.22, foot_len: 0.26 }`
- `FOOT_LEN_M` — actual foot length from shoe size (default ~0.2937m)
- `HEEL_OFFSET` — 0.06m
- `BALANCE_FRAC` — 0.35 (balance point is 35% along foot from heel)
- `SEGMENT_MASS` — object with fractional body mass per segment (head 8.1%, trunk 49.7%, etc.)

## What Needs to Change

### 1. Write a new function: `buildCorrectedPose(fd)`

This replaces the delta-based `computePerSidePose` path when balance is locked. Do NOT modify `computePerSidePose` — write a new function.

**Inputs** (read from current frame + slider values):
- `capturedKneeAngle` — from `fd.angles.knee_flex` (the depth the user actually achieved)
- `capturedDorsi` — from `(fd.angles.dorsi_l + fd.angles.dorsi_r) / 2`
- `stanceWidth` — from slider `sb-stance-width` (multiple of hip width)
- `toeOut` — from slider `sb-toe-out` (degrees)
- `dorsiDelta` — from slider `sb-d-dorsi` (degrees, added to captured dorsi)
- Segment lengths — from `AP` if available, else `REF` scaled by `AP.bodyScale`

**The FK chain** (reference: `computeSquatPose`'s `placeLeg` function at ~line 1728):

```
// Segment lengths
hipWidth = AP ? AP.hip_width_m : REF.hip_width * bodyScale
shinLength = AP ? AP.tibia_avg_m : REF.shin_len * bodyScale * shinRatio
thighLength = AP ? AP.femur_avg_m : REF.thigh_len * bodyScale * thighRatio
torsoLength = AP ? AP.torso_avg_m : REF.torso_len * bodyScale * torsoRatio
shoulderWidth = AP ? AP.shoulder_width_m : REF.shoulder_width * bodyScale

// Angles
dorsiflexionRad = (capturedDorsi + dorsiDelta) * deg2rad
kneeFlexRad = capturedKneeAngle * deg2rad
toeOutRad = toeOut * deg2rad
thighDirectionAngle = dorsiflexionRad - kneeFlexRad  // shin tilt minus knee bend

// 1. Place ankles on ground (Y=0) at stance width apart
ankleLeftZ = -(hipWidth / 2) * stanceWidth
ankleRightZ = +(hipWidth / 2) * stanceWidth
// Ankle X = 0 (origin), Y = 0 (ground)

// 2. Compute toe direction from toe-out angle (per leg)
// Left leg (side = -1):  toeDirX = cos(toeOut), toeDirZ = -sin(toeOut)
// Right leg (side = +1): toeDirX = cos(toeOut), toeDirZ = +sin(toeOut)

// 3. FK shin: ankle → knee
// Shin goes UP (Y) and FORWARD (along toe direction) based on dorsiflexion angle
kneeX = ankleX + shinLength * sin(dorsiflexionRad) * toeDirX
kneeY = ankleY + shinLength * cos(dorsiflexionRad)   // mostly vertical
kneeZ = ankleZ + shinLength * sin(dorsiflexionRad) * toeDirZ

// 4. FK thigh: knee → hip
// Thigh goes UP and BACKWARD from knee based on (dorsiflexion - kneeFlexion)
hipX = kneeX + thighLength * sin(thighDirectionAngle) * toeDirX
hipY = kneeY + thighLength * cos(thighDirectionAngle)
hipZ = kneeZ + thighLength * sin(thighDirectionAngle) * toeDirZ

// 5. Place foot_index keypoints (17, 18) — needed for BOS calculation
footIndexLeftX = ankleLeftX + FOOT_LEN_M * cos(toeOutRad)   // along toe direction
footIndexLeftZ = ankleLeftZ - FOOT_LEN_M * sin(toeOutRad)
footIndexRightX = ankleRightX + FOOT_LEN_M * cos(toeOutRad)
footIndexRightZ = ankleRightZ + FOOT_LEN_M * sin(toeOutRad)
// foot_index Y = 0 (on ground)

// 6. Compute hip midpoint
hipMidX = (hipLeftX + hipRightX) / 2
hipMidY = (hipLeftY + hipRightY) / 2

// 7. Solve trunk lean to keep COM over mid-foot target
// USE the ConstrainedChainSolver._solveTrunkFromCOM approach (~line 2113)
// This is a single asin() call — no iteration needed:
//
//   upperMass = massTrunk + massHead + massArms
//   A = (massTrunk * 0.5 * torsoLen + massHead * (torsoLen + headOffset*0.5) + massArms * torsoLen) / massTotal
//   B = upperMass / massTotal * hipMidX + lowerBodyCOMx
//   trunkLeanRad = asin((balanceTargetX - B) / A)
//
// balanceTargetX = balancePointAlongFoot(FOOT_LEN_M) * cos(toeOutRad)
// lowerBodyCOMx = weighted average of foot, shank, thigh COM X positions

// 8. Position upper body
shoulderMidX = hipMidX + torsoLength * sin(trunkLeanRad)
shoulderMidY = hipMidY + torsoLength * cos(trunkLeanRad)
// Set shoulder keypoints (5, 6) at shoulderMid ± shoulderWidth/2 in Z
// Set head (0) and face keypoints (1-4) relative to shoulder mid
// Set arm keypoints (7-10) hanging from shoulders (same as computeSquatPose ~line 1782)
```

**Return value**: same shape as `computePerSidePose` returns — `{ kpts, trunkAngleDeg, avgKneeDeg, dorsiDeg, totalTrunkLeanDeg, ... }` so `updateSandbox` can consume it without changes.

### 2. Rewire `buildSandboxKpts` (~line 1995)

Currently `buildSandboxKpts` dispatches to either raw captured kpts (no deltas active) or `computePerSidePose` (deltas active). Change it:

```
if (!_balanceLocked) {
    // Before balance: show raw captured skeleton (existing behavior)
    return raw captured kpts from fd;
} else {
    // After balance: rebuild from parameters using the new FK function
    return buildCorrectedPose(fd);
}
```

This means: before the user clicks Balance, they see their actual captured skeleton. After Balance, they see the corrected skeleton that rebuilds every frame from current slider values.

### 3. Auto-re-solve trunk lean every frame

Since `buildCorrectedPose` computes trunk lean analytically as part of its FK chain, and `buildSandboxKpts` is called every frame by the animation loop, the trunk lean automatically re-solves whenever any slider changes. No separate re-solve step needed.

Update `_balanceLeanOffsetDeg` inside `buildCorrectedPose` so other code that reads it (like the status display) stays consistent:
```
_balanceLeanOffsetDeg = trunkLeanDeg;  // update the global for status display
```

### 4. Store the locked balance target

When the user clicks Balance, store the COM target point so it persists across parameter changes:

```javascript
let _balanceTargetX = 0;  // set when balance is locked
let _balanceTargetZ = 0;
```

In `balanceSandbox()` (~line 1514), after the initial solve succeeds, save:
```javascript
const basePose = buildSandboxKpts(frameData);
const target = computeBalanceTargetGround(basePose.kpts, FOOT_LEN_M);
_balanceTargetX = target.x;
_balanceTargetZ = target.z;
```

Then `buildCorrectedPose` uses `_balanceTargetX` as its target, not recomputing the target from the (now-moved) ankle positions.

**Wait — actually this needs thought.** When stance width changes, the ankles move, which moves the mid-foot point. The balance target SHOULD move with the feet — you always want COM over mid-foot, regardless of where the feet are. So `buildCorrectedPose` should recompute `balanceTargetX` from the new ankle positions:

```javascript
const balanceTargetX = balancePointAlongFoot(FOOT_LEN_M) * Math.cos(toeOutRad);
```

This is what `computeSquatPose` does at ~line 1765. The balance target is always "35% along the foot from heel" — it's relative to the feet, not an absolute world position.

### 5. Replace the Sandbox Panel HTML

**Current sandbox panel** is at ~line 920-1008. Replace its contents.

**Remove these sections** (element IDs to delete):
- Body Proportions section: sliders `sb-body-scale`, `sb-torso-ratio`, `sb-thigh-ratio`, `sb-shin-ratio`, `sb-shoulder-width-ratio`, `sb-foot-ratio`
- Knee Flexion delta section: slider `sb-d-knee-flex`
- Per-side dorsiflexion: sliders `sb-d-dorsi-l`, `sb-d-dorsi-r` (keep the bilateral `sb-d-dorsi`)
- Trunk Lean delta section: slider `sb-d-forward-lean`
- Knee Valgus section: sliders `sb-d-valgus`, `sb-d-valgus-l`, `sb-d-valgus-r`
- Chain Solver section: radio buttons `sb-solver-mode`, `sb-ankle-override`, `sb-compensated-controls`
- Threshold bars: `sb-lean-threshold-bar`, `sb-valgus-threshold-bar`

**Keep these sections**:
- Balance section (with updated text)
- Stance section: sliders `sb-stance-width`, `sb-toe-out` (already exist)
- Barbell section: sliders `sb-barbell-weight`, `sb-body-mass` (already exist)
- Bilateral dorsiflexion: slider `sb-d-dorsi` (already exists)
- Playback section: scrubber, play/pause, speed (already exist)
- Live Angles section: `sb-angles-info` (already exists)

**New elements to add**:

1. **Depth check readout** — at the top of sandbox panel, before the Balance section:
```html
<div class="section">
    <div class="section-title"><span class="dot"></span> Depth Check</div>
    <div class="mono" id="sb-depth-check"></div>
</div>
```
Populate on sandbox tab activation:
```javascript
const depthAngle = baselineData.peakKneeFlex;
const depthOk = depthAngle >= 90;
document.getElementById('sb-depth-check').innerHTML = depthOk
    ? `<span class="balance-ok">Depth: ${depthAngle.toFixed(1)}° — below parallel ✓</span>`
    : `<span class="balance-bad">Depth: ${depthAngle.toFixed(1)}° — parallel is ~90°</span>`;
```

2. **Trunk lean live readout** — below the parameter sliders:
```html
<div class="section">
    <div class="section-title"><span class="dot"></span> Trunk Lean</div>
    <div class="mono" id="sb-trunk-lean-status"></div>
</div>
```
Update this in `updateSandbox` when `_balanceLocked`:
```javascript
const trunkLeanOffset = 180 - trunkAngleDeg;  // degrees from vertical
const leanSeverity = classifyLean(trunkAngleDeg);  // uses existing LEAN_T thresholds
const leanClass = leanSeverity === 'none' ? 'balance-ok' : 'balance-bad';
document.getElementById('sb-trunk-lean-status').innerHTML =
    `<span class="${leanClass}">Trunk lean: ${trunkLeanOffset.toFixed(1)}°</span> ${leanSeverity !== 'none' ? sb(leanSeverity) : '✓'}`;
```

### 6. Update `SB_PARAM_IDS` and slider bindings

The `SB_PARAM_IDS` array (~line 1239) controls which sliders get enabled/disabled when balance is locked. Update it to only include the kept sliders:

```javascript
const SB_PARAM_IDS = [
    'sb-stance-width', 'sb-toe-out',
    'sb-barbell-weight', 'sb-body-mass',
    'sb-d-dorsi',
];
```

Remove the slider binding calls for deleted sliders (~lines 1287-1299). Keep:
- `bindStanceSlider('sb-stance-width', ...)` 
- `bindStanceSlider('sb-toe-out', ...)`
- `bindSliderDelta('sb-d-dorsi', ...)`
- `bindDisplaySlider('sb-barbell-weight', ...)`
- `bindDisplaySlider('sb-body-mass', ...)`
- `bindDisplaySlider('sb-speed-slider', ...)`

### 7. Update `getSandboxBodyParams` and `getSandboxDeltas`

`getSandboxBodyParams` (~line 1814): simplify to only read what's needed:
```javascript
function getSandboxBodyParams() {{
    return {{
        bodyScale: AP ? AP.bodyScale : 1.0,
        torsoRatio: AP ? AP.torsoRatio : 1.0,
        thighRatio: AP ? AP.thighRatio : 1.0,
        shinRatio: AP ? AP.shinRatio : 1.0,
        shoulderWidthRatio: AP ? (AP.shoulderWidthRatio || 1.0) : 1.0,
        footRatio: AP ? (AP.footRatio || 1.0) : 1.0,
        stanceWidth: _sv('sb-stance-width'),
        toeOut: _sv('sb-toe-out'),
    }};
}}
```

`getSandboxDeltas` (~line 1827): simplify to only dorsi:
```javascript
function getSandboxDeltas() {{
    return {{
        dorsi: _sv('sb-d-dorsi'),
    }};
}}
```

### 8. Clean up dead code

After removing the sandbox UI elements and simplifying the functions, remove:
- `getSbSolverMode()` and the solver mode event listener (~line 2299-2307)
- Ankle override slider binding (~line 2308-2313)
- `ConstrainedChainSolver` class (~line 2053-2134) — its `_solveTrunkFromCOM` math should be inlined in `buildCorrectedPose`; the class itself is no longer needed
- `getOptimalCached()` and `_cachedOptimal` / `_lastOptKey` (~line 2259-2278) — the ghost torso feature relied on this; it's replaced by the live trunk lean readout
- `updateGhostTorso()` (~line 2248-2257) — no longer needed since the corrected skeleton IS the visualization
- References to deleted sliders in `sliderInit` (~line 1076-1093)

### 9. What NOT to touch

- **Replay mode** — completely untouched. `updateReplay()` (~line 1643), replay panel HTML, replay controls.
- **`computeCOM()`** (~line 2138) — already correct, used as-is
- **`computeBOS()`** (~line 2159) — already correct
- **`isBalanced()`** (~line 2196) — already correct
- **`computeBalanceTargetGround()`** (~line 1594) — already correct
- **`balancePointAlongFoot()`** (~line 1590) — already correct
- **COM/BOS visual elements and update functions** — `updateCOMVisuals()`, `updateBalanceTargetVisual()`, all Three.js visual objects (comSphere, comDisc, bosLine, midfootLine, etc.)
- **`computeSquatPose()`** (~line 1696) — keep as reference, still used for ghost torso in replay mode
- **`computePerSidePose()`** (~line 1840) — keep in code, just no longer called from `buildSandboxKpts` when balance is locked
- **Fault classification** (`classifyLean`, `classifyValgus`) — still used
- **Skeleton rendering** in `updateSandbox` (joint meshes `jm[]`, bone meshes `bm[]`) — untouched
- **Mode switching** event listeners (~line 1564-1581) — keep as-is
- **All Python code** outside the HTML template string — untouched

## Coordinate System Details

- **Y-axis**: upward. Ankle Y = 0 is ground level.
- **X-axis**: forward (in front of the person, toward camera)
- **Z-axis**: lateral. Left ankle has negative Z, right ankle has positive Z.
- **Trunk lean**: angle from vertical in radians. 0 = perfectly upright. Positive = leaning forward (increasing X).
- **Dorsiflexion**: angle of shin from vertical. 0 = shin is vertical. Positive = shin tilted forward.
- **Knee flexion**: 0 = legs fully extended. ~90° = thighs parallel to ground. Higher = deeper squat.
- **Toe-out**: angle of foot direction from forward (X-axis). Left foot toes point toward negative Z, right foot toward positive Z.
- **`trunk_flexion` convention**: 180° = fully upright. To get "degrees of lean from vertical": `180 - trunk_flexion`.
- All slider values are in degrees. Convert to radians for trig (`* Math.PI / 180`).

## Testing

Generate HTML from a session file:
```bash
python scripts/visualize_video_squats.py --refit
```
This uses the last saved session and produces an HTML file in `recordings/`.

**Verify these behaviors in order:**

1. **Replay mode unchanged** — switching to Replay tab shows captured skeleton with scrubber, angles, faults. No regressions.

2. **Sandbox entry** — clicking Sandbox tab shows depth check readout populated from baseline data. Sliders are disabled. Balance button is visible.

3. **Depth check accuracy** — the displayed knee angle matches `baselineData.peakKneeFlex`. Color is green if ≥90°, amber if <90°.

4. **Balance solve** — clicking Balance: status shows "Balanced" with trunk lean angle. Sliders become enabled. Skeleton may visually adjust (trunk lean changes to center COM).

5. **Stance width slider** — drag wider → trunk angle becomes more upright (trunk lean degrees decrease). The skeleton's feet visibly move apart. COM sphere stays on mid-foot target.

6. **Toe-out slider** — increase → trunk angle becomes more upright. Feet visually rotate outward. COM stays on target.

7. **Dorsiflexion slider** — increase → trunk angle becomes more upright (more ankle range = less compensation needed). Shins tilt further forward. COM stays on target.

8. **Combined effect** — set stance width to 2.0x, toe-out to 30°, dorsi +10° → trunk should be notably more upright than original. This is the key demo: "here's what your squat looks like with a wider, toed-out stance and better ankle mobility."

9. **Trunk lean readout** — updates in real-time as sliders move. Shows severity classification (none/mild/moderate/severe) using `LEAN_T` thresholds.

10. **COM visualization** — red sphere (COM) stays over green/orange mid-foot line as parameters change. BOS polygon adjusts as feet move.

11. **Frame scrubbing** — while balance is locked, scrubbing to different frames should show the corrected skeleton at each frame's knee angle, not the captured skeleton.

## Constraints

- Keep it simple. This is an MVP. No undo, no save, no presets, no reset button.
- Don't add error handling for impossible scenarios (e.g., asin argument > 1 is ok to clamp).
- Match existing code style (2-space indent in JS, camelCase variables, etc.).
- Every changed line should trace directly to this feature. Don't refactor adjacent code.
- Use explicit variable names in the FK math (e.g., `shinForwardComponent` not `sf`, `thighDirectionAngle` not `tda`).
- Don't add comments explaining what code does — the variable names should make it clear.

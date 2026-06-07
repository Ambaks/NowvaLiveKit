# Task: Fix Parameter Mismatch Between Real Video Replay and Synthetic Sandbox Visualizer

## Context

We have two visualizers:
1. **Real video replay** (`scripts/visualize_video_squats.py`) — captures webcam squats, runs the full biomechanics pipeline (MediaPipe pose estimation → pre-IK filters → AnalyticalIKSolver → angle filtering), extracts 3D skeleton data per frame, and generates a self-contained HTML replay with a Three.js stick figure.
2. **Synthetic sandbox** (`fault_visualizer.html`) — a parametric FK (forward kinematics) model that generates a COCO-17 stick figure from slider parameters. The user can adjust body proportions, stance, depth, faults, etc.

The replay HTML has an **"Open in Sandbox"** button that passes the athlete's reverse-computed parameters (body proportions, stance width, toe-out, dorsiflexion ratio, forward lean, valgus, arm ratio) to `fault_visualizer.html` via URL query params. The sandbox reads these params and pre-sets its sliders.

**The problem**: When the sandbox opens with the athlete's extracted params, the resulting stick figure does NOT match the real video replay. The proportions, dorsiflexion, and arm positioning are visibly wrong. The goal is to make the sandbox produce a stick figure that closely replicates what the real data shows.

## Issue 1: Dorsiflexion Ratio Mismatch (Critical)

### How the synthetic model uses dorsiRatio
File: `fault_visualizer.html`, line ~867
```javascript
const ankleDF = dorsiRatio * kneeFlexRad;  // kneeFlexRad is knee flexion in RADIANS
```
- `dorsiRatio` is a unitless coupling factor: "for every radian of knee bend, how many radians of ankle dorsiflexion?"
- Slider range: 0.00 to 0.40, default 0.15
- At 90° knee flex (1.57 rad) with dorsiRatio=0.15: ankleDF = 0.24 rad ≈ 13.5°

### How the real pipeline computes ankle dorsiflexion
File: `src/biomechanics/kinematics/analytical_ik.py`
- The IK solver computes `ankle_dorsiflexion_l/r` as the **shank angle from vertical**, scaled by 0.5
- This is an absolute angle measurement of how much the shin tilts forward, NOT a foot-relative ankle angle
- It's measured in degrees

### How the capture script computes dorsiRatio
File: `scripts/visualize_video_squats.py`, in `compute_athlete_params()`
```python
peak_dorsi_ratio = avg_dorsi_degrees / max_knee_degrees
```
- Both values are in degrees, so the ratio is dimensionless (degrees/degrees)
- A real athlete got dorsiRatio=0.53, which exceeds the slider max of 0.40

### Why they don't match
The synthetic model's dorsiRatio is a **parametric coupling in radians**: `ankleDF_rad = dorsiRatio * kneeFlexion_rad`. The real data computes a **degree-space ratio** of two independently-measured angles (shank tilt vs knee flexion). These are fundamentally different quantities that happen to share a name.

Additionally, the IK solver's "dorsiflexion" includes forward shank lean that isn't purely ankle dorsiflexion — it conflates shin tilt with actual ankle mobility.

### What needs to happen
Either:
- (A) Change the `compute_athlete_params()` extraction to produce a value compatible with the synthetic model's formula. Since the synthetic model does `ankleDF_rad = dorsiRatio * kneeFlexRad`, we need to find the dorsiRatio that, when plugged into that formula, produces the same ankle angle the real data shows. This means: `dorsiRatio = ankleDF_rad / kneeFlexRad = ankleDF_deg / kneeFlexDeg` — which is what we already compute. So the issue is that the slider max (0.40) is too low for real data, OR
- (B) Increase the slider max to accommodate real-world values (e.g., 0.60), OR
- (C) Re-examine whether the IK solver's dorsiflexion measurement is inflated (the `* 0.5` scale factor may not be enough), and fix the IK if so, OR
- (D) Compute dorsiRatio differently — e.g., use the actual ankle joint angle from the 3D skeleton (ankle-knee vector vs ankle-foot_index vector) instead of the shank-from-vertical approximation

## Issue 2: Arm Proportions Don't Match (Visible)

### How the synthetic model positions arms
File: `fault_visualizer.html`, lines ~881, ~1044-1056
```javascript
const ual = REF.upper_arm * bodyScale * armRatio;  // 0.30 * scale * ratio
const fal = REF.forearm * bodyScale * armRatio;     // 0.26 * scale * ratio
```
Arm positioning is **procedural/hardcoded** — arms follow trunk lean with fixed offsets:
```javascript
const armForwardAngle = totalTrunkLean + 1.2;
elbowFwdX = ual * Math.sin(armForwardAngle);
elbowFwdY = -ual * Math.sin(0.3);
// Wrists: fixed fractions of forearm length
set(9,  lElbow[0] + fal * 0.15, lElbow[1] - fal * 0.3, lElbow[2]);
```

### How the real data captures arms
- MediaPipe provides actual 3D world coordinates for shoulder, elbow, wrist
- The IK solver computes shoulder flexion (angle between trunk and upper arm) and elbow flexion
- Bone lengths are calibrated from the real skeleton (upper_arm_l/r, forearm_l/r)
- The `armRatio` extraction averages `(upper_arm_avg/0.30 + forearm_avg/0.26) / 2 / bodyScale`

### Why they don't match
1. **Single armRatio scales both segments equally**, but real athletes often have different upper_arm:forearm proportions than the 0.30:0.26 (1.15:1) ratio in REF. If someone has relatively shorter forearms, `armRatio` can't capture that — it averages the two.
2. **Arm POSITIONING is hardcoded** in the synthetic model. It doesn't use shoulder flexion or elbow flexion angles from the real data. A person holding arms forward for balance vs. arms at sides will look completely different in the replay but identical in the sandbox.
3. The `+ 1.2` constant in `armForwardAngle = totalTrunkLean + 1.2` may not match the athlete's actual arm position.

### What needs to happen
Either:
- (A) Pass actual shoulder flexion and elbow flexion angles from the real data to the sandbox, and use them to position the arms instead of the hardcoded offsets, OR
- (B) Split `armRatio` into `upperArmRatio` and `forearmRatio` so proportions are independently controlled, OR
- (C) At minimum, extract the arm angles at peak depth from the real data and pass them as additional URL params that the sandbox can use for arm positioning

## Issue 3: General Proportion Alignment

### bodyScale computation
The current formula:
```python
body_scale = mean(torso/0.50, femur/0.42, tibia/0.40)
```
Then individual ratios are normalized: `torsoRatio = (torso/0.50) / bodyScale`

This should be correct in theory, but verify that the synthetic model applies them the same way:
```javascript
const tl = REF.torso_len * bodyScale * torsoRatio;  // should equal real torso length
```

### Shoulder width
The synthetic model has `REF.shoulder_width = 0.36` but this is NOT exposed as a slider. The real athlete's shoulder width is measured but never passed to the sandbox. If the athlete has wider/narrower shoulders than 0.36m (scaled), the stick figures won't match.

## Files to Modify

- `scripts/visualize_video_squats.py` — `compute_athlete_params()` function and `build_html()` template
- `fault_visualizer.html` — `computeSquatPose()` FK function, `applyURLParams()`, and possibly add new sliders or override logic
- Possibly `src/biomechanics/kinematics/analytical_ik.py` — if dorsiflexion computation needs fixing

## Key Reference: Synthetic FK Function Signature
File: `fault_visualizer.html`, line ~851
```javascript
function computeSquatPose(phase, {
    maxKneeFlex, forwardLean, kneeValgus,
    bodyScale, torsoRatio, thighRatio, shinRatio, armRatio,
    stanceWidth, toeOut, dorsiRatio,
    barbellWeight, bodyMass,
})
```

## Key Reference: REF Proportions
```javascript
const REF = {
    hip_width: 0.22, thigh_len: 0.42, shin_len: 0.40,
    torso_len: 0.50, shoulder_width: 0.36,
    upper_arm: 0.30, forearm: 0.26,
    head_offset: 0.22, neck_len: 0.10, foot_len: 0.26,
};
```

## Success Criteria
When the user clicks "Open in Sandbox" from the replay HTML:
1. The synthetic stick figure's body proportions (torso, legs, arms) should visually match the replay stick figure at the same squat depth
2. The ankle dorsiflexion (shin tilt) should look the same at peak depth
3. The arm lengths and positioning should be recognizably similar
4. All slider values should be within their valid ranges (no clamping/overflow)

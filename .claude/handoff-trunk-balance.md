# Task: Replace Independent Trunk Lean Correction with COM-Balance Solver

## What's wrong now

In `src/biomechanics/diagnosis/keypoint_corrector.py`, the six corrections in `correct()` are independent patches. Each reads a `parameter_delta` from the diagnosis and applies a blind offset. They don't talk to each other. The result is a "corrected" skeleton that is geometrically valid (bone lengths preserved) but **not physically balanced** — the center of mass can be way off the base of support.

The worst offender is `_reduce_trunk_lean()` (line 216-246). It reads `trunk.rx` from `delta_brace_trunk()` in `parameter_deltas.py`, which computes a correction of `min(excess_lean * 0.4, 8°)`. This is arbitrary — the trunk lean in a squat is not a free parameter. It's **determined by physics**: the trunk must lean forward exactly enough to keep center of mass over the base of support (midfoot). The current code corrects "40% of excess lean, max 8°" which has no biomechanical basis.

Similarly, `_center_weight()` (line 204-214) shifts the pelvis laterally by a fixed fraction of hip asymmetry. It should shift to center COM laterally.

## What needs to change

Replace `_reduce_trunk_lean()` with `_balance_trunk()` — a method that **solves** for the trunk lean angle that places the whole-body center of mass over the ankle midpoint, clamped at 40°. This runs **unconditionally** after all lower-body corrections (like `_enforce_bone_lengths` does), not gated by whether `bracing_failure` was detected. Any lower-body correction (wider stance, deeper squat, knees out) changes the COM — the trunk must always rebalance.

## Coordinate system in the corrector

- **X** = sagittal (forward/backward). Trunk lean is measured in X-Y plane.
- **Y** = vertical, positive UP. `kpts[idx][1] -= drop` lowers a joint.
- **Z** = lateral (left/right). Stance widening moves ankles in X (see `__foot_target_delta`), but `_center_weight` shifts in Z.

Note: `_reduce_trunk_lean` already works in X-Y for lean. The new `_balance_trunk` should use the same convention.

## The COM balance model

Three-segment sagittal-plane model. Mass fractions from De Leva (1996), feet excluded (on the ground, part of base of support), renormalized:

```
SHANK_MASS_FRAC = 0.09    # both shanks combined
THIGH_MASS_FRAC = 0.29    # both thighs combined
UPPER_BODY_MASS_FRAC = 0.62  # trunk + head + arms
```

Segment center-of-mass positions (fraction from proximal joint toward distal):

```
SHANK_COM_FRAC = 0.433    # from knee toward ankle
THIGH_COM_FRAC = 0.433    # from hip toward knee
UPPER_COM_FRAC = 0.50     # from hip toward shoulder
```

### Balance equation (sagittal plane, X axis)

The goal: total COM in X equals the balance target (ankle midpoint X):

```
target_x = ankle_mid_x

shank_com_x = mean of (knee_x + 0.433 * (ankle_x - knee_x)) for both legs
thigh_com_x = mean of (hip_x + 0.433 * (knee_x - hip_x)) for both legs
upper_com_x = hip_mid_x + UPPER_COM_FRAC * torso_length * sin(θ)

Balance:
target_x = SHANK_MASS_FRAC * shank_com_x
         + THIGH_MASS_FRAC * thigh_com_x
         + UPPER_BODY_MASS_FRAC * upper_com_x
```

Solving for θ (trunk lean from vertical):

```
sin(θ) = (target_x - SHANK * shank_com_x - THIGH * thigh_com_x - UPPER * hip_mid_x)
         / (UPPER_BODY_MASS_FRAC * UPPER_COM_FRAC * torso_length)

θ = asin(clamp(sin_value, -1.0, 1.0))
θ = clamp(θ, 0.0, MAX_TRUNK_LEAN_RAD)
```

Where `MAX_TRUNK_LEAN_RAD = math.radians(40.0)`.

Then reposition upper body keypoints:
```
new_shoulder_x = hip_mid_x + torso_length * sin(θ)
new_shoulder_y = hip_mid_y + torso_length * cos(θ)
offset_x = new_shoulder_x - current_shoulder_x
offset_y = new_shoulder_y - current_shoulder_y

Translate all UPPER_BODY_INDICES by (offset_x, offset_y, 0)
```

This is the same translation approach used by the current `_reduce_trunk_lean` (lines 244-246) — it pivots the upper body about the hip midpoint by translating all upper body keypoints uniformly.

## Implementation steps

### Step 1: Add constants at module level in `keypoint_corrector.py`

After the existing keypoint index constants (after line 27), add:

```python
MAX_TRUNK_LEAN_DEG = 40.0

SHANK_MASS_FRAC = 0.09
THIGH_MASS_FRAC = 0.29
UPPER_BODY_MASS_FRAC = 0.62
SHANK_COM_FRAC = 0.433
THIGH_COM_FRAC = 0.433
UPPER_COM_FRAC = 0.50
```

### Step 2: Replace `_reduce_trunk_lean` with `_balance_trunk`

Delete `_reduce_trunk_lean()` (lines 216-246). Replace with:

```python
def _balance_trunk(self, kpts: np.ndarray) -> None:
```

No `cause` parameter — this method doesn't read from a diagnosis delta. It computes the balanced lean angle from the current lower-body keypoint positions.

Implementation:
1. Compute `hip_mid`, `shoulder_mid`, `ankle_mid` from kpts
2. Measure `torso_length` from `hip_mid` to `shoulder_mid` (2D: X-Y plane, same as old code)
3. Guard: if `torso_length < 1e-6`, return
4. Compute `shank_com_x` (average of left and right)
5. Compute `thigh_com_x` (average of left and right)
6. Compute `target_x = ankle_mid_x` (balance over ankle midpoint)
7. Solve for `sin(θ)` using the balance equation above
8. Clamp `sin(θ)` to [-1, 1], compute `θ = asin(...)`
9. Clamp `θ` to `[0, MAX_TRUNK_LEAN_RAD]` (no backward lean, max 40° forward)
10. Compute new shoulder midpoint position from `θ`
11. Translate all `UPPER_BODY_INDICES` by the offset

### Step 3: Update `correct()` method

**Remove** the cause-gated `bracing_failure` block (current lines 132-133):
```python
# DELETE these lines:
if "bracing_failure" in tier1_causes:
    self._reduce_trunk_lean(kpts, tier1_causes["bracing_failure"])
```

**Add** `_balance_trunk()` as an always-run step. The new correction order in `correct()`:

```python
# --- Lower body corrections (cause-gated) ---
if "narrow_stance" in tier1_causes:
    self._widen_stance(kpts, tier1_causes["narrow_stance"])

if "narrow_foot_angle" in tier1_causes:
    self._increase_toe_out(kpts, tier1_causes["narrow_foot_angle"])

if "depth_cue_unfamiliar" in tier1_causes:
    self._lower_to_depth(
        kpts, tier1_causes["depth_cue_unfamiliar"],
        original_thigh_l, original_shin_l,
        original_thigh_r, original_shin_r,
    )

if "knee_track_cue" in tier1_causes:
    self._push_knees_out(kpts, tier1_causes["knee_track_cue"])

if "weight_shift_cue" in tier1_causes:
    self._center_weight(kpts, tier1_causes["weight_shift_cue"])

# --- Enforcement passes (always run) ---
self._enforce_bone_lengths(
    kpts, original_thigh_l, original_shin_l,
    original_thigh_r, original_shin_r,
)

max_dorsi_deg = rom.get("dorsiflexion_drop") if rom else None
if max_dorsi_deg is not None:
    self._enforce_dorsi_cap(
        kpts, max_dorsi_deg,
        original_thigh_l, original_shin_l,
        original_thigh_r, original_shin_r,
    )

self._balance_trunk(kpts)

self._reground(kpts)
```

`_balance_trunk` runs after `_enforce_dorsi_cap` because the dorsi cap may raise hips, which changes the lower-body COM and therefore the trunk lean needed for balance.

### Step 4: Do NOT change `delta_brace_trunk` in `parameter_deltas.py`

`delta_brace_trunk()` (line 96-106) still exists and still returns `{"trunk.rx": ...}`. It's used by the diagnosis engine for the `bracing_failure` hypothesis and its explanation template. The corrector simply no longer reads that delta — the lean is computed from physics instead. Don't delete the function, don't modify it.

### Step 5: Do NOT change `_center_weight`

Leave `_center_weight()` as-is. It handles lateral (Z-axis) balance and is independent of the sagittal-plane COM solve. It stays cause-gated by `weight_shift_cue`.

## Files to touch

- `src/biomechanics/diagnosis/keypoint_corrector.py` — add constants, replace `_reduce_trunk_lean` with `_balance_trunk`, update `correct()` method order

## Files NOT to touch

- `src/biomechanics/diagnosis/graph/parameter_deltas.py` — `delta_brace_trunk` stays as-is
- `src/biomechanics/diagnosis/graph/causes.yaml` — cause graph stays as-is
- `src/biomechanics/diagnosis/engine.py` — hypothesis engine stays as-is
- `src/biomechanics/diagnosis/bridge.py` — no changes
- `scripts/visualize_video_squats.py` — no changes
- Any JS/HTML viewer files — don't touch

## Edge cases

1. **Required lean is negative** (COM already forward of ankles without any trunk lean): clamp θ to 0. Don't lean backward.
2. **Required lean exceeds 40°** (very deep squat with long femurs): clamp to 40°. The ghost shows the best achievable pose even if imperfect balance.
3. **Torso length near zero** (degenerate skeleton): return early, no trunk adjustment.
4. **sin(θ) outside [-1, 1]** (COM so far from ankles that no lean angle can balance): clamp before asin. Will hit the 40° cap.
5. **No lower-body corrections applied** (e.g., only `knee_track_cue` triggered): `_balance_trunk` still runs and adjusts trunk to balance the modified skeleton. If nothing moved, the balanced angle ≈ current angle and the offset ≈ 0.

## Test

1. `pytest tests/test_biomechanics/test_diagnosis/ -x` — existing tests pass
2. Run `python scripts/visualize_video_squats.py` on a test video
3. In the HTML viewer:
   - Ghost skeleton should look physically plausible (not falling over)
   - Trunk lean should be visually reasonable for the squat depth shown
   - If depth correction fires, the deeper ghost should have more forward lean (but ≤ 40°)
   - If only stance is widened (no depth change), trunk lean should stay roughly the same

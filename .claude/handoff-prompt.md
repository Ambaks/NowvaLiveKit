# Task: Fix Ghost Skeleton Depth Geometry — Surgical Changes Only

## What happened
A previous session went overboard. It was asked to fix the depth calculation in the ghost skeleton system but instead:
- Replaced the entire `KeypointCorrector` flow with a from-scratch FK skeleton builder (`fk_ghost.py`)
- Removed the morph animation (play/pause pulsing between observed and corrected)
- Built head/arms from hardcoded offsets instead of the observed keypoints
- Changed the JS viewer HTML (removed play button, renamed section, added ghost params div)
- Set `morph_frames: None` and `has_correction: True` for all reps unconditionally

**None of those changes should have been made.** The only thing that needed fixing was the depth geometry inside `KeypointCorrector._enforce_dorsi_cap()` and related depth functions.

## The two actual bugs to fix

### Bug 1: Dorsiflexion uses proportional ratio instead of absolute cap

In `src/biomechanics/diagnosis/keypoint_corrector.py`, the method `_enforce_dorsi_cap()` (line 312-349) computes:
```python
cap = dorsi_ratio * knee_flex_rad   # WRONG — proportional coupling
excess = dorsi_rad - cap
```

This means the dorsiflexion limit scales with knee flexion. At 90° knee flex with dorsi_ratio=0.15, the cap is only 13.5°. At 120° it's 18°. This is wrong — the athlete's max dorsiflexion from calibration (`peakDorsi`, stored as `dorsiflexion_drop` in the ROM dict) is an absolute ceiling.

**Fix**: Change `_enforce_dorsi_cap` to use `rom["dorsiflexion_drop"]` as an absolute cap in degrees, not `dorsi_ratio * knee_flexion`. The cap should be: `if dorsiflexion_angle > max_dorsi_deg, raise hips to reduce shin tilt`.

### Bug 2: Stance width has zero effect on achievable depth

The current ghost builds each leg in a 2D sagittal plane. When you widen the stance, the ankles move laterally but the hips are forced to `±hip_width/2`. The femur geometry is computed purely in the sagittal plane (X-Y), so the lateral offset between hip socket and knee is ignored. Wider stance = ankles further apart but zero change in achievable hip height.

**The 3D geometry that's missing**: When stance is wider than hip width, the knee sits laterally outside the hip socket. The femur must bridge that gap, which "uses up" femur length laterally:

```
delta_z = |hip_z - knee_z|    (lateral gap between hip socket and knee)
effective_femur_sagittal = sqrt(thigh_length² - delta_z²)
```

A shorter effective femur in the sagittal plane means the hip sits closer to the knee at the same dorsiflexion → less forward lean needed → deeper squat achievable with the same trunk lean budget.

**Fix**: In `_lower_to_depth()` (line 244-287), when computing the IK for the lowered position, account for the lateral femur component. The `solve_knee()` function already works in 3D, so this may partially handle it. But the iterative hip-lowering loop just drops hips straight down without considering whether wider stance allows deeper descent. The fix should make `_lower_to_depth` aware that wider stance → more depth headroom.

## What needs to happen

### Step 1: Revert ALL changes to `scripts/visualize_video_squats.py`
Run `git checkout HEAD -- scripts/visualize_video_squats.py` to restore the original working viewer. The original code already has:
- `KeypointCorrector` + `build_morph_frames` flow
- Play/pause morph animation
- "Correction Preview" section with proper HTML
- Per-rep correction based on diagnosis causes

### Step 2: Revert ALL changes to `src/biomechanics/diagnosis/__init__.py`
Run `git checkout HEAD -- src/biomechanics/diagnosis/__init__.py`

### Step 3: Pass `anthro` and `rom` to `corrector.correct()` in `run_diagnosis()`
The original call was: `corrected_kpts = corrector.correct(observed_kpts, set_diagnosis)`
But `correct()` accepts optional `anthro` and `rom` params that enable `_enforce_dorsi_cap()`.

Change to: `corrected_kpts = corrector.correct(observed_kpts, set_diagnosis, anthro=set_features.anthropometry, rom=set_features.rom)`

### Step 4: Fix `_enforce_dorsi_cap()` in `keypoint_corrector.py`
Currently at line 312-349. Change from:
```python
def _enforce_dorsi_cap(self, kpts, dorsi_ratio, thigh_l, shin_l, thigh_r, shin_r):
    ...
    cap = dorsi_ratio * knee_flex_rad    # proportional — WRONG
    excess = dorsi_rad - cap
```

To use absolute dorsiflexion from ROM:
```python
def _enforce_dorsi_cap(self, kpts, max_dorsi_deg, thigh_l, shin_l, thigh_r, shin_r):
    max_dorsi_rad = math.radians(max_dorsi_deg)
    ...
    # For each leg:
    dorsi_rad = self._compute_dorsiflexion(kpts[knee_idx], kpts[ankle_idx])
    excess = dorsi_rad - max_dorsi_rad    # absolute cap
```

Update the caller in `correct()` (line 136-142) to pass `rom["dorsiflexion_drop"]` instead of `rom["dorsi_ratio"]`:
```python
max_dorsi_deg = rom.get("dorsiflexion_drop") if rom else None
if max_dorsi_deg is not None:
    self._enforce_dorsi_cap(kpts, max_dorsi_deg, ...)
```

### Step 5: Fix `_lower_to_depth()` to account for 3D femur geometry
The current method (line 244-287) iteratively drops hips and re-solves knees via IK. The `solve_knee()` IK already works in 3D, so widening stance should naturally allow deeper descent through the IK solver.

However, the stopping condition (`hip_mid_y <= knee_mid_y`) doesn't account for the fact that with wider stance, the effective femur in sagittal plane is shorter, meaning the hip CAN sit lower relative to the knee.

The key insight: `solve_knee()` already handles the 3D constraint correctly — if the hip-to-ankle distance is shorter (because ankle is wider), the knee bends more, allowing the hip to drop further. So the 5-iteration loop with `drop = hip_mid_y - knee_mid_y + 0.01` should work IF the ankles have already been widened by `_widen_stance()` before `_lower_to_depth()` runs.

**Check**: Verify the correction order in `correct()`. Currently:
1. `_widen_stance` ← ankles move wider
2. `_increase_toe_out` ← feet rotate
3. `_lower_to_depth` ← hips drop (should benefit from wider ankles)
4. `_push_knees_out`
5. `_center_weight`
6. `_reduce_trunk_lean`
7. `_enforce_bone_lengths`
8. `_enforce_dorsi_cap`

This order means wider stance IS applied before depth lowering. The IK solver should naturally handle the 3D constraint. **Test this first** — the 3D femur issue may already be handled by `solve_knee()` once stance is widened. If it is, Bug 2 may not need a separate fix.

### Step 6: Keep `bridge.py` changes (just the `foot_length` addition)
The addition of `"foot_length": athlete_params.get("foot_avg_m", 0.26)` to `build_anthro_dict()` is fine — it's additive and doesn't break anything.

### Step 7: Keep or delete `fk_ghost.py` and its tests
The `fk_ghost.py` module has correct 3D geometry math that could be useful later, but it's not needed for this fix. Your call — either:
- Delete `src/biomechanics/diagnosis/fk_ghost.py` and `tests/test_biomechanics/test_diagnosis/test_fk_ghost.py`
- Or keep them as reference but don't import/use them

### Step 8: Test
1. Run `pytest tests/test_biomechanics/test_diagnosis/ -x` to verify diagnosis tests pass
2. Run `python scripts/visualize_video_squats.py` on a test video
3. Verify in the HTML viewer:
   - Morph animation still works (pulsing between observed and corrected)
   - Ghost is built from observed keypoints (head/arms look normal)
   - When diagnosis finds narrow_stance + depth issues, the ghost shows wider stance AND deeper position
   - Dorsiflexion in the ghost doesn't exceed the athlete's calibrated max

## Files to touch
- `scripts/visualize_video_squats.py` — REVERT to HEAD, then add `anthro=` and `rom=` to the `corrector.correct()` call
- `src/biomechanics/diagnosis/keypoint_corrector.py` — fix `_enforce_dorsi_cap()` to use absolute dorsiflexion
- `src/biomechanics/diagnosis/__init__.py` — REVERT to HEAD
- `src/biomechanics/diagnosis/bridge.py` — keep as-is (foot_length addition is fine)

## Files NOT to touch
- `engine.py`, `causes.yaml`, `evidence_tests.py`, `parameter_deltas.py` — diagnosis logic is correct
- The JS viewer HTML/JS — leave it alone, the original works
- `fk_ghost.py` — don't import or use it in the main flow

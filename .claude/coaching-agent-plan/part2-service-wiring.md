# Part 2: Live Pipeline Diagnosis Bridge ✅ DONE

## Goal
Make the diagnosis engine callable from live pipeline data by adding a key-mapping layer in `bridge.py`. Right now `build_rep_kinematic_summary()` expects the visualizer's frame format — the live pipeline's `JointAngles.as_dict()` and `Skeleton3D.to_numpy()` use different keys and structure. This part bridges that gap.

## The problem
The diagnosis bridge (`src/biomechanics/diagnosis/bridge.py`) expects:
```python
frame = {
    "angles": {"trunk_flexion": ..., "knee_valgus_l": ..., "dorsi_l": ..., "dorsi_r": ..., "knee_flex": ...},
    "kpts": [[x, y, z], ...]  # 19 keypoints (COCO 17 + 2 foot_index)
}
```

The live pipeline produces:
- `JointAngles.as_dict()` with keys like `ankle_dorsiflexion_l`, `ankle_dorsiflexion_r`, `knee_flexion_l`/`knee_flexion_r` (separate L/R, not single `knee_flex`)
- `Skeleton3D.to_numpy().tolist()` — 3D keypoints, but need to verify the coordinate system matches what the bridge expects (vis_x = mp_z, vis_y = -mp_y)

## File to modify

### `src/biomechanics/diagnosis/bridge.py`

Add `build_frame_from_live_pipeline(bottom_kpts: list, bottom_angles: dict) -> dict`:
- Maps `ankle_dorsiflexion_l` → `dorsi_l`, `ankle_dorsiflexion_r` → `dorsi_r`
- Derives `knee_flex` from `max(knee_flexion_l, knee_flexion_r)` (bridge uses a single max value)
- `trunk_flexion`, `knee_valgus_l`, `knee_valgus_r` — pass through (same keys)
- Wraps `bottom_kpts` as `kpts` (verify 19-element array with foot_index keypoints)
- Returns the frame dict that `build_rep_kinematic_summary()` expects

Also verify coordinate system alignment:
- The visualizer uses a specific viewer coordinate system for `compute_foot_direction_angle()` and `compute_stance_width_ratio()` (vis_x = mp_z, pointing away from camera)
- The live pipeline's `Skeleton3D` may use a different convention (check `analytical_ik.py`)
- If they differ, include a coordinate transform in the mapping function

## Verification
- Take a known set of `JointAngles.as_dict()` + `Skeleton3D.to_numpy().tolist()` from a live pipeline run
- Pass through `build_frame_from_live_pipeline()` → `build_rep_kinematic_summary()`
- Check output values are reasonable: trunk_pitch ~160-180° for upright, knee_valgus in single digits, depth_class matches known squat depth
- Compare against visualizer output for the same data if possible

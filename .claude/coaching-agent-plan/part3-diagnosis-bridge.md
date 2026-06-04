# Part 3: Diagnosis Bridge

## Goal
Add a helper function that maps live pipeline IPC data to the frame format the diagnosis engine's `build_rep_kinematic_summary()` expects.

## The problem
The diagnosis bridge (`src/biomechanics/diagnosis/bridge.py`) expects a frame dict with:
```python
{"angles": {"trunk_flexion": ..., "knee_valgus_l": ..., "dorsi_l": ..., "knee_flex": ...}, "kpts": [[x,y,z], ...]}
```

But the live pipeline's `JointAngles.as_dict()` uses different keys:
- `ankle_dorsiflexion_l` → bridge expects `dorsi_l`
- `ankle_dorsiflexion_r` → bridge expects `dorsi_r`
- `knee_flexion_l`/`knee_flexion_r` → bridge expects `knee_flex` (single max value)
- `trunk_flexion` → same key, works as-is
- `knee_valgus_l`/`knee_valgus_r` → same keys, works as-is

## File to modify

### `src/biomechanics/diagnosis/bridge.py`
Add `build_frame_from_ipc(bottom_kpts, bottom_angles) -> dict` that does the key mapping.

Also need to verify the coordinate system matches. The visualizer uses a specific viewer coordinate system (vis_x = mp_z, vis_y = -mp_y). The live pipeline's Skeleton3D may use a different convention. Check `analytical_ik.py` coordinate handling vs what the bridge expects. If they differ, the mapping function needs a coordinate transform too.

## Verification
- Take a known set of JointAngles + Skeleton3D from a live pipeline run
- Pass through `build_frame_from_ipc()` → `build_rep_kinematic_summary()`
- Compare output to what the visualizer produces for the same data
- Key check: trunk_pitch, knee_valgus, depth_class should be reasonable values

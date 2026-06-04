# Part 1: Pipeline Enrichment

## Goal
Send bottom-of-rep keypoints + joint angles with every `rep_complete` IPC message so the voice agent can run the diagnosis engine without needing raw video access.

## What the diagnosis engine needs per rep
- `bottom_kpts`: 19×3 array (COCO 17 + 2 foot_index keypoints) at the deepest point of the rep — this is the Skeleton3D at max knee flexion
- `bottom_angles`: full `JointAngles.as_dict()` at that same frame

## Files to modify

### `src/biomechanics/pipeline.py`
- Track the frame with max `avg_knee_flexion` during each rep
- Buffer `skeleton_3d.to_numpy().tolist()` and `joint_angles.as_dict()` at that frame
- Reset the buffer when a new rep starts (when the rep counter transitions)
- Expose the buffered data so it's available when `rep_data` fires
- Look at lines ~413-490 where rep_data is handled — that's where to capture and attach

### `src/biomechanics/coaching/ipc_bridge.py`
- Modify `send_rep_complete()` to accept optional `bottom_kpts: list | None` and `bottom_angles: dict | None`
- Include them in the IPC message dict when present
- Backward-compatible: existing callers that don't pass them still work

### `src/pose/pose_estimation_process.py`
- After `result.rep_data` fires (line ~494), read the bottom frame from the pipeline
- Pass `bottom_kpts` and `bottom_angles` to `bridge.send_rep_complete()`

## Data size
19 keypoints × 3 floats + ~20 angle values = ~500 bytes per rep. Negligible.

## Verification
- Run the pipeline, do a few squats
- Check IPC messages include `bottom_kpts` and `bottom_angles` fields
- Verify the keypoint array has 19 entries (not 17 — foot_index keypoints must be present)

# IK Fitting Bug — Kinodynamics poses are completely wrong

## The Problem

The IK solver (`src/biomechanics/optimizer/ik.py` → `fit_trajectory`) produces q vectors that, when run back through FK, do NOT match the original captured keypoints. Errors are 100–475mm per joint. The knees end up at ground level, hips are misplaced, and the resulting skeleton looks nothing like the actual squat.

**Replay mode works fine** — it renders the raw captured COCO keypoints directly. The bug is specifically in the IK fitting pipeline that converts those keypoints into 20-DOF q vectors.

This affects:
- The "Kinodynamics" solver mode in `scripts/visualize_video_squats.py` (has never worked correctly)
- The new diagnosis comparison viewer (`src/biomechanics/viewer/`) which consumes q vectors from the same pipeline

## Evidence — diagnostic output from `scripts/debug_fk_roundtrip.py`

Run: `PYTHONPATH=src python scripts/debug_fk_roundtrip.py`

### Rep 2 (shallow squat) — q vector has hip flexion of only -8° despite 91° knee flexion:
```
L_hip.rx = -0.1453 (-8.3deg)    ← should be ~80-100° for this knee angle
L_hip.rz = -0.5236 (-30.0deg)   ← SLAMMED TO BOUND LIMIT
L_knee.rx = +1.5954 (+91.4deg)
L_ankle.rx = +0.0000 (+0.0deg)  ← ALWAYS ZERO, never fitted
trunk.rx = +0.0000 (+0.0deg)    ← ALWAYS ZERO, never fitted

FK L_knee vs target: 361mm error
FK R_knee vs target: 383mm error
```

### Rep 3 (deep squat) — ankles 26cm above ground in FK:
```
L_hip.rx = +2.1660 (+124.1deg)  ← reasonable
L_knee.rx = +2.5805 (+147.9deg) ← reasonable
L_ankle.rx = +0.0000 (+0.0deg)  ← ZERO AGAIN

FK L_ankle Y=0.2653, target Y=0.0000  ← 265mm off!
After grounding, hips go NEGATIVE (below ground plane)
```

### Consistent patterns across ALL reps:
1. **Hip rz (abduction) always at ±30° bound limit** — optimizer hitting the wall
2. **Ankle rx/ry always exactly 0** — dorsiflexion and toe-out DOFs never used
3. **Trunk rx/rz always exactly 0** — trunk flexion never fitted
4. **Pelvis position off by 100-170mm** from target

## Key Files

- `src/biomechanics/optimizer/ik.py` — **THE BUG IS HERE**
  - `_rot3(axis, angle)` — single-axis rotation matrix builder (lines 14-21)
  - `_fk_jac(skeleton, q, descendants)` — FK + analytical Jacobian (lines 40-111)
  - `fit_frame(skeleton, landmarks, ...)` — single-frame L-BFGS-B optimizer (lines 155-279)
  - `fit_trajectory(skeleton, landmarks, ...)` — fits all frames + Gaussian smoothing (lines 282-337)

- `src/biomechanics/skeleton/definition.py` — SkeletonModel, 20-DOF joint tree, bounds
- `src/biomechanics/optimizer/landmark_adapter.py` — converts Skeleton3D → (8,4) landmark array
- `scripts/visualize_video_squats.py` — `_run_refit()` at line 2783 calls `fit_trajectory`
- `scripts/debug_fk_roundtrip.py` — diagnostic script, run it to reproduce

## The 20-DOF Skeleton

```
pelvis (root):  tx, ty, tz, rx, ry, rz  (6 DOF)
trunk:          rx, rz                    (2 DOF, child of pelvis)
L_hip:          rx, ry, rz                (3 DOF, child of pelvis)
R_hip:          rx, ry, rz                (3 DOF, child of pelvis)
L_knee:         rx                        (1 DOF, child of L_hip)
R_knee:         rx                        (1 DOF, child of R_hip)
L_ankle:        rx, ry                    (2 DOF, child of L_knee)
R_ankle:        rx, ry                    (2 DOF, child of R_knee)
```

Joint bounds (degrees):
```
pelvis.rx:  [-45, +45]     trunk.rx:  [-30, +60]
pelvis.ry:  [-25, +25]     trunk.rz:  [-25, +25]
pelvis.rz:  [-15, +15]     
L_hip.rx:   [-15, +130]    R_hip.rx:  [-15, +130]
L_hip.ry:   [-30, +45]     R_hip.ry:  [-45, +30]
L_hip.rz:   [-30, +40]     R_hip.rz:  [-40, +30]
L_knee.rx:  [0, +150]      R_knee.rx: [0, +150]
L_ankle.rx: [-30, +40]     R_ankle.rx:[-30, +40]
L_ankle.ry: [-20, +20]     R_ankle.ry:[-20, +20]
```

## How `fit_frame` works (line 155)

1. Takes (8, 4) landmarks in FK space [x, y, z, visibility]
2. Builds per-joint weights: `w[j] = visibility[j] * weights[j]`
   - weights from caller: `[0.5, 0.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]` (pelvis/trunk downweighted)
3. Cost = weighted sum of squared distances: `sum_j w_j * |FK(q)_j - target_j|^2`
4. Plus knee angle priors (weight=0.08) from observed hip-knee-ankle triangles
5. Plus regularization on pelvis rotations: `ry=5.0, rz=3.0, rx=0.5`
6. Optimized via L-BFGS-B with analytical Jacobian, max 50 iterations

## How `fit_trajectory` works (line 282)

1. Calls `fit_frame` for each frame, warm-starting from previous frame's result
2. After all frames: **Gaussian smoothing** (sigma=1.5 frames) on the full q trajectory
3. After smoothing: clips all DOFs to bounds

## Likely causes to investigate

### 1. Gaussian smoothing destroying the fit (HIGH PRIORITY)
`fit_trajectory` applies `gaussian_filter1d(q_traj, sigma=1.5)` AFTER fitting. This averages nearby frames, which could smear q values and produce physically inconsistent configurations. The bottom-of-squat frame gets blended with the descent/ascent frames, pulling joint angles toward standing.

**Test:** Run `fit_trajectory` with `smooth_sigma=0` and compare errors.

### 2. Ankle/trunk DOFs stuck at zero
These DOFs are initialized to 0 and never move. Possible reasons:
- The Jacobian for these DOFs might be wrong (zero or near-zero gradients)
- The cost landscape might have a local minimum at 0 for these DOFs
- The warm-start chain (each frame starts from previous frame's result) might keep them pinned

**Test:** Initialize ankle.rx to a non-zero value (e.g., 15°) and see if the fit improves. Also verify the Jacobian numerically for ankle DOFs.

### 3. Hip rz hitting bounds
Hip abduction/adduction is always at the ±30° limit. This suggests the optimizer is using hip rz as a compensator for errors it can't resolve through the correct DOFs. The bounds might be too tight, or the optimizer might be finding a local minimum.

**Test:** Widen hip rz bounds temporarily and see if errors decrease.

### 4. Jacobian correctness
The analytical Jacobian in `_fk_jac` (lines 77-109) uses the geometric Jacobian formula. If there's a sign error or axis mapping bug, the optimizer would get wrong gradients and converge to bad solutions.

**Test:** Compare analytical Jacobian against finite-difference numerical Jacobian for a few test configurations.

### 5. Coordinate transform issues in landmark_adapter.py
The pipeline is: vis kpts → MediaPipe space → FK space (negate X and Y). If this transform is wrong, the IK targets are in a different coordinate system than the FK outputs, and the optimizer can't converge.

**Test:** Take a single frame's landmarks, run FK on the fitted q, and compare the FK positions against the landmarks in FK space. (Already done in debug_fk_roundtrip.py — errors are 100-475mm, confirming the fit is bad.)

### 6. max_iter=50 too low
L-BFGS-B might need more iterations to converge, especially for deep squats far from the initial guess.

**Test:** Increase max_iter to 200 or 500 and check if residuals decrease.

## How to verify a fix

Run `PYTHONPATH=src python scripts/debug_fk_roundtrip.py` and check:
- FK vs target landmark errors should be <20mm for lower body joints
- Vis-space original vs reconstructed keypoints should be <30mm for lower body
- Ankle and trunk DOFs should have non-zero values in squat frames
- Hip rz should NOT be at the bound limit for every frame

Then run `PYTHONPATH=src python scripts/visualize_video_squats.py --refit --viewer` and visually confirm the Kinodynamics mode skeleton matches the replay skeleton.

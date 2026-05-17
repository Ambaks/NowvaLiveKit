# Skeleton Spatial Reference (20-DOF Squat Model)

Reference for LLMs and collaborators working on `src/biomechanics/skeleton/definition.py`.

## Coordinate System

- **+X** = subject's left (lateral)
- **+Y** = up (vertical)
- **+Z** = forward (anterior, direction the subject faces)

Y-up, right-handed. The Three.js visualizer in `scripts/visualize_video_squats.py` uses the same convention.

## Joint Hierarchy and Offset Directions

All offsets are relative to the parent joint, in the parent's local frame at neutral pose (all DOFs = 0).

### Upper Body

| Joint | Parent | Offset | Direction description |
|-------|--------|--------|----------------------|
| pelvis | (root) | (0, 0.95, 0) | Floating root, starts ~0.95m above floor |
| trunk | pelvis | (0, 0.28, 0) | Extends **upward** (+Y) from pelvis |
| head | trunk | (0, 0.40, 0) | Extends **upward** (+Y) from trunk |

### Legs

| Joint | Parent | Offset | Direction description |
|-------|--------|--------|----------------------|
| L_hip | pelvis | (-0.10, 0, 0) | Left side of pelvis (-X) |
| R_hip | pelvis | (0.10, 0, 0) | Right side of pelvis (+X) |
| L_knee | L_hip | (0, 0, -0.45) | Thigh extends **backward** (-Z) from hip |
| R_knee | R_hip | (0, 0, -0.45) | Thigh extends **backward** (-Z) from hip |
| L_ankle | L_knee | (0, 0, 0.43) | Shin extends **forward** (+Z) from knee |
| R_ankle | R_knee | (0, 0, 0.43) | Shin extends **forward** (+Z) from knee |
| L_toe | L_ankle | (0, -0.20, 0) | Foot hangs **downward** (-Y) from ankle |
| R_toe | R_ankle | (0, -0.20, 0) | Foot hangs **downward** (-Y) from ankle |

### Key geometry insight

The thigh (-Z) and shin (+Z) extend in **opposite directions** from the knee. This means at neutral pose (knee rx = 0), the leg is already in a bent configuration. The knee `rx` DOF opens or closes this bend. This is what produces a natural squat pose.

## DOF Summary

| Joint | DOFs | Notes |
|-------|------|-------|
| pelvis | tx, ty, tz, rx, ry, rz | 6-DOF floating root |
| trunk | rx, rz | Forward lean + lateral bend |
| L/R_hip | rx, ry, rz | Hip flexion/extension, ab/adduction, rotation |
| L/R_knee | rx | Knee flexion only (single axis) |
| L/R_ankle | rx, ry | Dorsiflexion/plantarflexion + inversion/eversion |
| head, toes | (none) | Passive endpoints, no DOFs |

**Total: 20 DOFs.**

## File locations

- Skeleton definition: `src/biomechanics/skeleton/definition.py`
- Forward kinematics: `src/biomechanics/skeleton/forward_kin.py`
- IK solver: `src/biomechanics/optimizer/ik.py`
- Visualizer (Three.js): `scripts/visualize_video_squats.py`

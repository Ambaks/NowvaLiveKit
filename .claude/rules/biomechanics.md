---
globs:
  - src/biomechanics/**
  - tests/test_biomechanics/**
---

# Biomechanics Domain Rules

## Coordinate System
- Y-axis is vertical (height). Larger Y = higher.
- `hip_position_cm = (hip_mid_y - ankle_mid_y) * 100`
  - More negative = standing (hip far above ankle)
  - Less negative = squat bottom (hip close to ankle)
- Squat bottoms are local maxima of hip_position_cm; standing peaks are local minima.
- All 3D positions in meters unless suffixed otherwise.

## COCO 17 Keypoint Format
- Use `CocoKeypoints` enum (aliased as `CK`) for keypoint indices
- Never use raw integers for keypoint access: `pts[CK.LEFT_KNEE]` not `pts[13]`
- 8 required keypoints for standing validation: shoulders, hips, knees, ankles

## Data Types
- Skeleton data: `Skeleton2D`, `Skeleton3D` from `biomechanics.utils.types`
- Fault data: `FaultEvent`, `FaultSeverity` from `biomechanics.utils.types`
- Angles: `JointAngles` dataclass, fields suffixed `_l`/`_r`
- Config: Pydantic models in `biomechanics.config` — one per subsystem

## Fault Detection
- Severity levels: `MILD`, `MODERATE`, `SEVERE` (three tiers, always)
- Thresholds in degrees unless field name says otherwise (`_cm`, `_m`)
- Fault rules inherit from `FaultRule` ABC in `biomechanics.faults.fault_types`
- Each rule is a single file in `biomechanics/faults/rules/`

## NumPy Conventions
- Keypoint arrays: shape `(N, 3)` — columns are `[x, y, z]` (3D) or `[x, y, confidence]` (2D)
- Always `import numpy as np`, access via `np.`

## Pipeline Architecture
- Data flows: capture → pose estimation → triangulation → IK → fault detection → coaching
- Exercise profiles in `biomechanics/profiles/` define which fault rules activate
- Config loaded once via `load_pipeline_config()`, passed down — not accessed globally

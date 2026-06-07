# NowvaLiveKit — Biomechanics Pipeline Upgrades: Detailed Implementation Specification

**Version:** 1.0  
**Date:** 2026-03-08  
**Scope:** 5 new processing layers inserted into the existing `BiomechanicsPipeline` in `src/biomechanics/pipeline.py`

---

## Table of Contents

1. [Architecture Overview — Before & After](#1-architecture-overview)
2. [Feature 1: Velocity Clamping](#2-velocity-clamping)
3. [Feature 2: Bone Length Constraints](#3-bone-length-constraints)
4. [Feature 3: Confidence-Weighted Blending](#4-confidence-weighted-blending)
5. [Feature 4: Predictive Fault Pre-Cueing](#5-predictive-fault-pre-cueing)
6. [Feature 5: Phase-Aware Smoothing](#6-phase-aware-smoothing)
7. [Integration — Updated Pipeline Flow](#7-integration)
8. [Config Changes](#8-config-changes)
9. [Testing Strategy](#9-testing-strategy)

---

## 1. Architecture Overview

### Current Pipeline (pipeline.py process_frame)

```
Camera → Pose Estimation → [BiLSTM branch] → IK Solve → One Euro Filter → Derivatives → Fault Detection → Rep Counter
```

### Upgraded Pipeline

```
Camera
  → Pose Estimation
  → [BiLSTM branch]  (unchanged — runs on raw skeleton)
  → **Confidence-Weighted Blending** (new — Feature 3)
  → **Velocity Clamping** (new — Feature 1)
  → **Bone Length Constraints** (new — Feature 2)
  → IK Solve
  → **Phase-Aware One Euro Filter** (modified — Feature 5)
  → Derivatives
  → **Predictive Fault Pre-Cueing** (new — Feature 4)
  → Fault Detection (rule engine evaluates PREDICTED angles)
  → Rep Counter
```

### Key Design Principle

Features 1–3 operate on the `Skeleton3D` object (raw 3D keypoints in meters) **before** the IK solver. Features 4–5 operate on `JointAngles` **after** the IK solver. This is deliberate: pre-IK filtering stabilizes the skeleton structurally, while post-IK processing improves coaching timing and angle stability.

---

## 2. Velocity Clamping

### Purpose

Reject impossible joint teleportations where the pose model places a keypoint far from its previous position in a single frame. The One Euro Filter cannot protect against this — it will smoothly track toward the wrong position. A velocity clamp hard-limits per-frame displacement so spikes are capped, not averaged.

### New File: `src/biomechanics/utils/velocity_clamp.py`

```python
"""
Velocity Clamping for 3D Skeleton Keypoints

Limits per-frame displacement of each keypoint to a physically plausible
maximum. If a keypoint moves further than the threshold in one frame,
its position is clamped to the maximum allowed displacement along the
direction of movement.

This runs BEFORE the IK solver, operating on Skeleton3D objects.
"""

import numpy as np
from typing import Optional

from biomechanics.utils.types import Skeleton3D, Point3D


class VelocityClamp:
    """
    Clamps per-frame keypoint displacement to a maximum threshold.

    Given a target FPS and a maximum human joint velocity (m/s), computes
    the maximum displacement per frame. If any keypoint exceeds this,
    its position is moved only as far as the threshold allows, along
    the original displacement direction.

    Args:
        max_velocity_m_per_s: Maximum plausible joint velocity in meters/sec.
            Human joints rarely exceed 3 m/s during heavy barbell lifts.
            Default 2.5 m/s provides headroom without passing spikes.
        target_fps: Expected frame rate. Used to compute per-frame threshold.
            Default 30.
    """

    def __init__(
        self,
        max_velocity_m_per_s: float = 2.5,
        target_fps: int = 30,
    ):
        self.max_displacement = max_velocity_m_per_s / target_fps
        self._prev_positions: Optional[np.ndarray] = None  # (17, 3)

    def clamp(self, skeleton: Skeleton3D) -> Skeleton3D:
        """
        Apply velocity clamping to a skeleton.

        First frame: stores positions, returns skeleton unchanged.
        Subsequent frames: clamps each keypoint displacement.

        Args:
            skeleton: Current frame's Skeleton3D

        Returns:
            New Skeleton3D with clamped keypoint positions.
            Confidences, timestamp, frame_index are preserved.
        """
        current = skeleton.to_numpy()  # (17, 3)
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])

        if self._prev_positions is None:
            self._prev_positions = current.copy()
            return skeleton

        displacement = current - self._prev_positions  # (17, 3)
        distances = np.linalg.norm(displacement, axis=1)  # (17,)

        # Find keypoints that exceed threshold
        exceeded = distances > self.max_displacement

        if np.any(exceeded):
            # Compute unit direction vectors for exceeded keypoints
            # Avoid division by zero for zero-distance keypoints
            safe_distances = np.where(distances > 1e-10, distances, 1.0)
            unit_dirs = displacement / safe_distances[:, np.newaxis]

            # Clamp: move only max_displacement along original direction
            clamped = self._prev_positions.copy()
            clamped[exceeded] = (
                self._prev_positions[exceeded]
                + unit_dirs[exceeded] * self.max_displacement
            )
            # Keep non-exceeded keypoints at their detected position
            clamped[~exceeded] = current[~exceeded]

            self._prev_positions = clamped.copy()
            return Skeleton3D.from_numpy(
                clamped,
                confidences=confidences,
                timestamp=skeleton.timestamp,
                frame_index=skeleton.frame_index,
            )

        # No clamping needed
        self._prev_positions = current.copy()
        return skeleton

    def reset(self):
        """Reset state (e.g., new session or exercise)."""
        self._prev_positions = None
```

### Integration Point in pipeline.py

After pose estimation returns `skeleton_3d`, before IK solve:

```python
# --- Velocity Clamping (after pose, before IK) ---
if skeleton_3d is not None:
    skeleton_3d = self._velocity_clamp.clamp(skeleton_3d)
```

### Config Addition

In `BiomechanicsConfig` / `biomechanics.yaml`:

```yaml
velocity_clamp:
  max_velocity_m_per_s: 2.5
  target_fps: 30
```

---

## 3. Bone Length Constraints

### Purpose

After calibrating segment lengths from the first N frames, enforce that bone lengths cannot change. If a keypoint drifts to a position that violates the calibrated segment length, project it back onto the allowed radius around its parent joint. This catches structurally impossible poses that pass through velocity clamping and smoothing.

### New File: `src/biomechanics/utils/bone_constraints.py`

```python
"""
Bone Length Constraint Enforcement

Calibrates segment lengths from the first N frames, then enforces
them as hard constraints. If a distal keypoint violates the calibrated
distance from its proximal joint, it is projected back onto the sphere
of allowed radius.

Operates on Skeleton3D objects, BEFORE the IK solver.

Bone pairs follow the COCO 17 keypoint ordering and are defined
as (proximal_index, distal_index) — the distal point gets corrected.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import deque

from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK


# Ordered from proximal to distal so corrections cascade properly.
# Each tuple is (proximal_keypoint_index, distal_keypoint_index).
BONE_PAIRS: List[Tuple[int, int]] = [
    # Torso
    (CK.LEFT_SHOULDER, CK.LEFT_HIP),
    (CK.RIGHT_SHOULDER, CK.RIGHT_HIP),
    (CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER),
    (CK.LEFT_HIP, CK.RIGHT_HIP),
    # Left leg
    (CK.LEFT_HIP, CK.LEFT_KNEE),
    (CK.LEFT_KNEE, CK.LEFT_ANKLE),
    # Right leg
    (CK.RIGHT_HIP, CK.RIGHT_KNEE),
    (CK.RIGHT_KNEE, CK.RIGHT_ANKLE),
    # Left arm
    (CK.LEFT_SHOULDER, CK.LEFT_ELBOW),
    (CK.LEFT_ELBOW, CK.LEFT_WRIST),
    # Right arm
    (CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW),
    (CK.RIGHT_ELBOW, CK.RIGHT_WRIST),
]


class BoneLengthConstraints:
    """
    Calibrates and enforces fixed bone lengths on Skeleton3D.

    During calibration (first `calibration_frames` frames), bone lengths
    are measured each frame and the median is stored. After calibration,
    any keypoint that violates its bone length by more than `tolerance`
    percent is projected back to the correct distance.

    Args:
        calibration_frames: Number of frames to observe before locking
            bone lengths. Default 30 (~1 second at 30fps).
        tolerance: Fractional tolerance before correction kicks in.
            0.15 means 15% deviation is allowed. Default 0.15.
    """

    def __init__(
        self,
        calibration_frames: int = 30,
        tolerance: float = 0.15,
    ):
        self.calibration_frames = calibration_frames
        self.tolerance = tolerance

        self._calibrated = False
        self._frame_count = 0

        # During calibration: bone_pair_key -> list of observed lengths
        self._length_observations: Dict[Tuple[int, int], List[float]] = {
            pair: [] for pair in BONE_PAIRS
        }

        # After calibration: bone_pair_key -> median length
        self._calibrated_lengths: Dict[Tuple[int, int], float] = {}

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    def enforce(self, skeleton: Skeleton3D) -> Skeleton3D:
        """
        Enforce bone length constraints.

        During calibration: records bone lengths, returns skeleton unchanged.
        After calibration: projects violating keypoints back to allowed radius.

        Args:
            skeleton: Current frame's Skeleton3D

        Returns:
            Skeleton3D with bone lengths enforced (or unchanged during calibration).
        """
        points = skeleton.to_numpy()  # (17, 3)
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])

        if not self._calibrated:
            self._record_calibration(points)
            self._frame_count += 1

            if self._frame_count >= self.calibration_frames:
                self._finalize_calibration()

            return skeleton

        # --- Enforcement pass ---
        corrected = points.copy()

        for proximal_idx, distal_idx in BONE_PAIRS:
            p_prox = corrected[proximal_idx]
            p_dist = corrected[distal_idx]

            current_length = np.linalg.norm(p_dist - p_prox)
            target_length = self._calibrated_lengths.get(
                (proximal_idx, distal_idx)
            )

            if target_length is None or target_length < 1e-6:
                continue

            # Check if violation exceeds tolerance
            deviation = abs(current_length - target_length) / target_length

            if deviation > self.tolerance:
                # Project distal point onto sphere of radius target_length
                # centered at proximal point
                if current_length < 1e-10:
                    # Degenerate: distal is on top of proximal.
                    # Push it in the +Y direction (upward) by target_length.
                    direction = np.array([0.0, 1.0, 0.0])
                else:
                    direction = (p_dist - p_prox) / current_length

                corrected[distal_idx] = p_prox + direction * target_length

        return Skeleton3D.from_numpy(
            corrected,
            confidences=confidences,
            timestamp=skeleton.timestamp,
            frame_index=skeleton.frame_index,
        )

    def _record_calibration(self, points: np.ndarray) -> None:
        """Record bone lengths for one frame during calibration."""
        for proximal_idx, distal_idx in BONE_PAIRS:
            length = float(np.linalg.norm(
                points[distal_idx] - points[proximal_idx]
            ))
            if length > 1e-6:  # Skip degenerate frames
                self._length_observations[(proximal_idx, distal_idx)].append(length)

    def _finalize_calibration(self) -> None:
        """Compute median bone lengths and lock calibration."""
        for pair, lengths in self._length_observations.items():
            if lengths:
                self._calibrated_lengths[pair] = float(np.median(lengths))

        self._calibrated = True

        # Free observation memory
        self._length_observations.clear()

    def reset(self):
        """Reset calibration state."""
        self._calibrated = False
        self._frame_count = 0
        self._calibrated_lengths.clear()
        self._length_observations = {pair: [] for pair in BONE_PAIRS}
```

### Integration Point in pipeline.py

After velocity clamping, before IK solve:

```python
# --- Bone Length Constraints (after velocity clamp, before IK) ---
if skeleton_3d is not None:
    skeleton_3d = self._bone_constraints.enforce(skeleton_3d)
```

### Config Addition

```yaml
bone_constraints:
  calibration_frames: 30
  tolerance: 0.15
```

---

## 4. Confidence-Weighted Blending

### Purpose

Replace the binary confidence threshold (accept/reject at 0.3) with a soft blending scheme. Low-confidence keypoints are blended toward their previous position rather than fully trusted or fully discarded. This provides graceful degradation when a joint is partially occluded.

### New File: `src/biomechanics/utils/confidence_blend.py`

```python
"""
Confidence-Weighted Keypoint Blending

Instead of a binary accept/reject threshold, blends each keypoint's
detected position with its previous position based on confidence score.

    blended = confidence * detected + (1 - confidence) * previous

High confidence → trust detection.
Low confidence → rely on previous position.
Zero confidence → fully use previous position.

Operates on Skeleton3D, BEFORE velocity clamping and IK.
"""

import numpy as np
from typing import Optional

from biomechanics.utils.types import Skeleton3D


class ConfidenceBlender:
    """
    Blends keypoint positions with previous frame based on confidence.

    Args:
        min_confidence: Below this confidence, fully use previous position.
            Default 0.1 (effectively zero-confidence floor).
        max_confidence: Above this confidence, fully trust detection.
            Default 0.9. Confidences between min and max are linearly
            interpolated.
    """

    def __init__(
        self,
        min_confidence: float = 0.1,
        max_confidence: float = 0.9,
    ):
        self.min_confidence = min_confidence
        self.max_confidence = max_confidence
        self._prev_positions: Optional[np.ndarray] = None  # (17, 3)

    def blend(self, skeleton: Skeleton3D) -> Skeleton3D:
        """
        Apply confidence-weighted blending.

        First frame: stores positions, returns skeleton unchanged.
        Subsequent frames: blends each keypoint based on its confidence.

        Args:
            skeleton: Current frame's Skeleton3D with per-keypoint confidences.

        Returns:
            New Skeleton3D with blended positions.
        """
        current = skeleton.to_numpy()  # (17, 3)
        confidences = np.array([kp.confidence for kp in skeleton.keypoints])

        if self._prev_positions is None:
            self._prev_positions = current.copy()
            return skeleton

        # Compute blend weights: map [min_confidence, max_confidence] → [0, 1]
        range_size = self.max_confidence - self.min_confidence
        if range_size < 1e-6:
            weights = np.where(confidences >= self.max_confidence, 1.0, 0.0)
        else:
            weights = (confidences - self.min_confidence) / range_size
            weights = np.clip(weights, 0.0, 1.0)

        # Blend: weight * current + (1 - weight) * previous
        # weights shape: (17,) → expand to (17, 1) for broadcasting
        blended = (
            weights[:, np.newaxis] * current
            + (1.0 - weights[:, np.newaxis]) * self._prev_positions
        )

        self._prev_positions = blended.copy()

        return Skeleton3D.from_numpy(
            blended,
            confidences=confidences,
            timestamp=skeleton.timestamp,
            frame_index=skeleton.frame_index,
        )

    def reset(self):
        """Reset state."""
        self._prev_positions = None
```

### Integration Point in pipeline.py

After pose estimation, BEFORE velocity clamping:

```python
# --- Confidence Blending (first pre-IK filter) ---
if skeleton_3d is not None:
    skeleton_3d = self._confidence_blender.blend(skeleton_3d)
```

### Config Addition

```yaml
confidence_blend:
  min_confidence: 0.1
  max_confidence: 0.9
```

---

## 5. Predictive Fault Pre-Cueing

### Purpose

Use the velocities already computed by `DerivativeTracker` to predict joint angles 150–200ms into the future, then evaluate fault rules against predicted angles instead of current angles. This compensates for audio pipeline latency (TTS generation + audio ducking + playback start), making cues arrive during the relevant movement phase instead of after.

### New File: `src/biomechanics/utils/predictive_state.py`

```python
"""
Predictive State Estimator

Uses current joint angles and angular velocities to predict the state
at a configurable time horizon (default 200ms). The predicted angles
are used for fault evaluation, allowing cues to fire before the fault
fully manifests.

This does NOT replace the current angles — it produces a separate
PredictedAngles object that the rule engine evaluates against.
"""

from biomechanics.utils.types import JointAngles
from biomechanics.utils.derivatives import AngleDerivatives


class PredictiveStateEstimator:
    """
    Predicts future joint angles using constant-velocity extrapolation.

    predicted_angle = current_angle + velocity * horizon_seconds

    Args:
        horizon_seconds: How far ahead to predict, in seconds.
            Default 0.2 (200ms). Should match approximate audio
            pipeline latency. Range 0.1–0.3 recommended.
        max_extrapolation_deg: Maximum angle change allowed per prediction.
            Prevents runaway extrapolation during noisy velocity spikes.
            Default 15.0 degrees.
    """

    def __init__(
        self,
        horizon_seconds: float = 0.2,
        max_extrapolation_deg: float = 15.0,
    ):
        self.horizon_seconds = horizon_seconds
        self.max_extrapolation_deg = max_extrapolation_deg

    def predict(
        self,
        angles: JointAngles,
        derivatives: AngleDerivatives,
    ) -> JointAngles:
        """
        Predict future joint angles from current angles + velocities.

        Args:
            angles: Current frame's filtered joint angles.
            derivatives: Current frame's angular velocities.

        Returns:
            New JointAngles object with predicted values.
            timestamp and frame_index are copied from the input.
        """
        dt = self.horizon_seconds

        def _extrapolate(current: float, velocity: float) -> float:
            delta = velocity * dt
            # Clamp extrapolation magnitude
            if abs(delta) > self.max_extrapolation_deg:
                delta = self.max_extrapolation_deg * (1.0 if delta > 0 else -1.0)
            return current + delta

        return JointAngles(
            # Hip angles — use average velocity for both sides since
            # DerivativeTracker tracks per-side
            hip_flexion_l=_extrapolate(
                angles.hip_flexion_l, derivatives.hip_velocity_l
            ),
            hip_flexion_r=_extrapolate(
                angles.hip_flexion_r, derivatives.hip_velocity_r
            ),
            # Hip adduction/rotation: no velocity tracked yet,
            # so use current values (no extrapolation)
            hip_adduction_l=angles.hip_adduction_l,
            hip_adduction_r=angles.hip_adduction_r,
            hip_rotation_l=angles.hip_rotation_l,
            hip_rotation_r=angles.hip_rotation_r,
            # Knee angles
            knee_flexion_l=_extrapolate(
                angles.knee_flexion_l, derivatives.knee_velocity_l
            ),
            knee_flexion_r=_extrapolate(
                angles.knee_flexion_r, derivatives.knee_velocity_r
            ),
            # Ankle: no velocity tracked, use current
            ankle_dorsiflexion_l=angles.ankle_dorsiflexion_l,
            ankle_dorsiflexion_r=angles.ankle_dorsiflexion_r,
            # Trunk: no velocity tracked, use current
            trunk_flexion=angles.trunk_flexion,
            trunk_lateral_flexion=angles.trunk_lateral_flexion,
            trunk_rotation=angles.trunk_rotation,
            # Pelvis: no velocity tracked, use current
            pelvis_tilt=angles.pelvis_tilt,
            pelvis_list=angles.pelvis_list,
            pelvis_rotation=angles.pelvis_rotation,
            # Metadata
            timestamp=angles.timestamp,
            frame_index=angles.frame_index,
        )
```

### Integration Point in pipeline.py

After derivatives are computed, BEFORE fault evaluation:

```python
# --- Predictive state for fault detection ---
predicted_angles = self._predictive_estimator.predict(angles, derivatives)

# --- Fault detection uses PREDICTED angles ---
faults = self._rule_engine.evaluate(
    predicted_angles,  # <-- was: angles
    in_rep=self._rep_counter.in_rep,
    rep_number=self._rep_counter.rep_count + 1,
)
```

**Critical note:** The rep counter should still receive the ACTUAL angles, not predicted ones. Prediction is only for fault timing.

```python
# Rep counter uses ACTUAL filtered angles (not predicted)
rep_data, feedback = self._rep_counter.update(angles, derivatives, faults)
```

### Config Addition

```yaml
predictive_state:
  horizon_seconds: 0.2
  max_extrapolation_deg: 15.0
```

---

## 6. Phase-Aware Smoothing

### Purpose

When the lifter is standing still between reps (phase = `idle`), the One Euro Filter should use much heavier smoothing to eliminate standing jitter. During active movement (descent/bottom/ascent), smoothing should be lighter to preserve motion fidelity.

### Modification to: `src/biomechanics/utils/filters.py`

The `JointAngleFilter` class needs a new method to update filter parameters based on the current rep phase.

```python
# Add to JointAngleFilter class:

# Phase -> (min_cutoff, beta) mapping
PHASE_PARAMS = {
    "idle":       (0.3, 0.003),   # Heavy smoothing — kill standing jitter
    "descending": (1.0, 0.007),   # Standard — responsive to fast descent
    "bottom":     (0.8, 0.005),   # Moderate — stable at bottom
    "ascending":  (1.0, 0.007),   # Standard — responsive to ascent
}

DEFAULT_PARAMS = (1.0, 0.007)


def update_phase(self, phase: str) -> None:
    """
    Adjust filter parameters based on current rep phase.

    Called each frame from the pipeline after rep counter updates.
    Changes apply to the NEXT filter call, not retroactively.

    Args:
        phase: One of "idle", "descending", "bottom", "ascending"
    """
    min_cutoff, beta = self.PHASE_PARAMS.get(phase, self.DEFAULT_PARAMS)

    # Only update if parameters actually changed (avoid dict iteration every frame)
    if min_cutoff != self.min_cutoff or beta != self.beta:
        self.min_cutoff = min_cutoff
        self.beta = beta

        # Update existing filter instances
        for filt in self._filters.values():
            filt.min_cutoff = min_cutoff
            filt.beta = beta
```

### Integration Point in pipeline.py

After the rep counter update (so we know the current phase), update the filter for the NEXT frame:

```python
# --- Phase-aware smoothing update ---
self._angle_filter.update_phase(self._rep_counter.phase)
```

This is called AFTER `rep_counter.update()` but the new parameters take effect on the NEXT `filter_angles()` call, which is the correct behavior.

### No Config Change Needed

The phase-parameter mapping is hardcoded because:
- These values are tightly coupled to the One Euro Filter behavior.
- They shouldn't vary per-user or per-deployment.
- Exposing them in config would invite misconfiguration.

---

## 7. Integration — Updated pipeline.py process_frame

Here is the complete updated flow for the `process_frame` method. Changed/new lines are marked.

```python
def process_frame(self) -> PipelineFrame:
    latency_ms = {}
    now = time.time()

    # --- Capture ---
    t0 = time.perf_counter()
    ret, frame = self._cap.read()
    latency_ms["capture"] = (time.perf_counter() - t0) * 1000.0

    if not ret or frame is None:
        self._frame_index += 1
        return PipelineFrame(frame_index=self._frame_index, timestamp=now, latency_ms=latency_ms)

    self.last_frame = frame

    # --- Pose estimation ---
    t0 = time.perf_counter()
    skeleton_2d = None
    skeleton_3d = None
    try:
        skeleton_2d, skeleton_3d = self._pose_estimator.estimate_both(frame)
    except Exception:
        pass
    latency_ms["pose"] = (time.perf_counter() - t0) * 1000.0

    if skeleton_3d is None:
        self._frame_index += 1
        return PipelineFrame(
            frame_index=self._frame_index, timestamp=now,
            skeleton_2d=skeleton_2d, latency_ms=latency_ms,
        )

    # --- BiLSTM (unchanged — runs on raw skeleton) ---
    bilstm_rep_data = None
    # ... (existing BiLSTM code unchanged) ...

    # ===== NEW PRE-IK FILTERING LAYERS =====
    t0 = time.perf_counter()

    # Layer A: Confidence-weighted blending
    skeleton_3d = self._confidence_blender.blend(skeleton_3d)

    # Layer B: Velocity clamping
    skeleton_3d = self._velocity_clamp.clamp(skeleton_3d)

    # Layer C: Bone length constraints
    skeleton_3d = self._bone_constraints.enforce(skeleton_3d)

    latency_ms["pre_ik_filters"] = (time.perf_counter() - t0) * 1000.0
    # ===== END NEW LAYERS =====

    # --- IK solve ---
    t0 = time.perf_counter()
    raw_angles = self._ik_solver.solve(skeleton_3d)
    angles = self._angle_filter.filter_angles(raw_angles)
    derivatives = self._derivative_tracker.update(angles)
    latency_ms["ik"] = (time.perf_counter() - t0) * 1000.0

    # --- Fault detection + rep counting ---
    t0 = time.perf_counter()

    # NEW: Predict future state for fault evaluation
    predicted_angles = self._predictive_estimator.predict(angles, derivatives)

    # Fault detection uses PREDICTED angles
    faults = self._rule_engine.evaluate(
        predicted_angles,
        in_rep=self._rep_counter.in_rep,
        rep_number=self._rep_counter.rep_count + 1,
    )

    # Calibration uses ACTUAL angles
    if not self._rule_engine.calibrated and self._rep_counter.in_rep:
        self._rule_engine.record_frame_for_calibration(angles)

    # Rep counter uses ACTUAL angles
    rep_data, feedback = self._rep_counter.update(angles, derivatives, faults)

    if rep_data is not None:
        depth_faults = self._rule_engine.evaluate_rep_complete(
            rep_data.max_depth_angle, angles, rep_data.rep_number
        )
        faults.extend(depth_faults)
        self._rule_engine.on_rep_complete_calibration(is_clean=rep_data.is_clean)

    # NEW: Update filter parameters for next frame based on current phase
    self._angle_filter.update_phase(self._rep_counter.phase)

    latency_ms["faults"] = (time.perf_counter() - t0) * 1000.0

    self._frame_index += 1

    # ... (existing PipelineFrame construction unchanged) ...
```

### Constructor Changes in `__init__`

```python
# Add these imports at the top of pipeline.py:
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.predictive_state import PredictiveStateEstimator

# In __init__, after existing component initialization:

# Pre-IK skeleton filtering
self._confidence_blender = ConfidenceBlender(
    min_confidence=self.config.confidence_blend.min_confidence,
    max_confidence=self.config.confidence_blend.max_confidence,
)
self._velocity_clamp = VelocityClamp(
    max_velocity_m_per_s=self.config.velocity_clamp.max_velocity_m_per_s,
    target_fps=self.config.pipeline.target_fps,
)
self._bone_constraints = BoneLengthConstraints(
    calibration_frames=self.config.bone_constraints.calibration_frames,
    tolerance=self.config.bone_constraints.tolerance,
)

# Post-IK predictive state
self._predictive_estimator = PredictiveStateEstimator(
    horizon_seconds=self.config.predictive_state.horizon_seconds,
    max_extrapolation_deg=self.config.predictive_state.max_extrapolation_deg,
)
```

---

## 8. Config Changes

### New Config Models in `src/biomechanics/config.py`

```python
class VelocityClampConfig(BaseModel):
    """Velocity clamping configuration."""
    max_velocity_m_per_s: float = 2.5
    target_fps: int = 30  # Falls back to pipeline.target_fps if not set

class BoneConstraintsConfig(BaseModel):
    """Bone length constraint configuration."""
    calibration_frames: int = 30
    tolerance: float = 0.15

class ConfidenceBlendConfig(BaseModel):
    """Confidence-weighted blending configuration."""
    min_confidence: float = 0.1
    max_confidence: float = 0.9

class PredictiveStateConfig(BaseModel):
    """Predictive fault pre-cueing configuration."""
    horizon_seconds: float = 0.2
    max_extrapolation_deg: float = 15.0
```

### Add to BiomechanicsConfig

```python
class BiomechanicsConfig(BaseModel):
    # ... existing fields ...
    velocity_clamp: VelocityClampConfig = Field(default_factory=VelocityClampConfig)
    bone_constraints: BoneConstraintsConfig = Field(default_factory=BoneConstraintsConfig)
    confidence_blend: ConfidenceBlendConfig = Field(default_factory=ConfidenceBlendConfig)
    predictive_state: PredictiveStateConfig = Field(default_factory=PredictiveStateConfig)
```

### Updated biomechanics.yaml

```yaml
# ... existing config ...

velocity_clamp:
  max_velocity_m_per_s: 2.5

bone_constraints:
  calibration_frames: 30
  tolerance: 0.15

confidence_blend:
  min_confidence: 0.1
  max_confidence: 0.9

predictive_state:
  horizon_seconds: 0.2
  max_extrapolation_deg: 15.0
```

---

## 9. Testing Strategy

### Unit Tests per Feature

All tests go in `tests/test_biomechanics/`.

#### test_velocity_clamp.py

1. **test_no_clamp_within_threshold**: Create two Skeleton3D frames where all keypoints move < max_displacement. Assert output equals input.
2. **test_clamp_teleporting_joint**: Set one keypoint 0.5m away from previous. Assert clamped distance equals max_displacement.
3. **test_direction_preserved**: After clamping, assert the direction from previous to clamped matches the direction to detected.
4. **test_first_frame_passthrough**: First call returns skeleton unchanged.
5. **test_reset**: After reset, next call acts as first frame again.

#### test_bone_constraints.py

1. **test_calibration_phase**: Feed 30 frames with consistent bone lengths. Assert `is_calibrated` becomes True.
2. **test_enforcement_corrects_violation**: After calibration, feed a skeleton where femur is 50% longer. Assert distal keypoint is projected back.
3. **test_within_tolerance_unchanged**: Feed skeleton where bone is 10% off (within 15% tolerance). Assert no correction.
4. **test_cascade_order**: Verify proximal-to-distal correction order (correcting knee after hip).

#### test_confidence_blend.py

1. **test_high_confidence_passthrough**: All confidences at 0.95 → output matches input.
2. **test_low_confidence_uses_previous**: All confidences at 0.05 → output matches previous frame.
3. **test_interpolation**: Confidence at 0.5 → output is midpoint between detected and previous.
4. **test_first_frame_passthrough**: First call returns unchanged.

#### test_predictive_state.py

1. **test_zero_velocity_no_change**: With zero velocities, predicted angles equal current angles.
2. **test_positive_velocity_extrapolates**: Knee velocity of 100 deg/s with 0.2s horizon → predicted knee angle is current + 20.
3. **test_max_extrapolation_clamp**: Large velocity that would extrapolate > 15 degrees gets clamped.
4. **test_untracked_angles_unchanged**: Angles without velocity tracking (ankle, trunk) are copied unchanged.

#### test_phase_aware_smoothing.py

1. **test_idle_phase_heavy_smoothing**: After setting phase to "idle", verify `min_cutoff` is 0.3.
2. **test_descending_phase_standard_smoothing**: After setting phase to "descending", verify `min_cutoff` is 1.0.
3. **test_parameters_update_existing_filters**: Create filters, call `update_phase`, verify individual filter instances updated.

### Integration Test

**test_pipeline_with_upgrades.py**: Feed synthetic skeleton sequences through the full pipeline and verify:
- No exceptions across 100 frames
- Rep detection still works with pre-IK filtering active
- Fault detection fires with predictive cueing
- Phase transitions update filter parameters

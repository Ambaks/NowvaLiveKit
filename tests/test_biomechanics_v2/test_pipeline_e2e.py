"""End-to-end tests for BiomechanicsV2Pipeline.

Feeds synthetic Skeleton3D frames (generated from MuJoCo FK) through the
pipeline and verifies that all layers produce valid output.
"""

from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from biomechanics.utils.types import CocoKeypoints, Skeleton3D
from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.pipeline import BiomechanicsV2Pipeline


# ---------------------------------------------------------------------------
# Helpers: generate synthetic Skeleton3D from MuJoCo FK
# ---------------------------------------------------------------------------

_TRUNK_SHOULDER_FRACTION = 0.58


def _mujoco_positions_to_skeleton3d(
    skeleton: MujocoSkeleton,
    q_vector: np.ndarray,
    timestamp: float,
    frame_index: int,
) -> Skeleton3D:
    """Run MuJoCo FK and convert 11 body positions back to 19-keypoint Skeleton3D.

    The output is in MediaPipe Y-down coordinates so that the pipeline's
    landmark_adapter can convert it back to MuJoCo Y-up without loss.
    """
    skeleton.set_qpos(q_vector)
    skeleton.forward()
    positions = skeleton.get_body_positions()

    keypoint_positions = np.zeros((19, 3))
    confidences = np.ones(19) * 0.9

    # MuJoCo Y-up -> MediaPipe Y-down: negate X, negate Y, keep Z
    def flip_to_mediapipe(position_yup: np.ndarray) -> np.ndarray:
        return np.array([-position_yup[0], -position_yup[1], position_yup[2]])

    # Direct body -> COCO keypoint mappings
    keypoint_positions[CocoKeypoints.NOSE] = flip_to_mediapipe(positions["head"])
    keypoint_positions[CocoKeypoints.LEFT_HIP] = flip_to_mediapipe(positions["L_hip"])
    keypoint_positions[CocoKeypoints.RIGHT_HIP] = flip_to_mediapipe(positions["R_hip"])
    keypoint_positions[CocoKeypoints.LEFT_KNEE] = flip_to_mediapipe(positions["L_knee"])
    keypoint_positions[CocoKeypoints.RIGHT_KNEE] = flip_to_mediapipe(positions["R_knee"])
    keypoint_positions[CocoKeypoints.LEFT_ANKLE] = flip_to_mediapipe(positions["L_ankle"])
    keypoint_positions[CocoKeypoints.RIGHT_ANKLE] = flip_to_mediapipe(positions["R_ankle"])
    keypoint_positions[CocoKeypoints.LEFT_FOOT_INDEX] = flip_to_mediapipe(positions["L_toe"])
    keypoint_positions[CocoKeypoints.RIGHT_FOOT_INDEX] = flip_to_mediapipe(positions["R_toe"])

    # Derive shoulder positions from trunk body
    # In the forward direction: trunk_yup = f * shoulder_mid_yup + (1-f) * hip_mid_yup
    # Reverse: shoulder_mid_yup = (trunk_yup - (1-f) * hip_mid_yup) / f
    hip_midpoint_yup = (positions["L_hip"] + positions["R_hip"]) / 2.0
    shoulder_midpoint_yup = (
        positions["trunk"] - (1.0 - _TRUNK_SHOULDER_FRACTION) * hip_midpoint_yup
    ) / _TRUNK_SHOULDER_FRACTION

    # Estimate shoulder width from hip width
    hip_direction = positions["L_hip"] - positions["R_hip"]
    hip_width = np.linalg.norm(hip_direction)
    hip_direction_normalized = hip_direction / (hip_width + 1e-10)
    shoulder_half_width = hip_width * 0.75

    left_shoulder_yup = shoulder_midpoint_yup + shoulder_half_width * hip_direction_normalized
    right_shoulder_yup = shoulder_midpoint_yup - shoulder_half_width * hip_direction_normalized
    keypoint_positions[CocoKeypoints.LEFT_SHOULDER] = flip_to_mediapipe(left_shoulder_yup)
    keypoint_positions[CocoKeypoints.RIGHT_SHOULDER] = flip_to_mediapipe(right_shoulder_yup)

    # Eyes and ears near head (low importance for squat pipeline)
    head_position = keypoint_positions[CocoKeypoints.NOSE]
    keypoint_positions[CocoKeypoints.LEFT_EYE] = head_position + [0.03, 0.0, 0.0]
    keypoint_positions[CocoKeypoints.RIGHT_EYE] = head_position + [-0.03, 0.0, 0.0]
    keypoint_positions[CocoKeypoints.LEFT_EAR] = head_position + [0.06, 0.0, 0.0]
    keypoint_positions[CocoKeypoints.RIGHT_EAR] = head_position + [-0.06, 0.0, 0.0]

    # Arms (low confidence — pipeline doesn't use them for squat IK)
    for arm_index in [
        CocoKeypoints.LEFT_ELBOW, CocoKeypoints.RIGHT_ELBOW,
        CocoKeypoints.LEFT_WRIST, CocoKeypoints.RIGHT_WRIST,
    ]:
        confidences[arm_index] = 0.1

    left_shoulder = keypoint_positions[CocoKeypoints.LEFT_SHOULDER]
    right_shoulder = keypoint_positions[CocoKeypoints.RIGHT_SHOULDER]
    keypoint_positions[CocoKeypoints.LEFT_ELBOW] = left_shoulder + [0.0, 0.30, 0.0]
    keypoint_positions[CocoKeypoints.RIGHT_ELBOW] = right_shoulder + [0.0, 0.30, 0.0]
    keypoint_positions[CocoKeypoints.LEFT_WRIST] = left_shoulder + [0.0, 0.55, 0.0]
    keypoint_positions[CocoKeypoints.RIGHT_WRIST] = right_shoulder + [0.0, 0.55, 0.0]

    return Skeleton3D.from_numpy(
        keypoint_positions,
        confidences=confidences,
        timestamp=timestamp,
        frame_index=frame_index,
    )


def _generate_squat_trajectory(
    skeleton: MujocoSkeleton,
    num_frames: int = 30,
    fps: float = 30.0,
) -> list[tuple[Skeleton3D, float]]:
    """Generate standing -> deep squat -> standing trajectory.

    Returns a list of (Skeleton3D, timestamp) pairs.
    """
    neutral_q = skeleton.neutral_q()
    scale_factor = skeleton.height_m / 1.75

    # Deep squat: hip flexion ~90deg, knee ~120deg, ankle DF ~25deg
    squat_q = neutral_q.copy()
    squat_q[1] = 0.55 * scale_factor  # lower pelvis
    squat_q[skeleton.get_joint_index("L_hip", "rx")] = np.radians(90)
    squat_q[skeleton.get_joint_index("R_hip", "rx")] = np.radians(90)
    squat_q[skeleton.get_joint_index("L_knee", "rx")] = np.radians(120)
    squat_q[skeleton.get_joint_index("R_knee", "rx")] = np.radians(120)
    squat_q[skeleton.get_joint_index("L_ankle", "rx")] = np.radians(25)
    squat_q[skeleton.get_joint_index("R_ankle", "rx")] = np.radians(25)

    frames = []
    for frame_idx in range(num_frames):
        # Sinusoidal interpolation: 0 -> 1 -> 0 over one full cycle
        interpolation_factor = 0.5 * (
            1.0 - np.cos(2.0 * np.pi * frame_idx / (num_frames - 1))
        )
        q_interpolated = neutral_q * (1.0 - interpolation_factor) + squat_q * interpolation_factor
        timestamp = frame_idx / fps

        skeleton_3d = _mujoco_positions_to_skeleton3d(
            skeleton, q_interpolated, timestamp, frame_idx
        )
        frames.append((skeleton_3d, timestamp))

    return frames


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipelineE2E:
    """End-to-end pipeline tests with synthetic data."""

    def _create_pipeline(self, **kwargs) -> BiomechanicsV2Pipeline:
        defaults = dict(
            height_m=1.75,
            weight_kg=75.0,
            exercise_name="Barbell Back Squat",
            enable_barbell=False,
        )
        defaults.update(kwargs)
        return BiomechanicsV2Pipeline(**defaults)

    def test_30_frame_trajectory_produces_joint_angles(self):
        """Feed 30 synthetic frames and verify every frame has joint_angles."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=30)
        pipeline = self._create_pipeline()

        results = []
        for skeleton_3d, timestamp in trajectory:
            result = pipeline.process_skeleton3d(skeleton_3d, timestamp)
            results.append(result)

        for frame_idx, result in enumerate(results):
            assert result.joint_angles is not None, (
                f"Frame {frame_idx} has no joint_angles"
            )

    def test_q_trajectory_shape(self):
        """Verify accumulated q-trajectory has correct shape."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=30)
        pipeline = self._create_pipeline()

        for skeleton_3d, timestamp in trajectory:
            pipeline.process_skeleton3d(skeleton_3d, timestamp)

        q_trajectory = pipeline.get_q_trajectory()
        assert q_trajectory.shape == (30, 20), (
            f"Expected (30, 20), got {q_trajectory.shape}"
        )

    def test_q_trajectory_varies_across_frames(self):
        """Q-values should change across the trajectory (not stuck at zero)."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=30)
        pipeline = self._create_pipeline()

        for skeleton_3d, timestamp in trajectory:
            pipeline.process_skeleton3d(skeleton_3d, timestamp)

        q_trajectory = pipeline.get_q_trajectory()
        per_dof_range = q_trajectory.max(axis=0) - q_trajectory.min(axis=0)
        total_variation = per_dof_range.sum()
        assert total_variation > 0.1, (
            f"Q-trajectory has too little variation: {total_variation:.4f}"
        )

    def test_fault_detection_runs(self):
        """Verify fault detection executes (empty fault list is valid for clean data)."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=30)
        pipeline = self._create_pipeline()

        all_faults = []
        for skeleton_3d, timestamp in trajectory:
            result = pipeline.process_skeleton3d(skeleton_3d, timestamp)
            all_faults.extend(result.faults)

        assert isinstance(all_faults, list)

    def test_latency_ms_populated(self):
        """Verify per-layer latency_ms is populated for each frame."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=10)
        pipeline = self._create_pipeline()

        for skeleton_3d, timestamp in trajectory:
            result = pipeline.process_skeleton3d(skeleton_3d, timestamp)
            assert "ik" in result.latency_ms, "Missing 'ik' latency"
            assert "pre_ik_filters" in result.latency_ms, "Missing 'pre_ik_filters' latency"
            assert "faults" in result.latency_ms, "Missing 'faults' latency"
            assert result.total_latency_ms > 0.0

    def test_reset_clears_state(self):
        """Verify reset() clears q-trajectory and frame index."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=5)
        pipeline = self._create_pipeline()

        for skeleton_3d, timestamp in trajectory:
            pipeline.process_skeleton3d(skeleton_3d, timestamp)

        assert pipeline.get_q_trajectory().shape[0] == 5

        pipeline.reset()

        assert pipeline.get_q_trajectory().shape == (0, 20)

    def test_get_skeleton_returns_mujoco_skeleton(self):
        """Verify get_skeleton() returns the MuJoCo skeleton with correct config."""
        pipeline = self._create_pipeline(height_m=1.885, weight_kg=80.0)
        skeleton = pipeline.get_skeleton()

        assert isinstance(skeleton, MujocoSkeleton)
        assert skeleton.height_m == 1.885
        assert skeleton.n_dof() == 20

    def test_scaled_height(self):
        """Verify pipeline works with non-default height (user's 188.5cm)."""
        skeleton = MujocoSkeleton(height_m=1.885, weight_kg=80.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=10)
        pipeline = self._create_pipeline(height_m=1.885, weight_kg=80.0)

        for skeleton_3d, timestamp in trajectory:
            result = pipeline.process_skeleton3d(skeleton_3d, timestamp)
            assert result.joint_angles is not None

        q_trajectory = pipeline.get_q_trajectory()
        assert q_trajectory.shape == (10, 20)

    def test_joint_angles_are_reasonable(self):
        """Verify joint angle magnitudes are in plausible ranges."""
        skeleton = MujocoSkeleton(height_m=1.75, weight_kg=75.0)
        trajectory = _generate_squat_trajectory(skeleton, num_frames=30)
        pipeline = self._create_pipeline()

        # Process all frames
        results = []
        for skeleton_3d, timestamp in trajectory:
            results.append(pipeline.process_skeleton3d(skeleton_3d, timestamp))

        # Find the frame closest to squat bottom (frame ~15 of 30)
        bottom_frame = 15
        bottom_angles = results[bottom_frame].joint_angles

        # At the squat bottom, hip and knee flexion should be significant
        assert bottom_angles.knee_flexion_l > 30.0, (
            f"Knee flexion at bottom too low: {bottom_angles.knee_flexion_l:.1f}°"
        )
        assert bottom_angles.hip_flexion_l > 20.0, (
            f"Hip flexion at bottom too low: {bottom_angles.hip_flexion_l:.1f}°"
        )

        # Trunk flexion should indicate some forward lean (< 180° = upright)
        assert bottom_angles.trunk_flexion < 180.0, (
            f"Trunk flexion should be < 180° at bottom: {bottom_angles.trunk_flexion:.1f}°"
        )

        # First frame (standing) should have low knee flexion
        standing_angles = results[0].joint_angles
        assert standing_angles.knee_flexion_l < 30.0, (
            f"Standing knee flexion too high: {standing_angles.knee_flexion_l:.1f}°"
        )

"""Tests for live pipeline → diagnosis bridge."""

from __future__ import annotations

import pytest

from biomechanics.diagnosis.bridge import (
    build_frame_from_live_pipeline,
    build_rep_kinematic_summary,
)


def _standing_kpts_mediapipe() -> list[list[float]]:
    """Realistic 19-keypoint skeleton in MediaPipe world coords (meters).

    MediaPipe convention: X=subject's left, Y=down, Z=toward camera.
    Re-centered at hip midpoint (hips average to ~0,0,0).
    Represents a standing pose with slight toe-out.
    """
    return [
        [0.00, -0.55, 0.02],   # 0  nose
        [0.02, -0.57, 0.01],   # 1  left_eye
        [-0.02, -0.57, 0.01],  # 2  right_eye
        [0.05, -0.55, -0.02],  # 3  left_ear
        [-0.05, -0.55, -0.02], # 4  right_ear
        [0.18, -0.40, 0.00],   # 5  left_shoulder
        [-0.18, -0.40, 0.00],  # 6  right_shoulder
        [0.20, -0.20, 0.05],   # 7  left_elbow
        [-0.20, -0.20, 0.05],  # 8  right_elbow
        [0.18, -0.05, 0.02],   # 9  left_wrist
        [-0.18, -0.05, 0.02],  # 10 right_wrist
        [0.10, 0.00, 0.00],    # 11 left_hip
        [-0.10, 0.00, 0.00],   # 12 right_hip
        [0.10, 0.40, 0.01],    # 13 left_knee
        [-0.10, 0.40, 0.01],   # 14 right_knee
        [0.12, 0.82, 0.00],    # 15 left_ankle
        [-0.12, 0.82, 0.00],   # 16 right_ankle
        [0.10, 0.84, 0.06],    # 17 left_foot_index (slightly forward)
        [-0.10, 0.84, 0.06],   # 18 right_foot_index
    ]


def _squat_bottom_kpts_mediapipe() -> list[list[float]]:
    """19-keypoint skeleton at squat bottom in MediaPipe world coords.

    Hips dropped close to knee height, trunk leaned forward,
    knees tracking over toes.
    """
    return [
        [0.00, -0.25, 0.20],   # 0  nose
        [0.02, -0.27, 0.19],   # 1  left_eye
        [-0.02, -0.27, 0.19],  # 2  right_eye
        [0.05, -0.25, 0.16],   # 3  left_ear
        [-0.05, -0.25, 0.16],  # 4  right_ear
        [0.18, -0.15, 0.12],   # 5  left_shoulder
        [-0.18, -0.15, 0.12],  # 6  right_shoulder
        [0.22, 0.05, 0.18],    # 7  left_elbow
        [-0.22, 0.05, 0.18],   # 8  right_elbow
        [0.20, 0.10, 0.22],    # 9  left_wrist
        [-0.20, 0.10, 0.22],   # 10 right_wrist
        [0.12, 0.00, 0.00],    # 11 left_hip
        [-0.12, 0.00, 0.00],   # 12 right_hip
        [0.12, 0.02, 0.30],    # 13 left_knee
        [-0.12, 0.02, 0.30],   # 14 right_knee
        [0.14, 0.38, 0.10],    # 15 left_ankle
        [-0.14, 0.38, 0.10],   # 16 right_ankle
        [0.12, 0.40, 0.16],    # 17 left_foot_index
        [-0.12, 0.40, 0.16],   # 18 right_foot_index
    ]


def _squat_bottom_angles() -> dict[str, float]:
    """Angles dict matching JointAngles.as_dict() at squat bottom."""
    return {
        "hip_flexion_l": 95.0,
        "hip_flexion_r": 93.0,
        "hip_adduction_l": 2.0,
        "hip_adduction_r": 1.5,
        "hip_rotation_l": 5.0,
        "hip_rotation_r": 4.0,
        "knee_flexion_l": 110.0,
        "knee_flexion_r": 108.0,
        "ankle_dorsiflexion_l": 28.0,
        "ankle_dorsiflexion_r": 26.0,
        "knee_valgus_l": 3.5,
        "knee_valgus_r": 2.0,
        "foot_confidence_l": 0.8,
        "foot_confidence_r": 0.7,
        "shoulder_flexion_l": 40.0,
        "shoulder_flexion_r": 38.0,
        "shoulder_abduction_l": 15.0,
        "shoulder_abduction_r": 14.0,
        "elbow_flexion_l": 90.0,
        "elbow_flexion_r": 88.0,
        "wrist_y_l": -10.0,
        "wrist_y_r": -10.0,
        "wrist_x_l": 5.0,
        "wrist_x_r": 5.0,
        "trunk_flexion": 145.0,
        "trunk_lateral_flexion": 1.0,
        "trunk_rotation": 2.0,
        "pelvis_tilt": 12.0,
        "pelvis_list": 0.5,
        "pelvis_rotation": 1.0,
    }


def _default_athlete_params() -> dict:
    return {
        "shoulder_width_m": 0.40,
        "hip_width_m": 0.30,
        "femur_avg_m": 0.42,
        "torso_avg_m": 0.45,
        "tibia_avg_m": 0.43,
        "foot_avg_m": 0.26,
    }


class TestBuildFrameFromLivePipeline:

    def test_angle_key_mapping(self):
        angles = _squat_bottom_angles()
        kpts = _squat_bottom_kpts_mediapipe()
        frame = build_frame_from_live_pipeline(kpts, angles)

        assert frame["angles"]["dorsi_l"] == 28.0
        assert frame["angles"]["dorsi_r"] == 26.0
        assert frame["angles"]["trunk_flexion"] == 145.0
        assert frame["angles"]["knee_valgus_l"] == 3.5
        assert frame["angles"]["knee_valgus_r"] == 2.0

    def test_knee_flex_takes_max(self):
        angles = _squat_bottom_angles()
        kpts = _squat_bottom_kpts_mediapipe()
        frame = build_frame_from_live_pipeline(kpts, angles)

        assert frame["angles"]["knee_flex"] == 110.0

    def test_coordinate_transform(self):
        kpts_mp = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts_mp, angles)
        kpts_vis = frame["kpts"]

        assert len(kpts_vis) == 19

        # vis_x = mp_z, vis_y = -mp_y, vis_z = -mp_x
        for i in range(19):
            assert kpts_vis[i][0] == pytest.approx(kpts_mp[i][2], abs=1e-9)
            assert kpts_vis[i][1] == pytest.approx(-kpts_mp[i][1], abs=1e-9)
            assert kpts_vis[i][2] == pytest.approx(-kpts_mp[i][0], abs=1e-9)

    def test_hip_y_positive_in_vis_coords(self):
        """Hip vis_y should be positive (above origin) since mp_y=0 at hip."""
        kpts_mp = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts_mp, angles)

        # Hip mp_y is 0.0, so vis_y = -0.0 = 0.0
        assert frame["kpts"][11][1] == pytest.approx(0.0, abs=1e-9)
        assert frame["kpts"][12][1] == pytest.approx(0.0, abs=1e-9)


class TestEndToEndBridgeToSummary:

    def test_produces_valid_summary(self):
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.rep_number == 1

    def test_trunk_pitch_reasonable(self):
        """trunk_pitch = 180 - trunk_flexion. At 145° flexion → 35° pitch."""
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.trunk_pitch_at_bottom == pytest.approx(35.0, abs=0.1)

    def test_dorsiflexion_passthrough(self):
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.ankle_df_l_max == pytest.approx(28.0, abs=0.1)
        assert summary.ankle_df_r_max == pytest.approx(26.0, abs=0.1)

    def test_knee_valgus_passthrough(self):
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.knee_valgus_l == pytest.approx(3.5, abs=0.1)
        assert summary.knee_valgus_r == pytest.approx(2.0, abs=0.1)

    def test_depth_class_below_parallel(self):
        """110° knee flexion → depth class 4 (below parallel, >105°)."""
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.depth_class_int == 4

    def test_stance_width_ratio_positive(self):
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.stance_width_ratio > 0.0

    def test_foot_direction_angles_positive(self):
        kpts = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts, angles)
        params = _default_athlete_params()

        summary = build_rep_kinematic_summary(frame, params, rep_number=1)

        assert summary.foot_direction_angle_l >= 0.0
        assert summary.foot_direction_angle_r >= 0.0

"""Tests for live pipeline → diagnosis bridge."""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.diagnosis.bridge import (
    build_frame_from_live_pipeline,
    build_rep_kinematic_summary,
    build_set_features,
    find_bottom_frame,
)
from biomechanics.diagnosis.rep_scoring import score_depth


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
        """Axis swap preserves relative geometry; translation is grounding."""
        kpts_mp = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts_mp, angles)
        kpts_vis = np.array(frame["kpts"])

        assert kpts_vis.shape == (19, 3)

        # vis_x = mp_z, vis_y = -mp_y, vis_z = -mp_x (up to a uniform shift)
        swapped = np.array([[p[2], -p[1], -p[0]] for p in kpts_mp])
        relative_vis = kpts_vis - kpts_vis[11]
        relative_swapped = swapped - swapped[11]
        np.testing.assert_allclose(relative_vis, relative_swapped, atol=1e-9)

    def test_hip_y_grounded_above_ankles(self):
        """Hip vis_y is ankle-relative height, not hip-centered zero.

        MediaPipe world coords put the origin at the hip midpoint; the
        bridge must re-ground so hip height is measured from the floor.
        """
        kpts_mp = _squat_bottom_kpts_mediapipe()
        angles = _squat_bottom_angles()
        frame = build_frame_from_live_pipeline(kpts_mp, angles)

        # mp hips at y=0, ankles at y=0.38 → grounded hip height = 0.38 m
        assert frame["kpts"][11][1] == pytest.approx(0.38, abs=1e-9)
        assert frame["kpts"][12][1] == pytest.approx(0.38, abs=1e-9)
        min_ankle_y = min(frame["kpts"][15][1], frame["kpts"][16][1])
        assert min_ankle_y == pytest.approx(0.0, abs=1e-9)


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


class TestLiveFrameGrounding:

    def test_standing_frame_grounded_independently(self):
        """Each frame grounds to its own ankle Y, so hip heights compare across frames."""
        frame = build_frame_from_live_pipeline(
            _squat_bottom_kpts_mediapipe(),
            _squat_bottom_angles(),
            standing_kpts=_standing_kpts_mediapipe(),
        )
        standing_vis = frame["standing_kpts"]

        min_ankle_y = min(standing_vis[15][1], standing_vis[16][1])
        assert min_ankle_y == pytest.approx(0.0, abs=1e-9)
        # mp standing: hips at y=0, ankles at y=0.82 → hip height 0.82 m
        assert standing_vis[11][1] == pytest.approx(0.82, abs=1e-9)

    def test_hip_mid_centered_in_xz(self):
        """A global XZ offset in camera coords must not survive the transform."""
        kpts_offset = [
            [x + 0.3, y, z + 0.5] for x, y, z in _squat_bottom_kpts_mediapipe()
        ]
        frame = build_frame_from_live_pipeline(kpts_offset, _squat_bottom_angles())
        kpts_vis = frame["kpts"]

        hip_mid_x = (kpts_vis[11][0] + kpts_vis[12][0]) / 2.0
        hip_mid_z = (kpts_vis[11][2] + kpts_vis[12][2]) / 2.0
        assert hip_mid_x == pytest.approx(0.0, abs=1e-9)
        assert hip_mid_z == pytest.approx(0.0, abs=1e-9)

    def test_depth_score_meaningful_from_live_frames(self):
        """Standing hip 0.82 m, bottom hip 0.38 m, bottom knee 0.36 m
        → depth = (82 - 38) / (82 - 36). Was ~0 before grounding."""
        frame = build_frame_from_live_pipeline(
            _squat_bottom_kpts_mediapipe(),
            _squat_bottom_angles(),
            standing_kpts=_standing_kpts_mediapipe(),
        )
        summary = build_rep_kinematic_summary(
            frame, _default_athlete_params(), rep_number=1,
        )

        depth = score_depth(summary, {}, {})
        assert depth == pytest.approx((82.0 - 38.0) / (82.0 - 36.0), abs=0.01)


def _valid_frame() -> dict:
    return build_frame_from_live_pipeline(
        _squat_bottom_kpts_mediapipe(), _squat_bottom_angles(),
    )


class TestFindBottomFrame:

    def test_skips_none_frames(self):
        valid = _valid_frame()
        assert find_bottom_frame([None, valid, None]) is valid

    def test_all_none_returns_none(self):
        assert find_bottom_frame([None, None]) is None

    def test_empty_returns_none(self):
        assert find_bottom_frame([]) is None


class TestBuildSetFeaturesEdgeCases:

    def test_degenerate_reps_skipped(self):
        replay_reps = [[], [None, None], [_valid_frame()]]
        features = build_set_features(
            replay_reps, _default_athlete_params(),
            baseline={"peakDorsi": 35.0, "peakKneeFlex": 120.0},
        )
        assert len(features.per_rep_kinematics) == 1

    def test_does_not_mutate_caller_frames(self):
        frame = _valid_frame()
        build_set_features(
            [[frame]], _default_athlete_params(),
            baseline={"peakDorsi": 35.0, "peakKneeFlex": 120.0},
        )
        assert "standing_kpts" not in frame

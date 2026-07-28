"""Integration tests for the pre-IK filter chain.

Drives the real chain, in production order, over synthetic frames in the
production Y-down coordinate frame. Every filter here passed its own unit
tests while the assembled chain destroyed the skeleton and left both
calibrators permanently uncalibrated, so these tests assert on the chain's
end-to-end outcome rather than any single stage.
"""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.ground_clamp import GroundClamp
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.preik_chain import apply_preik_filters
from biomechanics.utils.standing_gate import StandingPoseGate
from biomechanics.utils.types import Skeleton3D, CocoKeypoints as CK
from biomechanics.utils.velocity_clamp import VelocityClamp

# Production frame is Y-down: a keypoint that is physically higher has a
# smaller y. Hips at the origin, feet below at positive y.
HIP_Y = 0.0
KNEE_Y = 0.45
ANKLE_Y = 0.90
SHOULDER_Y = -0.50

FEMUR_LENGTH_M = KNEE_Y - HIP_Y
TIBIA_LENGTH_M = ANKLE_Y - KNEE_Y
TORSO_LENGTH_M = HIP_Y - SHOULDER_Y

POSITION_TOL_M = 0.02
BONE_TOL_M = 0.01


def _standing_points_y_down() -> np.ndarray:
    points = np.zeros((19, 3))
    points[CK.NOSE] = [0.0, -0.70, 0.0]
    points[CK.LEFT_EYE] = [0.03, -0.72, -0.02]
    points[CK.RIGHT_EYE] = [-0.03, -0.72, -0.02]
    points[CK.LEFT_EAR] = [0.07, -0.70, 0.0]
    points[CK.RIGHT_EAR] = [-0.07, -0.70, 0.0]
    points[CK.LEFT_SHOULDER] = [0.20, SHOULDER_Y, 0.0]
    points[CK.RIGHT_SHOULDER] = [-0.20, SHOULDER_Y, 0.0]
    points[CK.LEFT_ELBOW] = [0.25, -0.25, 0.0]
    points[CK.RIGHT_ELBOW] = [-0.25, -0.25, 0.0]
    points[CK.LEFT_WRIST] = [0.25, 0.0, 0.0]
    points[CK.RIGHT_WRIST] = [-0.25, 0.0, 0.0]
    points[CK.LEFT_HIP] = [0.12, HIP_Y, 0.0]
    points[CK.RIGHT_HIP] = [-0.12, HIP_Y, 0.0]
    points[CK.LEFT_KNEE] = [0.12, KNEE_Y, 0.0]
    points[CK.RIGHT_KNEE] = [-0.12, KNEE_Y, 0.0]
    points[CK.LEFT_ANKLE] = [0.12, ANKLE_Y, 0.0]
    points[CK.RIGHT_ANKLE] = [-0.12, ANKLE_Y, 0.0]
    points[CK.LEFT_FOOT_INDEX] = [0.12, ANKLE_Y + 0.02, 0.12]
    points[CK.RIGHT_FOOT_INDEX] = [-0.12, ANKLE_Y + 0.02, 0.12]
    return points


def _make_skeleton(points: np.ndarray, frame_index: int) -> Skeleton3D:
    return Skeleton3D.from_numpy(
        points,
        confidences=np.ones(len(points)),
        timestamp=frame_index / 30.0,
        frame_index=frame_index,
    )


def _build_chain(
    bone_calibration_frames: int = 30,
    ground_calibration_frames: int = 30,
    required_standing_frames: int = 5,
) -> dict:
    gate = StandingPoseGate(
        min_confidence=0.5,
        required_consecutive_frames=required_standing_frames,
    )
    return {
        "gate": gate,
        "filters": {
            "confidence_blender": ConfidenceBlender(
                min_confidence=0.1, max_confidence=0.9,
            ),
            "velocity_clamp": VelocityClamp(
                max_velocity_m_per_s=2.5, target_fps=30,
            ),
            "bone_constraints": BoneLengthConstraints(
                calibration_frames=bone_calibration_frames,
                tolerance=0.0,
                standing_gate=gate,
            ),
            "ground_clamp": GroundClamp(
                calibration_frames=ground_calibration_frames,
                standing_gate=gate,
            ),
            "position_smoother": KeypointPositionSmoother(
                min_cutoff=0.8, beta=4.0, d_cutoff=1.0,
            ),
        },
    }


def _run_standing_frames(chain: dict, frame_count: int) -> Skeleton3D:
    """Feed still standing frames through the chain the way the pipeline does."""
    points = _standing_points_y_down()
    skeleton = _make_skeleton(points, frame_index=0)
    for frame_index in range(frame_count):
        skeleton = _make_skeleton(points, frame_index=frame_index)
        chain["gate"].check(skeleton)
        skeleton = apply_preik_filters(skeleton, **chain["filters"])
    return skeleton


class TestCalibrationCompletes:

    def test_standing_gate_latches(self):
        chain = _build_chain()
        _run_standing_frames(chain, 10)
        assert chain["gate"].is_ready

    def test_gate_latches_at_exactly_required_frames(self):
        """The chain must not advance the gate — only the caller does."""
        chain = _build_chain(required_standing_frames=5)
        _run_standing_frames(chain, 4)
        assert not chain["gate"].is_ready
        assert chain["gate"].progress == (4, 5)

        _run_standing_frames(chain, 1)
        assert chain["gate"].is_ready

    def test_bone_calibration_completes(self):
        chain = _build_chain(bone_calibration_frames=30, required_standing_frames=5)
        _run_standing_frames(chain, 100)
        bone_constraints = chain["filters"]["bone_constraints"]
        assert bone_constraints.is_calibrated
        assert bone_constraints.body_proportions is not None

    def test_ground_calibration_completes(self):
        chain = _build_chain(ground_calibration_frames=30, required_standing_frames=5)
        _run_standing_frames(chain, 100)
        assert chain["filters"]["ground_clamp"].is_calibrated

    def test_calibrated_bone_lengths_match_input(self):
        chain = _build_chain()
        _run_standing_frames(chain, 100)
        proportions = chain["filters"]["bone_constraints"].body_proportions
        assert proportions.femur_length_avg == pytest.approx(
            FEMUR_LENGTH_M, abs=BONE_TOL_M,
        )
        assert proportions.tibia_length_avg == pytest.approx(
            TIBIA_LENGTH_M, abs=BONE_TOL_M,
        )
        assert proportions.torso_length_avg == pytest.approx(
            TORSO_LENGTH_M, abs=BONE_TOL_M,
        )


class TestSkeletonIsNotCorrupted:

    def test_still_standing_pose_survives_the_chain(self):
        """A still, anatomically perfect pose must come out ~unchanged."""
        chain = _build_chain()
        original = _standing_points_y_down()
        filtered = _run_standing_frames(chain, 100).to_numpy()

        for name, keypoint in (
            ("left_hip", CK.LEFT_HIP), ("right_hip", CK.RIGHT_HIP),
            ("left_knee", CK.LEFT_KNEE), ("right_knee", CK.RIGHT_KNEE),
            ("left_ankle", CK.LEFT_ANKLE), ("right_ankle", CK.RIGHT_ANKLE),
            ("left_shoulder", CK.LEFT_SHOULDER), ("right_shoulder", CK.RIGHT_SHOULDER),
        ):
            moved = float(np.linalg.norm(filtered[keypoint] - original[keypoint]))
            assert moved < POSITION_TOL_M, (
                f"{name} moved {moved * 100:.1f} cm through the chain"
            )

    def test_ankles_stay_below_knees(self):
        """The fold signature: ankles driven up to or above knee height."""
        chain = _build_chain()
        filtered = _run_standing_frames(chain, 100).to_numpy()
        for knee, ankle in (
            (CK.LEFT_KNEE, CK.LEFT_ANKLE),
            (CK.RIGHT_KNEE, CK.RIGHT_ANKLE),
        ):
            # Y-down: below means a larger y.
            assert filtered[ankle][1] > filtered[knee][1]

    def test_legs_do_not_cross(self):
        chain = _build_chain()
        filtered = _run_standing_frames(chain, 100).to_numpy()
        assert filtered[CK.LEFT_ANKLE][0] > filtered[CK.RIGHT_ANKLE][0]

    def test_bone_lengths_preserved(self):
        chain = _build_chain()
        filtered = _run_standing_frames(chain, 100).to_numpy()

        for proximal, distal, expected in (
            (CK.LEFT_HIP, CK.LEFT_KNEE, FEMUR_LENGTH_M),
            (CK.RIGHT_HIP, CK.RIGHT_KNEE, FEMUR_LENGTH_M),
            (CK.LEFT_KNEE, CK.LEFT_ANKLE, TIBIA_LENGTH_M),
            (CK.RIGHT_KNEE, CK.RIGHT_ANKLE, TIBIA_LENGTH_M),
        ):
            length = float(np.linalg.norm(filtered[distal] - filtered[proximal]))
            assert length == pytest.approx(expected, abs=BONE_TOL_M)

    def test_leg_extension_preserved(self):
        """Hip-to-ankle vertical span must stay near full leg length."""
        chain = _build_chain()
        filtered = _run_standing_frames(chain, 100).to_numpy()
        hip_mid_y = (filtered[CK.LEFT_HIP][1] + filtered[CK.RIGHT_HIP][1]) / 2.0
        leg_length = FEMUR_LENGTH_M + TIBIA_LENGTH_M

        for ankle in (CK.LEFT_ANKLE, CK.RIGHT_ANKLE):
            span = abs(float(filtered[ankle][1]) - hip_mid_y)
            assert span / leg_length > 0.9


class TestPipelineWiring:

    def test_rom_clamp_is_not_in_the_chain(self):
        """ROMClamp folded the legs on every frame. It stays out until it has
        per-user calibrated ROM and its own tests."""
        import inspect

        from biomechanics import pipeline
        from biomechanics.utils import preik_chain

        assert "rom_clamp" not in inspect.getsource(preik_chain).lower()
        assert "romclamp" not in inspect.getsource(pipeline).lower()

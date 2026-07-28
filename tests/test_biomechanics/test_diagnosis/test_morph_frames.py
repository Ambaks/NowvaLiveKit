"""Tests for corrected-pose morph frames.

Morph frames used to linearly interpolate joint positions. Interpolating the
endpoints of a rotating limb cuts the chord of the arc, so bones shrink
mid-morph and every intermediate frame the athlete sees is a skeleton that
cannot exist. These pin the bone lengths and the endpoints of the taper.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from biomechanics.diagnosis.keypoint_corrector import (
    KINEMATIC_BONES,
    build_morph_frames,
    rotate_about_axis,
    slerp_unit,
    HIP_L,
    HIP_R,
)

NUM_FRAMES = 60
LENGTH_TOL_M = 1e-9
POSITION_TOL_M = 1e-9

MEASURED_BONES = {
    "thigh_l": (HIP_L, 13),
    "shank_l": (13, 15),
    "foot_l": (15, 17),
    "thigh_r": (HIP_R, 14),
    "shank_r": (14, 16),
    "torso_l": (HIP_L, 5),
    "torso_r": (HIP_R, 6),
    "upper_arm_l": (5, 7),
    "forearm_l": (7, 9),
    "pelvis": (HIP_L, HIP_R),
}


def _squat_pose() -> np.ndarray:
    points = np.zeros((19, 3))
    points[11] = [-0.12, 0.75, 0.0]
    points[12] = [0.12, 0.75, 0.0]
    points[13] = [-0.15, 0.45, 0.18]
    points[14] = [0.15, 0.45, 0.18]
    points[15] = [-0.15, 0.06, 0.0]
    points[16] = [0.15, 0.06, 0.0]
    points[17] = [-0.15, 0.0, 0.20]
    points[18] = [0.15, 0.0, 0.20]
    points[5] = [-0.20, 1.25, 0.0]
    points[6] = [0.20, 1.25, 0.0]
    points[7] = [-0.24, 0.99, 0.05]
    points[8] = [0.24, 0.99, 0.05]
    points[9] = [-0.26, 0.75, 0.10]
    points[10] = [0.26, 0.75, 0.10]
    points[0] = [0.0, 1.47, 0.02]
    points[1] = [-0.03, 1.50, 0.0]
    points[2] = [0.03, 1.50, 0.0]
    points[3] = [-0.07, 1.48, 0.0]
    points[4] = [0.07, 1.48, 0.0]
    return points


def _rotate_all_bones(
    pose: np.ndarray, angle_deg: float, axis: np.ndarray,
) -> np.ndarray:
    """A correction that rotates every bone, so lengths are exactly preserved.

    This is the invariant KeypointCorrector.correct() itself maintains, so any
    length change through the morph is an interpolation artifact.
    """
    out = pose.copy()
    axis = axis / np.linalg.norm(axis)
    angle_rad = math.radians(angle_deg)

    pelvis = (pose[HIP_L] + pose[HIP_R]) / 2.0
    for hip in (HIP_L, HIP_R):
        out[hip] = pelvis + rotate_about_axis(pose[hip] - pelvis, axis, angle_rad)
    for parent, child in KINEMATIC_BONES:
        out[child] = out[parent] + rotate_about_axis(
            pose[child] - pose[parent], axis, angle_rad,
        )
    return out


def _bone_length(pose: np.ndarray, bone: tuple[int, int]) -> float:
    return float(np.linalg.norm(pose[bone[1]] - pose[bone[0]]))


class TestSlerpUnit:

    def test_midpoint_is_halfway_along_the_arc(self):
        start = np.array([1.0, 0.0, 0.0])
        end = np.array([0.0, 1.0, 0.0])
        mid = slerp_unit(start, end, 0.5)
        assert np.linalg.norm(mid) == pytest.approx(1.0, abs=1e-9)
        assert mid[0] == pytest.approx(mid[1], abs=1e-9)

    def test_stays_on_the_unit_sphere(self):
        start = np.array([1.0, 0.0, 0.0])
        end = np.array([0.0, 0.6, 0.8])
        for weight in np.linspace(0.0, 1.0, 21):
            result = slerp_unit(start, end, float(weight))
            assert np.linalg.norm(result) == pytest.approx(1.0, abs=1e-9)

    def test_identical_vectors_are_stable(self):
        vector = np.array([0.0, 1.0, 0.0])
        np.testing.assert_allclose(slerp_unit(vector, vector, 0.5), vector)

    def test_antiparallel_vectors_do_not_produce_nan(self):
        start = np.array([0.0, 1.0, 0.0])
        result = slerp_unit(start, -start, 0.5)
        assert np.all(np.isfinite(result))
        assert np.linalg.norm(result) == pytest.approx(1.0, abs=1e-9)


class TestBoneLengthsThroughMorph:

    @pytest.fixture
    def frames(self) -> list[np.ndarray]:
        observed = _squat_pose()
        corrected = _rotate_all_bones(observed, 35.0, np.array([1.0, 0.3, 0.0]))
        return [
            np.array(frame)
            for frame in build_morph_frames(
                observed.tolist(), corrected.tolist(), NUM_FRAMES,
            )
        ]

    def test_every_bone_holds_its_length_in_every_frame(self, frames):
        observed = _squat_pose()
        for name, bone in MEASURED_BONES.items():
            expected = _bone_length(observed, bone)
            for index, frame in enumerate(frames):
                actual = _bone_length(frame, bone)
                assert actual == pytest.approx(expected, abs=LENGTH_TOL_M), (
                    f"{name} was {actual:.4f} m at frame {index}, "
                    f"expected {expected:.4f} m"
                )

    def test_frame_count_matches_request(self, frames):
        assert len(frames) == NUM_FRAMES

    def test_frames_are_finite(self, frames):
        for frame in frames:
            assert np.all(np.isfinite(frame))


class TestTaperEndpoints:

    def test_first_frame_is_the_observed_pose(self):
        """The Gaussian taper used to start at weight 0.044, so the frame
        presented as 'this is you' was already part-way corrected."""
        observed = _squat_pose()
        corrected = _rotate_all_bones(observed, 30.0, np.array([1.0, 0.0, 0.0]))
        first = np.array(
            build_morph_frames(observed.tolist(), corrected.tolist(), NUM_FRAMES)[0]
        )
        np.testing.assert_allclose(first, observed, atol=POSITION_TOL_M)

    def test_peak_frame_reaches_the_corrected_pose(self):
        observed = _squat_pose()
        corrected = _rotate_all_bones(observed, 30.0, np.array([1.0, 0.0, 0.0]))
        frames = [
            np.array(frame)
            for frame in build_morph_frames(
                observed.tolist(), corrected.tolist(), NUM_FRAMES,
            )
        ]
        closest = min(
            float(np.abs(frame - corrected).max()) for frame in frames
        )
        assert closest < 1e-6

    def test_morph_returns_to_the_observed_pose(self):
        observed = _squat_pose()
        corrected = _rotate_all_bones(observed, 30.0, np.array([1.0, 0.0, 0.0]))
        last = np.array(
            build_morph_frames(observed.tolist(), corrected.tolist(), NUM_FRAMES)[-1]
        )
        assert float(np.abs(last - observed).max()) < 0.01

    def test_identical_poses_produce_no_motion(self):
        observed = _squat_pose()
        for frame in build_morph_frames(
            observed.tolist(), observed.tolist(), NUM_FRAMES,
        ):
            np.testing.assert_allclose(
                np.array(frame), observed, atol=POSITION_TOL_M,
            )

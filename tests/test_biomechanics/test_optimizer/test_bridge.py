"""Tests for Prompt 3: adapter, angle extraction, fault rules, and rep-segmenter integration."""

import sys
import json
from collections import deque
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.skeleton.forward_kin import (
    forward_kinematics,
    load_reference_point,
    midfoot_xz,
)
from biomechanics.optimizer.ik import fit_frame, fit_trajectory
from biomechanics.optimizer.landmark_adapter import skeleton3d_to_landmarks
from biomechanics.optimizer.angle_extract import q_to_joint_angles
from biomechanics.utils.types import Skeleton3D, Point3D, JointAngles
from biomechanics.faults.rules.limited_dorsiflexion import LimitedDorsiflexionRule
from biomechanics.faults.rules.bar_drift import BarDriftRule
from biomechanics.analysis.rep_segmenter import segment_set

from .synth_fixtures import (
    generate_landmarks_from_q,
    _make_clean_squat_q,
    _make_bad_squat_q,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURE_DIR / f"{name}.json") as f:
        return json.load(f)


def _make_skeleton() -> SkeletonModel:
    return scale_skeleton(1.78, 80.0)


# ---------------------------------------------------------------------------
# Skeleton3D ↔ landmarks adapter
# ---------------------------------------------------------------------------


class TestLandmarkAdapter:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def _skeleton3d_from_fk(self, skeleton: SkeletonModel, q: np.ndarray) -> Skeleton3D:
        """Build a fake Skeleton3D (19 COCO keypoints, Y-down) from FK positions.

        The adapter expects Y-down MediaPipe coords, so we negate Y from
        the Y-up FK output to simulate what the pipeline would provide.
        """
        xforms = forward_kinematics(skeleton, q)
        pos = {name: T[:3, 3] for name, T in xforms.items()}

        # Map skeleton joints → COCO indices (fill unused with zeros)
        coco_pts: list[Point3D] = []
        for _ in range(19):
            coco_pts.append(Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0))

        pelvis = (pos["L_hip"] + pos["R_hip"]) / 2
        shoulder = pos["trunk"]  # trunk joint ≈ shoulder midpoint

        mapping = {
            5: (shoulder, 0.9),  # L shoulder ≈ trunk offset left
            6: (shoulder, 0.9),  # R shoulder ≈ trunk offset right
            11: (pos["L_hip"], 0.95),
            12: (pos["R_hip"], 0.95),
            13: (pos["L_knee"], 0.92),
            14: (pos["R_knee"], 0.92),
            15: (pos["L_ankle"], 0.88),
            16: (pos["R_ankle"], 0.88),
        }

        for idx, (p, conf) in mapping.items():
            # Negate Y to convert Y-up → Y-down (simulate MediaPipe output)
            coco_pts[idx] = Point3D(x=float(p[0]), y=float(-p[1]), z=float(p[2]), confidence=conf)

        return Skeleton3D(keypoints=coco_pts, timestamp=0.0, frame_index=0)

    def test_output_shape(self, skeleton):
        q = skeleton.neutral_q()
        skel3d = self._skeleton3d_from_fk(skeleton, q)
        lm = skeleton3d_to_landmarks(skel3d)
        assert lm.shape == (8, 4)

    def test_y_flipped_to_positive(self, skeleton):
        """Pelvis should be at positive Y (above ground) after Y-flip."""
        q = skeleton.neutral_q()
        skel3d = self._skeleton3d_from_fk(skeleton, q)
        lm = skeleton3d_to_landmarks(skel3d)
        # Pelvis Y should be positive (above ground) in Y-up
        assert lm[0, 1] > 0.0, f"pelvis Y = {lm[0, 1]}"

    def test_x_flipped_to_skeleton_left_negative(self):
        """MediaPipe left-positive X should become skeleton left-negative X."""
        pts = [Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0) for _ in range(19)]
        pts[11] = Point3D(x=0.12, y=-1.0, z=0.0, confidence=1.0)
        pts[12] = Point3D(x=-0.12, y=-1.0, z=0.0, confidence=1.0)
        pts[5] = Point3D(x=0.10, y=-1.4, z=0.0, confidence=1.0)
        pts[6] = Point3D(x=-0.10, y=-1.4, z=0.0, confidence=1.0)
        pts[13] = Point3D(x=0.12, y=-0.6, z=0.0, confidence=1.0)
        pts[14] = Point3D(x=-0.12, y=-0.6, z=0.0, confidence=1.0)
        pts[15] = Point3D(x=0.12, y=-0.1, z=0.0, confidence=1.0)
        pts[16] = Point3D(x=-0.12, y=-0.1, z=0.0, confidence=1.0)

        lm = skeleton3d_to_landmarks(Skeleton3D(keypoints=pts))

        assert lm[2, 0] == pytest.approx(-0.12)
        assert lm[3, 0] == pytest.approx(0.12)

    def test_trunk_landmark_interpolates_to_t12_l1(self):
        """The model trunk joint is below the shoulder midpoint."""
        pts = [Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0) for _ in range(19)]
        for idx in (11, 12):
            pts[idx] = Point3D(x=0.0, y=-1.0, z=0.0, confidence=1.0)
        for idx in (5, 6):
            pts[idx] = Point3D(x=0.0, y=-1.5, z=0.0, confidence=1.0)
        for idx in (13, 14):
            pts[idx] = Point3D(x=0.0, y=-0.6, z=0.0, confidence=1.0)
        for idx in (15, 16):
            pts[idx] = Point3D(x=0.0, y=-0.1, z=0.0, confidence=1.0)

        lm = skeleton3d_to_landmarks(Skeleton3D(keypoints=pts))

        assert lm[1, 1] == pytest.approx(1.29)
        assert lm[1, 1] < 1.5

    def test_confidence_propagated(self, skeleton):
        q = skeleton.neutral_q()
        skel3d = self._skeleton3d_from_fk(skeleton, q)
        lm = skeleton3d_to_landmarks(skel3d)
        # L_hip (index 2) should carry confidence from COCO left_hip
        assert lm[2, 3] > 0.0
        # Pelvis (index 0) should carry min of L/R hip confidence
        assert lm[0, 3] == min(
            skel3d.keypoints[11].confidence,
            skel3d.keypoints[12].confidence,
        )

    def test_roundtrip_positions(self, skeleton):
        """Adapter output should place joints close to FK positions."""
        q = skeleton.neutral_q()
        xforms = forward_kinematics(skeleton, q)
        fk_pelvis = (xforms["L_hip"][:3, 3] + xforms["R_hip"][:3, 3]) / 2

        skel3d = self._skeleton3d_from_fk(skeleton, q)
        lm = skeleton3d_to_landmarks(skel3d)

        np.testing.assert_allclose(lm[0, :3], fk_pelvis, atol=1e-6)

    def test_adapter_then_fit_frame(self, skeleton):
        """Landmarks from the adapter should be consumable by fit_frame."""
        q_true = skeleton.neutral_q()
        skel3d = self._skeleton3d_from_fk(skeleton, q_true)
        lm = skeleton3d_to_landmarks(skel3d)
        q_fit = fit_frame(skeleton, lm, q_init=skeleton.neutral_q())
        assert q_fit.shape == (skeleton.n_dof,)


# ---------------------------------------------------------------------------
# q → JointAngles extraction
# ---------------------------------------------------------------------------


class TestAngleExtraction:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def test_neutral_pose_angles(self, skeleton):
        """At neutral (standing), hip/knee flexion ≈ 0, trunk flexion ≈ 180."""
        q = skeleton.neutral_q()
        angles = q_to_joint_angles(skeleton, q)
        assert abs(angles.hip_flexion_l) < 5.0
        assert abs(angles.hip_flexion_r) < 5.0
        assert abs(angles.knee_flexion_l) < 5.0
        assert abs(angles.knee_flexion_r) < 5.0
        assert angles.trunk_flexion > 170.0

    def test_deep_squat_angles(self, skeleton):
        """Clean squat at bottom should show high hip/knee flexion."""
        data = _load_fixture("synth_clean_squat")
        q_traj = np.array(data["q_trajectory"])
        mid = q_traj.shape[0] // 2
        angles = q_to_joint_angles(skeleton, q_traj[mid])

        assert angles.hip_flexion_l > 50.0, f"hip_flex_l = {angles.hip_flexion_l}"
        assert angles.knee_flexion_l > 60.0, f"knee_flex_l = {angles.knee_flexion_l}"
        assert angles.ankle_dorsiflexion_l > 10.0, f"dorsi_l = {angles.ankle_dorsiflexion_l}"

    def test_bad_squat_limited_dorsiflexion(self, skeleton):
        """Bad squat fixture has limited dorsiflexion (15° max)."""
        data = _load_fixture("synth_bad_squat")
        q_traj = np.array(data["q_trajectory"])
        mid = q_traj.shape[0] // 2
        angles = q_to_joint_angles(skeleton, q_traj[mid])

        # Bad fixture uses 15° max dorsiflexion
        assert angles.ankle_dorsiflexion_l < 25.0, f"dorsi_l = {angles.ankle_dorsiflexion_l}"

    def test_symmetry_in_clean_squat(self, skeleton):
        """Clean squat should have symmetric L/R angles."""
        data = _load_fixture("synth_clean_squat")
        q_traj = np.array(data["q_trajectory"])
        mid = q_traj.shape[0] // 2
        angles = q_to_joint_angles(skeleton, q_traj[mid])

        assert abs(angles.hip_flexion_l - angles.hip_flexion_r) < 2.0
        assert abs(angles.knee_flexion_l - angles.knee_flexion_r) < 2.0
        assert abs(angles.ankle_dorsiflexion_l - angles.ankle_dorsiflexion_r) < 2.0

    def test_all_analytical_fields_present(self, skeleton):
        """q_to_joint_angles should populate the same fields as AnalyticalIKSolver."""
        q = skeleton.neutral_q()
        angles = q_to_joint_angles(skeleton, q)

        required = [
            "hip_flexion_l", "hip_flexion_r",
            "knee_flexion_l", "knee_flexion_r",
            "ankle_dorsiflexion_l", "ankle_dorsiflexion_r",
            "trunk_flexion", "trunk_lateral_flexion",
            "pelvis_tilt", "pelvis_list",
            "knee_valgus_l", "knee_valgus_r",
            "hip_adduction_l", "hip_adduction_r",
        ]
        angle_dict = angles.as_dict()
        for field in required:
            assert field in angle_dict, f"missing field: {field}"

    def test_trunk_flexion_convention(self, skeleton):
        """Forward lean should decrease trunk_flexion below 180."""
        q = skeleton.neutral_q()
        q[skeleton.dof_index("trunk", "rx")] = np.radians(30)
        angles = q_to_joint_angles(skeleton, q)
        assert angles.trunk_flexion < 170.0


# ---------------------------------------------------------------------------
# Limited dorsiflexion fault rule
# ---------------------------------------------------------------------------


class TestLimitedDorsiflexionRule:
    def _make_angles(self, dorsi_l: float, dorsi_r: float, frame: int = 0) -> JointAngles:
        return JointAngles(
            ankle_dorsiflexion_l=dorsi_l,
            ankle_dorsiflexion_r=dorsi_r,
            frame_index=frame,
        )

    def test_no_fault_good_mobility(self):
        rule = LimitedDorsiflexionRule(threshold=25.0)
        history: deque = deque(maxlen=30)
        # Simulate rep with good dorsiflexion
        for i in range(30):
            phase = np.exp(-((i - 15) / 7.5) ** 2)
            a = self._make_angles(30.0 * phase, 30.0 * phase, i)
            rule.evaluate(a, history, in_rep=True, rep_number=1)
        # End rep
        result = rule.evaluate(self._make_angles(0, 0, 30), history, in_rep=False, rep_number=1)
        assert result is None

    def test_fault_limited_mobility(self):
        rule = LimitedDorsiflexionRule(threshold=25.0, mild_threshold=20.0)
        history: deque = deque(maxlen=30)
        # Simulate rep with limited dorsiflexion (max 15°)
        for i in range(30):
            phase = np.exp(-((i - 15) / 7.5) ** 2)
            a = self._make_angles(15.0 * phase, 15.0 * phase, i)
            rule.evaluate(a, history, in_rep=True, rep_number=1)
        result = rule.evaluate(self._make_angles(0, 0, 30), history, in_rep=False, rep_number=1)
        assert result is not None
        assert result.fault_type == "limited_dorsiflexion"

    def test_severity_clamped_to_moderate(self):
        rule = LimitedDorsiflexionRule(threshold=25.0, mild_threshold=20.0, moderate_threshold=15.0)
        history: deque = deque(maxlen=30)
        # Very bad mobility (max 5°) — should still be capped at MODERATE
        for i in range(30):
            a = self._make_angles(5.0, 5.0, i)
            rule.evaluate(a, history, in_rep=True, rep_number=1)
        result = rule.evaluate(self._make_angles(0, 0, 30), history, in_rep=False, rep_number=1)
        assert result is not None
        assert result.severity.value in ("mild", "moderate")


# ---------------------------------------------------------------------------
# Bar drift fault rule
# ---------------------------------------------------------------------------


class TestBarDriftRule:
    def test_no_fault_balanced(self):
        rule = BarDriftRule(mild_threshold=5.0)
        history: deque = deque(maxlen=30)
        angles = JointAngles()
        # Simulate balanced rep: load ref and midfoot at same xz
        for i in range(30):
            rule.set_frame_context(skeleton_state={
                "load_reference_xz": np.array([0.0, 0.0]),
                "midfoot_xz": np.array([0.0, 0.0]),
            })
            rule.evaluate(angles, history, in_rep=True, rep_number=1)
        rule.set_frame_context(skeleton_state=None)
        result = rule.evaluate(angles, history, in_rep=False, rep_number=1)
        assert result is None

    def test_fault_forward_drift(self):
        rule = BarDriftRule(mild_threshold=5.0)
        history: deque = deque(maxlen=30)
        angles = JointAngles()
        # Simulate rep with 12cm forward drift
        for i in range(30):
            rule.set_frame_context(skeleton_state={
                "load_reference_xz": np.array([0.0, 0.12]),
                "midfoot_xz": np.array([0.0, 0.0]),
            })
            rule.evaluate(angles, history, in_rep=True, rep_number=1)
        rule.set_frame_context(skeleton_state=None)
        result = rule.evaluate(angles, history, in_rep=False, rep_number=1)
        assert result is not None
        assert result.fault_type == "bar_drift"
        assert result.details["drift_cm"] >= 10.0

    def test_no_fault_without_skeleton_state(self):
        rule = BarDriftRule()
        history: deque = deque(maxlen=30)
        angles = JointAngles()
        for i in range(30):
            rule.evaluate(angles, history, in_rep=True, rep_number=1)
        result = rule.evaluate(angles, history, in_rep=False, rep_number=1)
        assert result is None


# ---------------------------------------------------------------------------
# Rep segmenter integration with optimizer IK path
# ---------------------------------------------------------------------------


class TestRepSegmenterIntegration:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    def _hip_signal_from_q(
        self, skeleton: SkeletonModel, q_traj: np.ndarray, fps: float
    ) -> dict:
        """Extract hip position time series from q trajectory for the rep segmenter."""
        T = q_traj.shape[0]
        timestamps = np.arange(T) / fps
        hip_pos = np.zeros(T)

        for t in range(T):
            xforms = forward_kinematics(skeleton, q_traj[t])
            pelvis_y = xforms["pelvis"][:3, 3][1]
            l_ankle_y = xforms["L_ankle"][:3, 3][1]
            r_ankle_y = xforms["R_ankle"][:3, 3][1]
            ankle_y = (l_ankle_y + r_ankle_y) / 2
            # Negate to match pipeline convention: more negative = standing
            hip_pos[t] = -(pelvis_y - ankle_y) * 100.0

        velocity = np.gradient(hip_pos, timestamps)

        return {
            "timestamps": timestamps.tolist(),
            "hip_position_cm": hip_pos.tolist(),
            "hip_velocity_cm_s": velocity.tolist(),
        }

    def test_segmenter_finds_rep_in_clean_squat(self, skeleton):
        """fit_trajectory → FK hip signal → segment_set should find 1 rep."""
        data = _load_fixture("synth_clean_squat")
        landmarks = np.array(data["landmarks"])
        fps = data["fps"]

        q_traj = fit_trajectory(skeleton, landmarks, smooth_sigma=1.0)
        signal = self._hip_signal_from_q(skeleton, q_traj, fps)
        result = segment_set(signal, min_depth_cm=5.0)

        assert result["total_reps"] >= 1, f"expected ≥1 rep, got {result['total_reps']}"

    def test_segmenter_finds_rep_in_bad_squat(self, skeleton):
        """Bad squat fixture should also produce a valid rep."""
        data = _load_fixture("synth_bad_squat")
        landmarks = np.array(data["landmarks"])
        fps = data["fps"]

        q_traj = fit_trajectory(skeleton, landmarks, smooth_sigma=1.0)
        signal = self._hip_signal_from_q(skeleton, q_traj, fps)
        result = segment_set(signal, min_depth_cm=5.0)

        assert result["total_reps"] >= 1

    def test_rep_depth_is_positive(self, skeleton):
        """Detected rep should have positive depth_cm."""
        data = _load_fixture("synth_clean_squat")
        landmarks = np.array(data["landmarks"])
        fps = data["fps"]

        q_traj = fit_trajectory(skeleton, landmarks, smooth_sigma=1.0)
        signal = self._hip_signal_from_q(skeleton, q_traj, fps)
        result = segment_set(signal, min_depth_cm=5.0)

        if result["total_reps"] > 0:
            assert result["reps"][0]["depth_cm"] > 0

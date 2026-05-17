"""Proportional response test — THE gate for the what-if optimizer.

Invariants checked:
1. Small perturbation  → small change in q_corrected vs q_fitted
2. Large perturbation  → large change
3. Change is monotonically increasing with perturbation magnitude
4. Corrected pose satisfies hard constraints (feet rooted, COM in polygon)
5. q_corrected converts to JointAngles via q_to_joint_angles()
6. Each correction improves biomechanical cost vs the uncorrected perturbation
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.optimizer.ik import _fk_jac, _build_descendants
from biomechanics.optimizer.costs import (
    _com_from_pos,
    _support_bounds,
    cost_torque_proxy,
    cost_load_over_midfoot,
    cost_knee_tracking,
)
from biomechanics.optimizer.whatif import whatif_solve
from biomechanics.optimizer.angle_extract import q_to_joint_angles


def _make_skeleton() -> SkeletonModel:
    return scale_skeleton(1.78, 80.0)


def _bottom_squat_q(skeleton: SkeletonModel) -> np.ndarray:
    """Deep squat pose (bottom of rep)."""
    q = skeleton.neutral_q()
    q[skeleton.dof_index("L_hip", "rx")] = np.radians(100)
    q[skeleton.dof_index("R_hip", "rx")] = np.radians(100)
    q[skeleton.dof_index("L_knee", "rx")] = np.radians(120)
    q[skeleton.dof_index("R_knee", "rx")] = np.radians(120)
    q[skeleton.dof_index("L_ankle", "rx")] = np.radians(30)
    q[skeleton.dof_index("R_ankle", "rx")] = np.radians(30)
    q[skeleton.dof_index("trunk", "rx")] = np.radians(40)
    q[1] -= 0.35
    return q


# Perturbation magnitudes (radians) — trunk forward lean
_DELTAS_RAD = [np.radians(2), np.radians(5), np.radians(10)]


class TestProportionalResponse:
    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    @pytest.fixture
    def q_fitted(self, skeleton):
        return _bottom_squat_q(skeleton)

    @pytest.fixture
    def corrections(self, skeleton, q_fitted):
        """Run the optimizer at three perturbation magnitudes."""
        results = []
        for delta in _DELTAS_RAD:
            perturbation = {"trunk.rx": delta}
            q_corr = whatif_solve(skeleton, q_fitted, perturbation)
            results.append(q_corr)
        return results

    # ── 1-3. Proportionality and monotonicity ──

    def test_monotonic_change_with_perturbation(self, q_fitted, corrections):
        """||q_corr - q_fitted|| must increase monotonically with perturbation."""
        norms = [np.linalg.norm(qc - q_fitted) for qc in corrections]
        for i in range(len(norms) - 1):
            assert norms[i + 1] > norms[i], (
                f"non-monotonic: delta[{i}]→{norms[i]:.6f}, "
                f"delta[{i+1}]→{norms[i+1]:.6f}"
            )

    def test_small_perturbation_small_change(self, q_fitted, corrections):
        """Smallest perturbation should produce a modest change."""
        norm = np.linalg.norm(corrections[0] - q_fitted)
        assert norm < 0.5, f"small perturbation moved q by {norm:.4f} — too large"

    def test_large_perturbation_larger_change(self, q_fitted, corrections):
        """Largest perturbation must move q more than the smallest one."""
        n_small = np.linalg.norm(corrections[0] - q_fitted)
        n_large = np.linalg.norm(corrections[-1] - q_fitted)
        assert n_large > n_small

    # ── 4. Hard-constraint satisfaction ──

    def test_feet_rooted(self, skeleton, q_fitted, corrections):
        """Ankle world positions must stay within tolerance of the fitted pose."""
        desc = _build_descendants(skeleton)
        pos_ref, _ = _fk_jac(skeleton, q_fitted, desc)
        lai = skeleton.joint_index("L_ankle")
        rai = skeleton.joint_index("R_ankle")
        for qc in corrections:
            pos_c, _ = _fk_jac(skeleton, qc, desc)
            np.testing.assert_allclose(
                pos_c[lai], pos_ref[lai], atol=5e-3,
                err_msg="L_ankle moved",
            )
            np.testing.assert_allclose(
                pos_c[rai], pos_ref[rai], atol=5e-3,
                err_msg="R_ankle moved",
            )

    def test_com_inside_support_polygon(self, skeleton, q_fitted, corrections):
        """COM (xz) must stay inside the support polygon."""
        desc = _build_descendants(skeleton)
        pos0, _ = _fk_jac(skeleton, q_fitted, desc)
        x_min, x_max, z_min, z_max = _support_bounds(skeleton, pos0)
        for qc in corrections:
            pos_c, _ = _fk_jac(skeleton, qc, desc)
            com = _com_from_pos(skeleton, pos_c)
            assert com[0] >= x_min - 1e-3, f"COM.x={com[0]:.4f} < x_min={x_min:.4f}"
            assert com[0] <= x_max + 1e-3, f"COM.x={com[0]:.4f} > x_max={x_max:.4f}"
            assert com[2] >= z_min - 1e-3, f"COM.z={com[2]:.4f} < z_min={z_min:.4f}"
            assert com[2] <= z_max + 1e-3, f"COM.z={com[2]:.4f} > z_max={z_max:.4f}"

    # ── 5. q_to_joint_angles compatibility ──

    def test_corrected_q_to_joint_angles(self, skeleton, corrections):
        """Every corrected q must convert to a valid JointAngles."""
        for qc in corrections:
            angles = q_to_joint_angles(skeleton, qc)
            assert angles.hip_flexion_l is not None
            assert angles.knee_flexion_l is not None
            assert angles.ankle_dorsiflexion_l is not None
            assert angles.trunk_flexion is not None

    # ── 6. Biomechanical improvement ──

    def test_correction_improves_biomechanics(self, skeleton, q_fitted):
        """Corrected pose should have lower biomech cost than uncorrected perturbation."""
        delta = np.radians(8)
        q_perturbed = q_fitted.copy()
        q_perturbed[skeleton.dof_index("trunk", "rx")] += delta

        q_corrected = whatif_solve(skeleton, q_fitted, {"trunk.rx": delta})

        # Sum non-deviation costs (torque + load + knee tracking)
        def biomech_cost(q):
            c1, _ = cost_torque_proxy(skeleton, q)
            c2, _ = cost_load_over_midfoot(skeleton, q)
            c3, _ = cost_knee_tracking(skeleton, q)
            return c1 + c2 + c3

        cost_raw = biomech_cost(q_perturbed)
        cost_fixed = biomech_cost(q_corrected)
        assert cost_fixed <= cost_raw + 1e-6, (
            f"correction worsened cost: {cost_fixed:.6f} > {cost_raw:.6f}"
        )


class TestProportionalResponsePelvisTilt:
    """Proportional response with pelvis forward-tilt perturbation."""

    @pytest.fixture
    def skeleton(self):
        return _make_skeleton()

    @pytest.fixture
    def q_fitted(self, skeleton):
        return _bottom_squat_q(skeleton)

    def test_monotonic_pelvis_perturbation(self, skeleton, q_fitted):
        deltas = [np.radians(2), np.radians(5), np.radians(10)]
        norms = []
        for d in deltas:
            qc = whatif_solve(skeleton, q_fitted, {"pelvis.rx": d})
            norms.append(np.linalg.norm(qc - q_fitted))

        for i in range(len(norms) - 1):
            assert norms[i + 1] > norms[i], (
                f"non-monotonic pelvis tilt response: {norms}"
            )

    def test_perturbed_dof_locked(self, skeleton, q_fitted):
        """Perturbed DOF should stay near its perturbed value."""
        delta = np.radians(5)
        qc = whatif_solve(skeleton, q_fitted, {"pelvis.rx": delta})
        idx = skeleton.dof_index("pelvis", "rx")
        expected = q_fitted[idx] + delta
        assert abs(qc[idx] - expected) < np.radians(1), (
            f"pelvis.rx drifted: expected {expected:.4f}, got {qc[idx]:.4f}"
        )

"""Tests for keypoint corrector symmetry enforcement and balance lean."""

from __future__ import annotations

import math

import numpy as np
import pytest

from biomechanics.diagnosis.keypoint_corrector import (
    ANKLE_L,
    ANKLE_R,
    DEFAULT_FOOT_LEN_M,
    FOOT_L,
    FOOT_R,
    HIP_L,
    HIP_R,
    KNEE_L,
    KNEE_R,
    UPPER_BODY_INDICES,
    KeypointCorrector,
    apply_lean_to_upper_body,
    compute_balance_target_ground,
    compute_com_ground,
    solve_balance_lean,
)
from biomechanics.diagnosis.types import (
    DiagnosisResult,
    HypothesizedCause,
)

SYMMETRY_TOL = 1e-6


def _make_19pt_skeleton(
    hip_y_l: float = 0.50,
    hip_y_r: float = 0.50,
    knee_y_l: float = 0.30,
    knee_y_r: float = 0.30,
    ankle_y_l: float = 0.0,
    ankle_y_r: float = 0.0,
    hip_z_offset: float = 0.15,
    knee_z_offset: float = 0.13,
    ankle_z_offset: float = 0.15,
) -> np.ndarray:
    """Build a 19-keypoint skeleton with controllable L/R asymmetry."""
    kpts = np.zeros((19, 3))

    kpts[0] = [0.0, 1.6, 0.0]
    kpts[5] = [0.0, 1.2, -0.18]
    kpts[6] = [0.0, 1.2, 0.18]
    kpts[7] = [0.15, 1.0, -0.20]
    kpts[8] = [0.15, 1.0, 0.20]
    kpts[9] = [0.25, 0.85, -0.20]
    kpts[10] = [0.25, 0.85, 0.20]

    kpts[HIP_L] = [0.0, hip_y_l, -hip_z_offset]
    kpts[HIP_R] = [0.0, hip_y_r, hip_z_offset]
    kpts[KNEE_L] = [0.10, knee_y_l, -knee_z_offset]
    kpts[KNEE_R] = [0.10, knee_y_r, knee_z_offset]
    kpts[ANKLE_L] = [0.0, ankle_y_l, -ankle_z_offset]
    kpts[ANKLE_R] = [0.0, ankle_y_r, ankle_z_offset]
    kpts[FOOT_L] = [0.15, ankle_y_l, -ankle_z_offset]
    kpts[FOOT_R] = [0.15, ankle_y_r, ankle_z_offset]

    return kpts


def _lateral_distance(kpt: np.ndarray, midpoint: np.ndarray, lat_unit: np.ndarray) -> float:
    return float(np.dot(kpt - midpoint, lat_unit))


def _make_diagnosis(cause_ids: list[str]) -> DiagnosisResult:
    causes = []
    for cid in cause_ids:
        delta: dict = {}
        if cid == "narrow_stance":
            delta = {"__foot_target_delta": [0.0, 0.0, -0.03, 0.0, 0.0, 0.03]}
        elif cid == "narrow_foot_angle":
            delta = {"L_ankle.ry": 0.15, "R_ankle.ry": -0.15}
        elif cid == "knee_track_cue":
            delta = {"L_hip.ry": -0.08, "R_hip.ry": 0.08}
        elif cid == "weight_shift_cue":
            delta = {"pelvis.tx": 0.02}
        causes.append(
            HypothesizedCause(
                cause_id=cid,
                tier=1,
                score=0.8,
                evidence_score=0.7,
                prior=0.3,
                implicated_by=["test"],
                parameter_delta=delta,
                explanation="test",
            )
        )
    return DiagnosisResult(
        set_id="test",
        detected_symptoms=[],
        immediate_causes=causes,
        session_causes=[],
        longterm_causes=[],
        contextual_notes=[],
        combined_perturbation={},
        confidence=0.8,
    )


class TestEnforceSymmetry:

    def test_symmetric_input_unchanged(self) -> None:
        kpts = _make_19pt_skeleton()
        corrector = KeypointCorrector()

        before = kpts.copy()
        corrector._enforce_symmetry(kpts)

        np.testing.assert_allclose(kpts[HIP_L:FOOT_R + 1], before[HIP_L:FOOT_R + 1], atol=1e-6)

    def test_asymmetric_hip_heights_equalized(self) -> None:
        kpts = _make_19pt_skeleton(hip_y_l=0.52, hip_y_r=0.48)
        corrector = KeypointCorrector()

        corrector._enforce_symmetry(kpts)

        assert kpts[HIP_L][1] == pytest.approx(kpts[HIP_R][1], abs=SYMMETRY_TOL)

    def test_asymmetric_ankle_heights_equalized(self) -> None:
        kpts = _make_19pt_skeleton(ankle_y_l=0.02, ankle_y_r=-0.01)
        corrector = KeypointCorrector()

        corrector._enforce_symmetry(kpts)

        assert kpts[ANKLE_L][1] == pytest.approx(kpts[ANKLE_R][1], abs=SYMMETRY_TOL)

    def test_lateral_distances_mirrored(self) -> None:
        kpts = _make_19pt_skeleton(hip_y_l=0.52, hip_y_r=0.48)
        corrector = KeypointCorrector()

        corrector._enforce_symmetry(kpts)

        hip_lateral = kpts[HIP_R] - kpts[HIP_L]
        hip_lateral[1] = 0.0
        lat_unit = hip_lateral / np.linalg.norm(hip_lateral)

        for l_idx, r_idx in [(HIP_L, HIP_R), (ANKLE_L, ANKLE_R), (FOOT_L, FOOT_R)]:
            mid = (kpts[l_idx] + kpts[r_idx]) / 2.0
            dist_l = abs(_lateral_distance(kpts[l_idx], mid, lat_unit))
            dist_r = abs(_lateral_distance(kpts[r_idx], mid, lat_unit))
            assert dist_l == pytest.approx(dist_r, abs=SYMMETRY_TOL)

    def test_bone_lengths_symmetric_after_enforcement(self) -> None:
        kpts = _make_19pt_skeleton(hip_y_l=0.55, hip_y_r=0.45)
        corrector = KeypointCorrector()

        corrector._enforce_symmetry(kpts)

        thigh_l_after = np.linalg.norm(kpts[KNEE_L] - kpts[HIP_L])
        shin_l_after = np.linalg.norm(kpts[ANKLE_L] - kpts[KNEE_L])
        thigh_r_after = np.linalg.norm(kpts[KNEE_R] - kpts[HIP_R])
        shin_r_after = np.linalg.norm(kpts[ANKLE_R] - kpts[KNEE_R])

        assert thigh_l_after == pytest.approx(thigh_r_after, abs=1e-4)
        assert shin_l_after == pytest.approx(shin_r_after, abs=1e-4)

    def test_knee_heights_symmetric_after_enforcement(self) -> None:
        kpts = _make_19pt_skeleton(
            hip_y_l=0.55, hip_y_r=0.45,
            knee_y_l=0.35, knee_y_r=0.25,
        )
        corrector = KeypointCorrector()

        corrector._enforce_symmetry(kpts)

        assert kpts[KNEE_L][1] == pytest.approx(kpts[KNEE_R][1], abs=1e-3)

    def test_knee_tracks_over_toes(self) -> None:
        kpts = _make_19pt_skeleton(
            hip_y_l=0.55, hip_y_r=0.55,
            knee_y_l=0.30, knee_y_r=0.30,
        )
        # Cave right knee inward to create asymmetry
        kpts[KNEE_R][2] = 0.05
        corrector = KeypointCorrector()

        corrector._enforce_symmetry(kpts)

        for knee_idx, ankle_idx, foot_idx in [
            (KNEE_L, ANKLE_L, FOOT_L),
            (KNEE_R, ANKLE_R, FOOT_R),
        ]:
            shin_xz = kpts[knee_idx] - kpts[ankle_idx]
            shin_xz[1] = 0.0
            foot_xz = kpts[foot_idx] - kpts[ankle_idx]
            foot_xz[1] = 0.0

            shin_len = np.linalg.norm(shin_xz)
            foot_len = np.linalg.norm(foot_xz)
            if shin_len < 1e-9 or foot_len < 1e-9:
                continue

            cross_y = np.cross(shin_xz, foot_xz)[1]
            assert abs(cross_y) == pytest.approx(0.0, abs=0.01)
            assert np.dot(shin_xz, foot_xz) > 0

    def test_dorsiflexion_capped(self) -> None:
        kpts = _make_19pt_skeleton(
            hip_y_l=0.40, hip_y_r=0.40,
            knee_y_l=0.25, knee_y_r=0.25,
        )
        # Push knees far forward to create high dorsiflexion
        kpts[KNEE_L][0] = 0.30
        kpts[KNEE_R][0] = 0.30
        corrector = KeypointCorrector()
        max_dorsi_deg = 30.0

        corrector._enforce_symmetry(kpts, max_dorsi_deg=max_dorsi_deg)

        import math
        for knee_idx, ankle_idx in [(KNEE_L, ANKLE_L), (KNEE_R, ANKLE_R)]:
            dorsi = corrector._compute_dorsiflexion(kpts[knee_idx], kpts[ankle_idx])
            assert math.degrees(dorsi) <= max_dorsi_deg + 0.5

    def test_dorsiflexion_capped_negative_x_lean(self) -> None:
        """Dorsi cap must work when shin leans in -X (real squat geometry)."""
        kpts = _make_19pt_skeleton(
            hip_y_l=0.40, hip_y_r=0.40,
            knee_y_l=0.25, knee_y_r=0.25,
        )
        kpts[KNEE_L][0] = -0.30
        kpts[KNEE_R][0] = -0.30
        corrector = KeypointCorrector()
        max_dorsi_deg = 30.0

        corrector._enforce_symmetry(kpts, max_dorsi_deg=max_dorsi_deg)

        import math
        for knee_idx, ankle_idx in [(KNEE_L, ANKLE_L), (KNEE_R, ANKLE_R)]:
            dorsi = corrector._compute_dorsiflexion(kpts[knee_idx], kpts[ankle_idx])
            assert math.degrees(dorsi) <= max_dorsi_deg + 0.5


class TestCorrectIntegrationSymmetry:

    def test_corrected_output_is_symmetric(self) -> None:
        kpts = _make_19pt_skeleton(
            hip_y_l=0.53, hip_y_r=0.47,
            knee_y_l=0.32, knee_y_r=0.28,
        )
        diagnosis = _make_diagnosis(["narrow_stance", "knee_track_cue"])

        corrector = KeypointCorrector()
        result = corrector.correct(kpts.tolist(), diagnosis)

        assert result is not None
        out = np.array(result)

        assert out[HIP_L][1] == pytest.approx(out[HIP_R][1], abs=1e-4)
        assert out[ANKLE_L][1] == pytest.approx(out[ANKLE_R][1], abs=1e-4)
        assert out[KNEE_L][1] == pytest.approx(out[KNEE_R][1], abs=1e-3)


class TestLateralComCentering:

    def test_lateral_trunk_lean_centers_com_over_target(self) -> None:
        """With a weight-shift cue, the COM ground projection must land on the
        mid-foot balance target along the lateral axis, even when the captured
        trunk leans sideways."""
        kpts = _make_19pt_skeleton()
        for idx in UPPER_BODY_INDICES:
            kpts[idx][2] += 0.08

        diagnosis = _make_diagnosis(["weight_shift_cue"])
        corrector = KeypointCorrector()

        result = corrector.correct(kpts.tolist(), diagnosis)

        assert result is not None
        out = np.array(result)

        com = compute_com_ground(out, DEFAULT_FOOT_LEN_M)
        target = compute_balance_target_ground(out, DEFAULT_FOOT_LEN_M)

        hip_lateral = out[HIP_R] - out[HIP_L]
        lat_xz = np.array([hip_lateral[0], hip_lateral[2]])
        lat_xz /= np.linalg.norm(lat_xz)

        gap_lateral = abs(float(np.dot(target - com, lat_xz)))
        assert gap_lateral <= 0.004

    def test_symmetric_pose_barely_moves(self) -> None:
        """A laterally balanced capture needs no lateral shift."""
        kpts = _make_19pt_skeleton()
        diagnosis = _make_diagnosis(["weight_shift_cue"])
        corrector = KeypointCorrector()

        result = corrector.correct(kpts.tolist(), diagnosis)

        assert result is not None
        out = np.array(result)
        hip_mid_z_before = (kpts[HIP_L][2] + kpts[HIP_R][2]) / 2.0
        hip_mid_z_after = (out[HIP_L][2] + out[HIP_R][2]) / 2.0
        assert hip_mid_z_after == pytest.approx(hip_mid_z_before, abs=0.005)


class TestBalanceLean:

    def test_rotation_preserves_relative_distances(self) -> None:
        kpts = _make_19pt_skeleton()
        lean_rad = math.radians(15.0)

        before_dists = []
        for i in UPPER_BODY_INDICES:
            for j in UPPER_BODY_INDICES:
                if i < j:
                    before_dists.append(np.linalg.norm(kpts[i] - kpts[j]))

        result = apply_lean_to_upper_body(kpts, lean_rad)

        after_dists = []
        for i in UPPER_BODY_INDICES:
            for j in UPPER_BODY_INDICES:
                if i < j:
                    after_dists.append(np.linalg.norm(result[i] - result[j]))

        np.testing.assert_allclose(before_dists, after_dists, atol=1e-10)

    def test_rotation_tilts_head_forward(self) -> None:
        kpts = _make_19pt_skeleton()
        hip_mid_x = (kpts[HIP_L][0] + kpts[HIP_R][0]) / 2.0
        hip_mid_y = (kpts[HIP_L][1] + kpts[HIP_R][1]) / 2.0
        nose_dy_before = kpts[0][1] - hip_mid_y

        lean_rad = math.radians(10.0)
        result = apply_lean_to_upper_body(kpts, lean_rad)

        nose_dx_after = result[0][0] - hip_mid_x
        nose_dy_after = result[0][1] - hip_mid_y
        nose_dx_before = kpts[0][0] - hip_mid_x

        assert nose_dx_after > nose_dx_before
        assert nose_dy_after < nose_dy_before

    def test_balance_solve_converges(self) -> None:
        kpts = _make_19pt_skeleton()
        foot_len = 0.29

        lean = solve_balance_lean(kpts, foot_len)

        assert lean is not None
        assert math.isfinite(lean)
        assert abs(math.degrees(lean)) < 30.0

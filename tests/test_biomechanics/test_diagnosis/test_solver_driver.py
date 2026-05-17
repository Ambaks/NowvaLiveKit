"""Tests for FormSolverDriver: convergence, relaxation, and V1 cost config."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.diagnosis.solver_driver import FormSolverDriver, V1_COST_WEIGHTS
from biomechanics.diagnosis.types import (
    DiagnosisResult,
    DetectedSymptom,
    HypothesizedCause,
)


def _make_skeleton():
    return scale_skeleton(1.78, 80.0)


def _squat_q(skeleton, phase=0.7):
    q = skeleton.neutral_q()
    q[skeleton.dof_index("L_hip", "rx")] = np.radians(100 * phase)
    q[skeleton.dof_index("R_hip", "rx")] = np.radians(100 * phase)
    q[skeleton.dof_index("L_knee", "rx")] = np.radians(120 * phase)
    q[skeleton.dof_index("R_knee", "rx")] = np.radians(120 * phase)
    q[skeleton.dof_index("L_ankle", "rx")] = np.radians(30 * phase)
    q[skeleton.dof_index("R_ankle", "rx")] = np.radians(30 * phase)
    q[skeleton.dof_index("trunk", "rx")] = np.radians(40 * phase)
    q[1] -= 0.35 * phase
    return q


def _make_diagnosis(perturbation: dict) -> DiagnosisResult:
    return DiagnosisResult(
        set_id="test_set",
        detected_symptoms=[
            DetectedSymptom(symptom_id="excessive_trunk_lean", severity=0.6, contributing_reps=[2]),
        ],
        immediate_causes=[
            HypothesizedCause(
                cause_id="bracing_failure",
                tier=1,
                score=0.7,
                evidence_score=0.8,
                prior=0.3,
                implicated_by=["excessive_trunk_lean"],
                parameter_delta=perturbation,
                explanation="test",
            ),
        ],
        session_causes=[],
        longterm_causes=[],
        contextual_notes=[],
        combined_perturbation=perturbation,
        confidence=0.6,
    )


class TestFormSolverDriver:
    def test_solve_with_small_perturbation_converges(self):
        skeleton = _make_skeleton()
        q_bottom = _squat_q(skeleton, phase=0.7)
        perturbation = {"trunk.rx": -0.05}
        diagnosis = _make_diagnosis(perturbation)

        driver = FormSolverDriver(skeleton)
        result = driver.solve(q_bottom, diagnosis, anthro={})

        assert result.converged is True
        assert len(result.q_corrected) == skeleton.n_dof
        assert result.relaxations == []
        q_corrected = np.array(result.q_corrected)
        assert not np.allclose(q_corrected, q_bottom, atol=1e-4)

    def test_v1_cost_weights_exclude_torque_proxy(self):
        skeleton = _make_skeleton()
        driver = FormSolverDriver(skeleton)
        assert "torque_proxy" not in driver.cost_weights or driver.cost_weights["torque_proxy"] == 0.0

    def test_cost_terms_used_excludes_torque_proxy(self):
        skeleton = _make_skeleton()
        q_bottom = _squat_q(skeleton, phase=0.7)
        perturbation = {"trunk.rx": -0.03}
        diagnosis = _make_diagnosis(perturbation)

        driver = FormSolverDriver(skeleton)
        result = driver.solve(q_bottom, diagnosis, anthro={})

        assert "torque_proxy" not in result.cost_terms_used
        assert "pose_deviation" in result.cost_terms_used
        assert "load_over_midfoot" in result.cost_terms_used

    def test_foot_target_delta_passed_through(self):
        skeleton = _make_skeleton()
        q_bottom = _squat_q(skeleton, phase=0.7)
        perturbation = {"__foot_target_delta": [-0.02, 0.0, 0.0, 0.02, 0.0, 0.0]}
        diagnosis = _make_diagnosis(perturbation)

        driver = FormSolverDriver(skeleton)
        result = driver.solve(q_bottom, diagnosis, anthro={})

        assert "__foot_target_delta" in result.applied_perturbation

    def test_empty_perturbation_converges(self):
        skeleton = _make_skeleton()
        q_bottom = _squat_q(skeleton, phase=0.7)
        diagnosis = _make_diagnosis({})

        driver = FormSolverDriver(skeleton)
        result = driver.solve(q_bottom, diagnosis, anthro={})

        assert result.converged is True
        assert len(result.q_corrected) == skeleton.n_dof

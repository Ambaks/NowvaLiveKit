"""Tests for the on-demand "show me that" demo and last-rep replay.

The pipeline stores rep keypoints in the MediaPipe world frame (Y-down)
while the demo builder and viewer both work in viewer coords (Y-up), so
these guard the transform and the fault-highlight vocabulary.
"""

from __future__ import annotations

import numpy as np
import pytest

from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.coaching.session_tracker import SessionTracker
from biomechanics.faults.fault_types import FaultType
from biomechanics.viz.demo_ws_bridge import FAULT_HIGHLIGHT_JOINTS, HIGHLIGHT_JOINTS

HIP_L, HIP_R = 11, 12
ANKLE_L, ANKLE_R = 15, 16


class _NullClient:
    def send_message(self, message: dict) -> None:
        pass


def _viewer_squat_pose() -> np.ndarray:
    """A plausible squat bottom in viewer coords: Y-up, feet grounded."""
    kpts = np.zeros((21, 3))
    kpts[5] = [0.18, 0.95, 0.05]
    kpts[6] = [-0.18, 0.95, 0.05]
    kpts[HIP_L] = [0.10, 0.55, 0.0]
    kpts[HIP_R] = [-0.10, 0.55, 0.0]
    kpts[13] = [0.12, 0.30, 0.18]
    kpts[14] = [-0.12, 0.30, 0.18]
    kpts[ANKLE_L] = [0.13, 0.06, 0.0]
    kpts[ANKLE_R] = [-0.13, 0.06, 0.0]
    kpts[17] = [0.14, 0.02, 0.16]
    kpts[18] = [-0.14, 0.02, 0.16]
    kpts[19] = [0.13, 0.02, -0.05]
    kpts[20] = [-0.13, 0.02, -0.05]
    return kpts


def _to_mediapipe_frame(viewer: np.ndarray) -> list[list[float]]:
    """Invert viewer=[mp_z, -mp_y, -mp_x] back to the frame the pipeline stores."""
    return np.column_stack([-viewer[:, 2], -viewer[:, 1], viewer[:, 0]]).tolist()


class TestOnDemandDemoCoordinateFrame:
    def test_observed_pose_is_converted_to_viewer_coords(self, monkeypatch):
        """Without the transform build_demo_data rejects every pose."""
        tracker = SessionTracker(IPCBridge(_NullClient()))
        tracker._athlete_params = {
            "shoulder_width_m": 0.40, "femur_avg_m": 0.45, "tibia_avg_m": 0.40,
        }
        tracker._baseline = {"peakDorsi": 25.0}
        tracker._rep_kinematic_buffer = [object()]
        tracker._last_rep_bottom_kpts = _to_mediapipe_frame(_viewer_squat_pose())

        captured: dict = {}

        class _Diagnosis:
            immediate_causes = [object()]

        class _Engine:
            def diagnose(self, features):
                return _Diagnosis()

        def _fake_build_demo_data(observed, diagnosis, anthro, rom):
            captured["observed"] = np.asarray(observed)
            return "demo"

        monkeypatch.setattr("biomechanics.coaching.session_tracker.SetFeatures",
                            lambda **kw: None)
        monkeypatch.setattr("biomechanics.coaching.session_tracker.HypothesisEngine", _Engine)
        monkeypatch.setattr("biomechanics.coaching.session_tracker.build_demo_data",
                            _fake_build_demo_data)

        assert tracker.build_on_demand_demo() == "demo"

        observed = captured["observed"]
        hip_y = (observed[HIP_L, 1] + observed[HIP_R, 1]) / 2
        ankle_y = (observed[ANKLE_L, 1] + observed[ANKLE_R, 1]) / 2
        assert hip_y > ankle_y, "hips must sit above ankles — pose is not Y-up"

    def test_returns_none_without_rep_data(self):
        tracker = SessionTracker(IPCBridge(_NullClient()))
        assert tracker.build_on_demand_demo() is None


class TestFaultHighlightVocabulary:
    def test_every_key_is_a_real_fault_type(self):
        valid = {f.value for f in FaultType}
        assert set(FAULT_HIGHLIGHT_JOINTS).issubset(valid)

    def test_the_faults_that_fire_during_squats_are_covered(self):
        for fault in ("knee_valgus", "forward_lean", "depth", "bilateral_asymmetry"):
            assert FAULT_HIGHLIGHT_JOINTS.get(fault), f"{fault} has no highlight joints"

    def test_cause_ids_and_fault_types_are_disjoint(self):
        """They are separate vocabularies — matching one against the other
        is what made replay highlighting silently dead."""
        assert not set(HIGHLIGHT_JOINTS) & set(FAULT_HIGHLIGHT_JOINTS)

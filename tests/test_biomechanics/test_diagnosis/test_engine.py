"""End-to-end tests for HypothesisEngine.diagnose()."""

import pytest

from biomechanics.diagnosis import HypothesisEngine, SetFeatures, RepKinematicSummary
from biomechanics.diagnosis.types import DiagnosisResult


NORMAL_ANTHRO = {
    "femur_torso_ratio": 1.0,
    "femur_length_avg": 0.45,
    "tibia_length_avg": 0.43,
    "torso_length": 0.45,
    "hip_width": 0.30,
    "shoulder_width": 0.40,
}

NORMAL_ROM = {
    "dorsiflexion_drop": 35.0,
    "avg_depth": 120.0,
    "trunk_flexion": 60.0,
    "hip_adduction": 15.0,
    "asymmetry": 5.0,
}


def _make_rep(rep_number: int = 1, **overrides) -> RepKinematicSummary:
    defaults = {
        "rep_number": rep_number,
        "trunk_pitch_at_bottom": 35.0,
        "knee_valgus_l": 3.0,
        "knee_valgus_r": 3.0,
        "ankle_df_l_max": 25.0,
        "ankle_df_r_max": 25.0,
        "hip_y_l_at_bottom": 38.0,
        "hip_y_r_at_bottom": 38.0,
        "knee_y_l_at_bottom": 42.0,
        "knee_y_r_at_bottom": 42.0,
        "stance_width_ratio": 1.0,
        "foot_direction_angle_l": 20.0,
        "foot_direction_angle_r": 20.0,
        "depth_class_int": 3,
    }
    defaults.update(overrides)
    return RepKinematicSummary(**defaults)


class TestAnkleLimitedLifter:
    """Scenario: limited ankle DF, narrow stance, shallow depth."""

    @pytest.fixture
    def diagnosis(self) -> DiagnosisResult:
        engine = HypothesisEngine()
        reps = [
            _make_rep(
                rep_number=i,
                trunk_pitch_at_bottom=48.0,
                ankle_df_l_max=33.0,
                ankle_df_r_max=32.0,
                stance_width_ratio=0.65,
                foot_direction_angle_l=10.0,
                foot_direction_angle_r=10.0,
                hip_y_l_at_bottom=44.0,
                hip_y_r_at_bottom=44.0,
                knee_y_l_at_bottom=42.0,
                knee_y_r_at_bottom=42.0,
                depth_class_int=2,
            )
            for i in range(1, 6)
        ]
        features = SetFeatures(
            user_id=1,
            set_id="test_ankle_limited",
            rep_count=5,
            per_rep_kinematics=reps,
            anthropometry=NORMAL_ANTHRO,
            rom=NORMAL_ROM,
        )
        return engine.diagnose(features)

    def test_returns_diagnosis_result(self, diagnosis):
        assert isinstance(diagnosis, DiagnosisResult)

    def test_detects_excessive_trunk_lean(self, diagnosis):
        symptom_ids = [s.symptom_id for s in diagnosis.detected_symptoms]
        assert "excessive_trunk_lean" in symptom_ids

    def test_detects_depth_limit(self, diagnosis):
        symptom_ids = [s.symptom_id for s in diagnosis.detected_symptoms]
        assert "depth_limit" in symptom_ids

    def test_limited_ankle_df_in_longterm_causes(self, diagnosis):
        cause_ids = [c.cause_id for c in diagnosis.longterm_causes]
        assert "limited_ankle_df" in cause_ids

    def test_narrow_stance_in_immediate_causes(self, diagnosis):
        cause_ids = [c.cause_id for c in diagnosis.immediate_causes]
        assert "narrow_stance" in cause_ids

    def test_immediate_causes_have_perturbations(self, diagnosis):
        for cause in diagnosis.immediate_causes:
            assert cause.parameter_delta is not None

    def test_combined_perturbation_not_empty(self, diagnosis):
        assert len(diagnosis.combined_perturbation) > 0

    def test_combined_perturbation_keys_are_valid(self, diagnosis):
        valid_joint_axes = {
            "pelvis.tx", "pelvis.ty", "pelvis.tz",
            "pelvis.rx", "pelvis.ry", "pelvis.rz",
            "trunk.rx", "trunk.rz",
            "L_hip.rx", "L_hip.ry", "L_hip.rz",
            "R_hip.rx", "R_hip.ry", "R_hip.rz",
            "L_knee.rx", "R_knee.rx",
            "L_ankle.rx", "L_ankle.ry",
            "R_ankle.rx", "R_ankle.ry",
            "__foot_target_delta",
        }
        for key in diagnosis.combined_perturbation:
            assert key in valid_joint_axes, f"Invalid perturbation key: {key}"


class TestLongFemurLifter:
    """Scenario: high femur/torso ratio causing structural trunk lean."""

    @pytest.fixture
    def diagnosis(self) -> DiagnosisResult:
        engine = HypothesisEngine()
        long_femur_anthro = {**NORMAL_ANTHRO, "femur_torso_ratio": 1.2}
        # Trunk lean is high but proportional to their anatomy
        # The expected lean for ratio 1.2 is ~54°, so 50° is within expected
        # We set it higher than expected to trigger the symptom
        reps = [
            _make_rep(
                rep_number=i,
                trunk_pitch_at_bottom=62.0,
                stance_width_ratio=1.0,
                foot_direction_angle_l=20.0,
                foot_direction_angle_r=20.0,
                depth_class_int=3,
            )
            for i in range(1, 4)
        ]
        features = SetFeatures(
            user_id=2,
            set_id="test_long_femur",
            rep_count=3,
            per_rep_kinematics=reps,
            anthropometry=long_femur_anthro,
            rom=NORMAL_ROM,
        )
        return engine.diagnose(features)

    def test_returns_diagnosis_result(self, diagnosis):
        assert isinstance(diagnosis, DiagnosisResult)

    def test_femur_ratio_in_contextual_notes(self, diagnosis):
        cause_ids = [c.cause_id for c in diagnosis.contextual_notes]
        assert "anthropometric_femur_torso_ratio" in cause_ids

    def test_contextual_cause_has_no_perturbation(self, diagnosis):
        for cause in diagnosis.contextual_notes:
            if cause.cause_id == "anthropometric_femur_torso_ratio":
                assert cause.parameter_delta is None


class TestValgusUnderLoad:
    """Scenario: progressive knee valgus suggesting weakness."""

    @pytest.fixture
    def diagnosis(self) -> DiagnosisResult:
        engine = HypothesisEngine()
        reps = [
            _make_rep(
                rep_number=i,
                knee_valgus_l=8.0 + i * 1.5,
                knee_valgus_r=7.0 + i * 1.5,
                stance_width_ratio=1.0,
                foot_direction_angle_l=22.0,
                foot_direction_angle_r=22.0,
                depth_class_int=3,
            )
            for i in range(1, 6)
        ]
        features = SetFeatures(
            user_id=3,
            set_id="test_valgus",
            rep_count=5,
            per_rep_kinematics=reps,
            anthropometry=NORMAL_ANTHRO,
            rom=NORMAL_ROM,
        )
        return engine.diagnose(features)

    def test_returns_diagnosis_result(self, diagnosis):
        assert isinstance(diagnosis, DiagnosisResult)

    def test_detects_knee_not_tracking(self, diagnosis):
        symptom_ids = [s.symptom_id for s in diagnosis.detected_symptoms]
        assert "knee_not_tracking_toes" in symptom_ids

    def test_weak_hip_abductors_in_longterm(self, diagnosis):
        cause_ids = [c.cause_id for c in diagnosis.longterm_causes]
        assert "weak_hip_abductors" in cause_ids

    def test_knee_track_cue_in_immediate(self, diagnosis):
        cause_ids = [c.cause_id for c in diagnosis.immediate_causes]
        assert "knee_track_cue" in cause_ids

    def test_knee_track_cue_has_perturbation(self, diagnosis):
        for cause in diagnosis.immediate_causes:
            if cause.cause_id == "knee_track_cue":
                assert cause.parameter_delta is not None
                assert "L_hip.ry" in cause.parameter_delta
                assert "R_hip.ry" in cause.parameter_delta

    def test_confidence_is_positive(self, diagnosis):
        assert diagnosis.confidence > 0.0

    def test_all_causes_have_explanations(self, diagnosis):
        all_causes = (
            diagnosis.immediate_causes
            + diagnosis.session_causes
            + diagnosis.longterm_causes
            + diagnosis.contextual_notes
        )
        for cause in all_causes:
            assert len(cause.explanation) > 0


class TestHealthyLifter:
    """Scenario: good form, no issues detected."""

    def test_no_symptoms_detected(self):
        engine = HypothesisEngine()
        reps = [
            _make_rep(
                rep_number=i,
                trunk_pitch_at_bottom=32.0,
                knee_valgus_l=2.0,
                knee_valgus_r=2.0,
                ankle_df_l_max=22.0,
                ankle_df_r_max=22.0,
                hip_y_l_at_bottom=38.0,
                hip_y_r_at_bottom=38.0,
                knee_y_l_at_bottom=42.0,
                knee_y_r_at_bottom=42.0,
                stance_width_ratio=1.0,
                foot_direction_angle_l=22.0,
                foot_direction_angle_r=22.0,
                depth_class_int=3,
            )
            for i in range(1, 4)
        ]
        features = SetFeatures(
            user_id=4,
            set_id="test_healthy",
            rep_count=3,
            per_rep_kinematics=reps,
            anthropometry=NORMAL_ANTHRO,
            rom=NORMAL_ROM,
        )
        result = engine.diagnose(features)

        assert isinstance(result, DiagnosisResult)
        assert len(result.detected_symptoms) == 0
        assert len(result.immediate_causes) == 0
        assert len(result.longterm_causes) == 0
        assert result.confidence == 0.0
        assert result.combined_perturbation == {}

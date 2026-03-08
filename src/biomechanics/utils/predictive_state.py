"""
Predictive State Estimator

Uses current joint angles and angular velocities to predict the state
at a configurable time horizon (default 200ms). The predicted angles
are used for fault evaluation, allowing cues to fire before the fault
fully manifests.

This does NOT replace the current angles — it produces a separate
predicted JointAngles object that the rule engine evaluates against.
"""

from biomechanics.utils.types import JointAngles
from biomechanics.utils.derivatives import AngleDerivatives


class PredictiveStateEstimator:
    """
    Predicts future joint angles using constant-velocity extrapolation.

    predicted_angle = current_angle + velocity * horizon_seconds

    Args:
        horizon_seconds: How far ahead to predict, in seconds.
            Default 0.2 (200ms). Should match approximate audio
            pipeline latency. Range 0.1–0.3 recommended.
        max_extrapolation_deg: Maximum angle change allowed per prediction.
            Prevents runaway extrapolation during noisy velocity spikes.
            Default 15.0 degrees.
    """

    def __init__(
        self,
        horizon_seconds: float = 0.2,
        max_extrapolation_deg: float = 15.0,
    ):
        self.horizon_seconds = horizon_seconds
        self.max_extrapolation_deg = max_extrapolation_deg

    def predict(
        self,
        angles: JointAngles,
        derivatives: AngleDerivatives,
    ) -> JointAngles:
        """
        Predict future joint angles from current angles + velocities.

        Args:
            angles: Current frame's filtered joint angles.
            derivatives: Current frame's angular velocities.

        Returns:
            New JointAngles object with predicted values.
            timestamp and frame_index are copied from the input.
        """
        dt = self.horizon_seconds

        def _extrapolate(current: float, velocity: float) -> float:
            delta = velocity * dt
            # Clamp extrapolation magnitude
            if abs(delta) > self.max_extrapolation_deg:
                delta = self.max_extrapolation_deg * (1.0 if delta > 0 else -1.0)
            return current + delta

        return JointAngles(
            # Hip angles — extrapolate using per-side velocities
            hip_flexion_l=_extrapolate(
                angles.hip_flexion_l, derivatives.hip_velocity_l
            ),
            hip_flexion_r=_extrapolate(
                angles.hip_flexion_r, derivatives.hip_velocity_r
            ),
            # Hip adduction/rotation: no velocity tracked yet,
            # so use current values (no extrapolation)
            hip_adduction_l=angles.hip_adduction_l,
            hip_adduction_r=angles.hip_adduction_r,
            hip_rotation_l=angles.hip_rotation_l,
            hip_rotation_r=angles.hip_rotation_r,
            # Knee angles
            knee_flexion_l=_extrapolate(
                angles.knee_flexion_l, derivatives.knee_velocity_l
            ),
            knee_flexion_r=_extrapolate(
                angles.knee_flexion_r, derivatives.knee_velocity_r
            ),
            # Ankle: no velocity tracked, use current
            ankle_dorsiflexion_l=angles.ankle_dorsiflexion_l,
            ankle_dorsiflexion_r=angles.ankle_dorsiflexion_r,
            # Trunk: no velocity tracked, use current
            trunk_flexion=angles.trunk_flexion,
            trunk_lateral_flexion=angles.trunk_lateral_flexion,
            trunk_rotation=angles.trunk_rotation,
            # Pelvis: no velocity tracked, use current
            pelvis_tilt=angles.pelvis_tilt,
            pelvis_list=angles.pelvis_list,
            pelvis_rotation=angles.pelvis_rotation,
            # Metadata
            timestamp=angles.timestamp,
            frame_index=angles.frame_index,
        )

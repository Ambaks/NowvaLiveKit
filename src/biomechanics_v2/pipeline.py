"""Biomechanics V2 Pipeline Orchestrator

Wires capture -> filtering -> MuJoCo IK -> fault detection -> rep segmentation
into a single pipeline. Uses MuJoCo physics for IK and angle extraction while
reusing V1's proven capture, filtering, fault detection, and rep counting.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from biomechanics.config import BiomechanicsConfig
from biomechanics.faults.rule_engine import RuleEngine
from biomechanics.profiles import get_profile
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.standing_gate import StandingPoseGate
from biomechanics.utils.types import (
    BarbellDetection,
    BarTrackState,
    PipelineFrame,
    Skeleton2D,
    Skeleton3D,
)
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.solver.angle_extract import q_to_joint_angles
from biomechanics_v2.solver.landmark_adapter import skeleton3d_to_landmarks
from biomechanics_v2.solver.mujoco_ik import MujocoIKSolver

logger = logging.getLogger(__name__)


class BiomechanicsV2Pipeline:
    """V2 biomechanics pipeline using MuJoCo physics for IK and angle extraction.

    Components wired:
      - Pose estimation (from biomechanics.pose, lazy-initialized)
      - Pre-IK filters (from biomechanics.utils)
      - MuJoCo skeleton (from biomechanics_v2.model)
      - MuJoCo IK solver (from biomechanics_v2.solver)
      - Angle extractor (from biomechanics_v2.solver)
      - Fault detection (from biomechanics.faults)
      - Rep counter (from biomechanics.faults)
      - Barbell tracker (from biomechanics.barbell_tracking, optional)
    """

    def __init__(
        self,
        height_m: float = 1.75,
        weight_kg: float = 75.0,
        exercise_name: str = "Barbell Back Squat",
        enable_barbell: bool = True,
        config: Optional[BiomechanicsConfig] = None,
    ):
        self._config = config or BiomechanicsConfig()
        self._frame_index = 0

        # Exercise profile (bundles fault rules, rep signal, calibration)
        self._profile = get_profile(exercise_name)

        # Pose estimation — lazy-initialized on first process_frame() call
        # so that process_skeleton3d() works without MediaPipe installed
        self._pose_estimator = None

        # Standing gate (needed by BoneLengthConstraints for calibration)
        standing_gate_config = self._config.standing_gate
        self._standing_gate = StandingPoseGate(
            min_confidence=standing_gate_config.min_confidence,
            max_knee_flexion_deg=standing_gate_config.max_knee_flexion_deg,
            max_trunk_flexion_deg=standing_gate_config.max_trunk_flexion_deg,
            min_torso_length_m=standing_gate_config.min_torso_length_m,
            max_torso_length_m=standing_gate_config.max_torso_length_m,
            required_consecutive_frames=standing_gate_config.required_consecutive_frames,
        )

        # Pre-IK filtering chain (reused from V1)
        self._confidence_blender = ConfidenceBlender(
            min_confidence=self._config.confidence_blend.min_confidence,
            max_confidence=self._config.confidence_blend.max_confidence,
        )
        self._velocity_clamp = VelocityClamp(
            max_velocity_m_per_s=self._config.velocity_clamp.max_velocity_m_per_s,
            target_fps=self._config.pipeline.target_fps,
        )
        self._bone_constraints = BoneLengthConstraints(
            calibration_frames=self._config.bone_constraints.calibration_frames,
            tolerance=self._config.bone_constraints.tolerance,
            standing_gate=self._standing_gate,
        )
        self._position_smoother = KeypointPositionSmoother(
            min_cutoff=self._config.position_filter.min_cutoff,
            beta=self._config.position_filter.beta,
            d_cutoff=self._config.position_filter.d_cutoff,
        )

        # MuJoCo skeleton + IK solver
        self._skeleton = MujocoSkeleton(height_m=height_m, weight_kg=weight_kg)
        self._ik_solver = MujocoIKSolver(self._skeleton)
        self._previous_q: Optional[np.ndarray] = None
        self._proportions_applied = False

        # Fault detection (rules from exercise profile)
        profile_rules = self._profile.create_fault_rules(self._config)
        self._rule_engine = RuleEngine(rules=profile_rules, config=self._config)
        self._rule_engine.set_profile(self._profile)

        # Rep counting (strategy from exercise profile)
        self._rep_counter = self._profile.create_rep_counter(self._config)

        # Barbell tracking (optional, independent of pose)
        self._barbell_detector = None
        self._bar_tracker = None
        if enable_barbell and self._config.barbell_tracking.enabled:
            try:
                from biomechanics.barbell_tracking import BarbellDetector, BarPathTracker

                barbell_config = self._config.barbell_tracking
                self._barbell_detector = BarbellDetector(
                    model_path=barbell_config.model_path,
                    conf_threshold=barbell_config.conf_threshold,
                    imgsz=barbell_config.imgsz,
                    device=barbell_config.device,
                )
                self._bar_tracker = BarPathTracker(
                    bar_length_m=barbell_config.bar_length_m,
                    kalman_q=barbell_config.kalman_q,
                    kalman_r=barbell_config.kalman_r,
                    path_history_len=barbell_config.path_history_len,
                )
            except Exception:
                logger.warning(
                    "Barbell tracking unavailable — model not found or import failed"
                )

        # Accumulated q-trajectory for the current set
        self._q_trajectory: list[np.ndarray] = []

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray, timestamp: float) -> PipelineFrame:
        """Process single video frame through the full V2 pipeline.

        Steps:
        1. Pose estimation -> Skeleton2D, Skeleton3D
        2. Pre-IK filtering -> filtered Skeleton3D
        3. Landmark adapter -> (11, 4) targets
        4. MuJoCo IK -> q-vector
        5. Angle extraction -> JointAngles
        6. Fault detection -> List[FaultEvent]
        7. Rep counting -> Optional[RepData]
        8. Barbell tracking (parallel) -> BarTrackState
        9. Pack into PipelineFrame
        """
        latency_ms: dict[str, float] = {}

        # Barbell detection (independent of pose)
        bar_detection: Optional[BarbellDetection] = None
        bar_track: Optional[BarTrackState] = None
        if self._barbell_detector is not None:
            tick = time.perf_counter()
            try:
                bar_detection = self._barbell_detector.detect(
                    frame, timestamp=timestamp, frame_index=self._frame_index
                )
            except Exception:
                bar_detection = None
            if self._bar_tracker is not None:
                bar_track = self._bar_tracker.update(
                    bar_detection, timestamp=timestamp
                )
            latency_ms["barbell"] = (time.perf_counter() - tick) * 1000.0

        # Pose estimation
        tick = time.perf_counter()
        self._ensure_pose_estimator()
        skeleton_2d: Optional[Skeleton2D] = None
        skeleton_3d: Optional[Skeleton3D] = None
        try:
            skeleton_2d, skeleton_3d = self._pose_estimator.estimate_both(frame)
        except Exception:
            pass
        latency_ms["pose"] = (time.perf_counter() - tick) * 1000.0

        if skeleton_3d is None:
            self._frame_index += 1
            return PipelineFrame(
                frame_index=self._frame_index,
                timestamp=timestamp,
                skeleton_2d=skeleton_2d,
                bar_detection=bar_detection,
                bar_track=bar_track,
                latency_ms=latency_ms,
            )

        return self._process_from_skeleton(
            skeleton_3d=skeleton_3d,
            skeleton_2d=skeleton_2d,
            timestamp=timestamp,
            bar_detection=bar_detection,
            bar_track=bar_track,
            latency_ms=latency_ms,
        )

    def process_skeleton3d(
        self,
        skeleton_3d: Skeleton3D,
        timestamp: float,
        skeleton_2d: Optional[Skeleton2D] = None,
    ) -> PipelineFrame:
        """Process a pre-extracted Skeleton3D through the pipeline.

        Bypasses pose estimation — use this when the skeleton has already been
        extracted (e.g. from a different estimator, pre-recorded data, or tests).
        """
        return self._process_from_skeleton(
            skeleton_3d=skeleton_3d,
            skeleton_2d=skeleton_2d,
            timestamp=timestamp,
            bar_detection=None,
            bar_track=None,
            latency_ms={},
        )

    def on_bone_calibration_complete(self, proportions) -> None:
        """Called when BoneLengthConstraints finishes calibrating.

        Re-scales the MuJoCo model from observed proportions and rebuilds
        the IK solver (its cached model/data references go stale after rescale).
        Also adjusts fault detection thresholds for the user's anatomy.
        """
        self._skeleton.scale_from_proportions(proportions)
        self._ik_solver = MujocoIKSolver(self._skeleton)
        self._rule_engine.apply_body_proportion_scaling(proportions)
        self._proportions_applied = True
        logger.info(
            "[V2 PIPELINE] Bone calibration applied — MuJoCo model rescaled"
        )

    def get_q_trajectory(self) -> np.ndarray:
        """Return accumulated (T, 20) q-trajectory for the current set."""
        if not self._q_trajectory:
            return np.zeros((0, 20))
        return np.array(self._q_trajectory)

    def get_skeleton(self) -> MujocoSkeleton:
        """Return the MuJoCo skeleton model (for what-if solver)."""
        return self._skeleton

    def reset(self) -> None:
        """Reset all stateful components for a new set.

        Bone calibration and body proportions persist across sets.
        """
        self._frame_index = 0
        self._previous_q = None
        self._q_trajectory.clear()
        self._rule_engine.reset()
        self._rep_counter.reset()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_pose_estimator(self) -> None:
        """Lazy-initialize pose estimator on first use."""
        if self._pose_estimator is not None:
            return
        pose_config = self._config.pose
        if pose_config.backend == "rtmpose":
            from biomechanics.pose.rtmpose import RTMPoseEstimator

            self._pose_estimator = RTMPoseEstimator(
                confidence_threshold=pose_config.confidence_threshold,
                model_path=pose_config.model_path,
            )
        else:
            from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator

            self._pose_estimator = MediaPipePoseEstimator(
                confidence_threshold=pose_config.confidence_threshold,
                model_complexity=pose_config.model_complexity,
            )

    def _process_from_skeleton(
        self,
        skeleton_3d: Skeleton3D,
        skeleton_2d: Optional[Skeleton2D],
        timestamp: float,
        bar_detection: Optional[BarbellDetection],
        bar_track: Optional[BarTrackState],
        latency_ms: dict[str, float],
    ) -> PipelineFrame:
        """Core pipeline: Skeleton3D -> filtered -> IK -> angles -> faults -> rep."""

        # Standing gate (feeds into bone_constraints calibration)
        self._standing_gate.check(skeleton_3d)

        # Pre-IK filtering chain
        tick = time.perf_counter()
        skeleton_3d = self._confidence_blender.blend(skeleton_3d)
        skeleton_3d = self._velocity_clamp.clamp(skeleton_3d)
        skeleton_3d = self._bone_constraints.enforce(skeleton_3d)
        skeleton_3d = self._position_smoother.smooth(skeleton_3d)
        latency_ms["pre_ik_filters"] = (time.perf_counter() - tick) * 1000.0

        # Apply body-proportion scaling once after bone calibration completes
        if (
            not self._proportions_applied
            and self._bone_constraints.is_calibrated
            and self._bone_constraints.body_proportions is not None
        ):
            self.on_bone_calibration_complete(
                self._bone_constraints.body_proportions
            )

        # Landmark adapter: 19-keypoint Skeleton3D (Y-down) -> (11, 4) targets (Y-up)
        tick = time.perf_counter()
        landmarks = skeleton3d_to_landmarks(skeleton_3d)

        # MuJoCo IK: landmarks -> q-vector
        q_vector = self._ik_solver.fit_frame(
            landmarks=landmarks,
            q_init=self._previous_q,
        )
        self._previous_q = q_vector
        self._q_trajectory.append(q_vector.copy())

        # Angle extraction: q-vector -> JointAngles (degrees)
        joint_angles = q_to_joint_angles(
            self._skeleton,
            q_vector,
            timestamp=timestamp,
            frame_index=self._frame_index,
        )
        latency_ms["ik"] = (time.perf_counter() - tick) * 1000.0

        # Rep signal (exercise-specific, from profile)
        rep_signal = self._profile.get_rep_signal(skeleton_3d, joint_angles)

        # Fault detection + rep counting
        tick = time.perf_counter()
        faults = self._rule_engine.evaluate(
            joint_angles,
            in_rep=self._rep_counter.in_rep,
            rep_number=self._rep_counter.rep_count + 1,
            bar_detection=bar_detection,
        )

        # Track angles for baseline calibration during reps
        if not self._rule_engine.calibrated and self._rep_counter.in_rep:
            self._rule_engine.record_frame_for_calibration(joint_angles)

        # Rep counting (uses profile-provided signal)
        rep_data, _feedback = self._rep_counter.update(
            signal_value=rep_signal,
            timestamp=timestamp,
            angles=joint_angles,
            faults=faults,
        )

        # Post-rep fault evaluation (depth, tempo)
        if rep_data is not None:
            depth_faults = self._rule_engine.evaluate_rep_complete(
                rep_data.max_depth_angle,
                joint_angles,
                rep_data.rep_number,
                rep_data=rep_data,
            )
            faults.extend(depth_faults)
            rep_data.faults.extend(depth_faults)
            self._rule_engine.on_rep_complete_calibration(
                is_clean=rep_data.is_clean
            )

        latency_ms["faults"] = (time.perf_counter() - tick) * 1000.0

        self._frame_index += 1

        return PipelineFrame(
            frame_index=self._frame_index,
            timestamp=timestamp,
            skeleton_2d=skeleton_2d,
            skeleton_3d=skeleton_3d,
            joint_angles=joint_angles,
            faults=faults,
            rep_data=rep_data,
            bar_detection=bar_detection,
            bar_track=bar_track,
            latency_ms=latency_ms,
        )

"""
Biomechanics Pipeline

Wires all processing layers into a single pipeline:
  Webcam capture → Pose estimation → IK solve → Fault detection → Rep counting

Returns a PipelineFrame per iteration with per-layer timing.
"""

import os
import threading
import time
from typing import List, Optional

import cv2
import numpy as np

from biomechanics.config import BiomechanicsConfig, load_pipeline_config
from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.faults import RuleEngine
from biomechanics.profiles import get_profile
from biomechanics.utils.types import (
    PipelineFrame,
    Skeleton2D,
    Skeleton3D,
    JointAngles,
    FaultEvent,
    CocoKeypoints,
    DEPTH_CLASS_NAMES,
    BarbellDetection,
    BarTrackState,
)
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.derivatives import DerivativeTracker
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.velocity_clamp import VelocityClamp
from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.predictive_state import PredictiveStateEstimator
from biomechanics.utils.standing_gate import StandingPoseGate


class BiomechanicsPipeline:
    """
    Full biomechanics processing pipeline.

    Captures video, estimates pose, computes joint angles, detects faults,
    and counts reps. Each call to process_frame() runs one iteration and
    returns a PipelineFrame with all results and per-layer timing.
    """

    def __init__(
        self,
        config: Optional[BiomechanicsConfig] = None,
        exercise_name: str = "Barbell Back Squat",
    ):
        self.config = config or BiomechanicsConfig()
        self._frame_index = 0

        # Load exercise profile (bundles fault rules, rep signal, cues)
        self._profile = get_profile(exercise_name)

        # Optional pre-IK filtering (off by default, enable via .env)
        self._preik_enabled = os.getenv("ENABLE_PREIK_FILTERS", "true").lower() == "true"

        # Layer 1: Capture (threaded — always holds the latest frame)
        self._cap = cv2.VideoCapture(self.config.capture.device_id)
        w, h = self.config.capture.resolution
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open camera device {self.config.capture.device_id}"
            )

        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._capture_running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._capture_thread.start()

        # Layer 2: Pose estimation
        if self.config.pose.backend == "rtmpose":
            from biomechanics.pose.rtmpose import RTMPoseEstimator

            self._pose_estimator = RTMPoseEstimator(
                confidence_threshold=self.config.pose.confidence_threshold,
                model_path=self.config.pose.model_path,
            )
        else:
            model_complexity = self.config.pose.model_complexity
            self._pose_estimator = MediaPipePoseEstimator(
                confidence_threshold=self.config.pose.confidence_threshold,
                model_complexity=model_complexity,
            )

        # Layer 3: Inverse kinematics
        self._ik_solver = AnalyticalIKSolver()

        # Temporal smoothing
        self._angle_filter = JointAngleFilter(min_cutoff=1.0, beta=0.007)

        # Derivative computation
        self._derivative_tracker = DerivativeTracker(smoothing_alpha=0.3)

        # Standing pose gate — runs unconditionally to validate user is
        # in frame and standing before any calibration starts.
        sg = self.config.standing_gate
        self._standing_gate = StandingPoseGate(
            min_confidence=sg.min_confidence,
            max_knee_flexion_deg=sg.max_knee_flexion_deg,
            max_trunk_flexion_deg=sg.max_trunk_flexion_deg,
            min_torso_length_m=sg.min_torso_length_m,
            max_torso_length_m=sg.max_torso_length_m,
            required_consecutive_frames=sg.required_consecutive_frames,
        )

        # Readiness gate — per-set gate that ensures the user is fully
        # detected and standing before data collection begins. Resets
        # between sets so each set starts with clean data.
        rg = self.config.readiness_gate
        self._readiness_gate = StandingPoseGate(
            min_confidence=rg.min_confidence,
            max_knee_flexion_deg=rg.max_knee_flexion_deg,
            max_trunk_flexion_deg=rg.max_trunk_flexion_deg,
            min_torso_length_m=rg.min_torso_length_m,
            max_torso_length_m=rg.max_torso_length_m,
            required_consecutive_frames=rg.required_consecutive_frames,
        )

        # Pre-IK skeleton filtering (only initialised when enabled)
        self._confidence_blender = None
        self._velocity_clamp = None
        self._bone_constraints = None
        self._position_smoother = None
        self._predictive_estimator = None
        self._proportions_applied = False

        if self._preik_enabled:
            self._confidence_blender = ConfidenceBlender(
                min_confidence=self.config.confidence_blend.min_confidence,
                max_confidence=self.config.confidence_blend.max_confidence,
            )
            self._velocity_clamp = VelocityClamp(
                max_velocity_m_per_s=self.config.velocity_clamp.max_velocity_m_per_s,
                target_fps=self.config.pipeline.target_fps,
            )
            self._bone_constraints = BoneLengthConstraints(
                calibration_frames=self.config.bone_constraints.calibration_frames,
                tolerance=self.config.bone_constraints.tolerance,
                standing_gate=self._standing_gate,
            )
            self._position_smoother = KeypointPositionSmoother(
                min_cutoff=self.config.position_filter.min_cutoff,
                beta=self.config.position_filter.beta,
                d_cutoff=self.config.position_filter.d_cutoff,
            )
            self._predictive_estimator = PredictiveStateEstimator(
                horizon_seconds=self.config.predictive_state.horizon_seconds,
                max_extrapolation_deg=self.config.predictive_state.max_extrapolation_deg,
            )

        # Layer 3b (optional): Barbell detection + Kalman-smoothed tracking.
        # Runs on the raw frame independently of pose; feeds BarPathRule
        # and BarTiltAsymmetryRule via bar_detection kwarg.
        self._barbell_detector = None
        self._bar_tracker = None
        if self.config.barbell_tracking.enabled:
            from biomechanics.barbell_tracking import BarbellDetector, BarPathTracker

            bt = self.config.barbell_tracking
            self._barbell_detector = BarbellDetector(
                model_path=bt.model_path,
                conf_threshold=bt.conf_threshold,
                imgsz=bt.imgsz,
                device=bt.device,
            )
            self._bar_tracker = BarPathTracker(
                bar_length_m=bt.bar_length_m,
                kalman_q=bt.kalman_q,
                kalman_r=bt.kalman_r,
                path_history_len=bt.path_history_len,
            )

        # Layer 4: Fault detection (rules provided by exercise profile)
        profile_rules = self._profile.create_fault_rules(self.config)
        self._rule_engine = RuleEngine(rules=profile_rules)
        self._rule_engine.set_profile(self._profile)

        # Layer 5: Rep counting (strategy determined by exercise profile)
        self._rep_counter = self._profile.create_rep_counter(self.config)

        # Layer 6 (optional): BiLSTM rep counting
        self._bilstm = None
        if self.config.bilstm.enabled:
            from biomechanics.ml.inference import BiLSTMInference
            from biomechanics.ml.bilstm_counter import BiLSTMCounterConfig

            bilstm_counter_cfg = BiLSTMCounterConfig(
                min_depth_class=self.config.bilstm.min_depth_class,
                min_rep_frames=self.config.bilstm.min_rep_frames,
                ema_alpha=self.config.bilstm.ema_alpha,
                num_classes=self.config.bilstm.num_classes,
            )
            self._bilstm = BiLSTMInference(
                model_path=self.config.bilstm.model_path,
                device=self.config.bilstm.device,
                config=bilstm_counter_cfg,
            )

        # Track max knee flexion independently for BiLSTM rep windows.
        # The hip position counter's snapshot may be desync'd from the
        # BiLSTM's rep boundaries, so we track angle peaks here.
        self._bilstm_max_knee_flex: float = 0.0
        self._bilstm_min_knee_flex: float = 180.0

        # Buffer faults from the hip counter for the BiLSTM to consume.
        # The hip counter resets _current_faults on rep completion, which
        # happens before the BiLSTM fires — so we stash them here.
        self._pending_bilstm_faults: List[FaultEvent] = []

        # Store last raw frame for dashboard access
        self.last_frame: Optional[np.ndarray] = None

    @property
    def rep_counter(self):
        """Expose rep counter for external access (e.g. dashboard)."""
        return self._rep_counter

    @property
    def is_ready(self) -> bool:
        """Whether the readiness gate has passed and data is being collected."""
        return self._readiness_gate.is_ready

    def reset_readiness_gate(self) -> None:
        """Reset the per-set readiness gate.

        Call this when a set ends or a rest period starts so the next
        set requires the user to be fully detected for 30 frames first.
        """
        self._readiness_gate.reset()
        self._bilstm_max_knee_flex = 0.0
        self._bilstm_min_knee_flex = 180.0
        self._pending_bilstm_faults.clear()

    def _capture_loop(self) -> None:
        """Continuously read frames from the camera in a background thread."""
        while self._capture_running:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._frame_lock:
                    self._latest_frame = frame

    def process_frame(self) -> PipelineFrame:
        """
        Run one full pipeline iteration.

        Returns:
            PipelineFrame with all layer outputs and per-layer timing.
        """
        latency_ms = {}
        now = time.time()

        # --- Capture (grab latest frame from capture thread) ---
        t0 = time.perf_counter()
        with self._frame_lock:
            frame = self._latest_frame
        latency_ms["capture"] = (time.perf_counter() - t0) * 1000.0

        if frame is None:
            self._frame_index += 1
            return PipelineFrame(
                frame_index=self._frame_index,
                timestamp=now,
                latency_ms=latency_ms,
            )

        bar_detection: Optional[BarbellDetection] = None
        bar_track: Optional[BarTrackState] = None

        self.last_frame = frame

        # --- Barbell detection + tracking (independent of pose) ---
        if self._barbell_detector is not None:
            t0 = time.perf_counter()
            try:
                bar_detection = self._barbell_detector.detect(
                    frame, timestamp=now, frame_index=self._frame_index
                )
            except Exception:
                bar_detection = None
            if self._bar_tracker is not None:
                bar_track = self._bar_tracker.update(bar_detection, timestamp=now)
            latency_ms["barbell"] = (time.perf_counter() - t0) * 1000.0

        # --- Pose estimation ---
        t0 = time.perf_counter()
        skeleton_2d: Optional[Skeleton2D] = None
        skeleton_3d: Optional[Skeleton3D] = None

        try:
            skeleton_2d, skeleton_3d = self._pose_estimator.estimate_both(frame)
        except Exception:
            pass  # pose failed — skip downstream

        latency_ms["pose"] = (time.perf_counter() - t0) * 1000.0

        if skeleton_3d is None:
            # No pose detected — return early with what we have
            self._frame_index += 1
            return PipelineFrame(
                frame_index=self._frame_index,
                timestamp=now,
                skeleton_2d=skeleton_2d,
                bar_detection=bar_detection,
                bar_track=bar_track,
                latency_ms=latency_ms,
            )

        # --- BiLSTM rep counting (runs on raw skeleton, before IK) ---
        bilstm_rep_data = None
        bilstm_prob = None
        bilstm_depth_class = None
        bilstm_depth_class_name = None
        bilstm_class_probs = None
        if self._bilstm is not None:
            t0 = time.perf_counter()
            bilstm_rep_data = self._bilstm.process_skeleton(skeleton_3d)
            bilstm_prob = self._bilstm.current_probability
            bilstm_depth_class = self._bilstm.current_depth_class
            bilstm_depth_class_name = DEPTH_CLASS_NAMES.get(bilstm_depth_class, "Unknown")
            bilstm_class_probs = self._bilstm.current_class_probabilities.tolist()
            latency_ms["bilstm"] = (time.perf_counter() - t0) * 1000.0

        # --- Standing pose gate (runs every frame, unconditional) ---
        self._standing_gate.check(skeleton_3d)

        # --- Readiness gate (per-set, resets between sets) ---
        self._readiness_gate.check(skeleton_3d)
        if not self._readiness_gate.is_ready:
            self._frame_index += 1
            return PipelineFrame(
                frame_index=self._frame_index,
                timestamp=now,
                skeleton_2d=skeleton_2d,
                skeleton_3d=skeleton_3d,
                bar_detection=bar_detection,
                bar_track=bar_track,
                latency_ms=latency_ms,
            )

        # --- Pre-IK filtering layers (optional) ---
        if self._preik_enabled:
            t0 = time.perf_counter()
            skeleton_3d = self._confidence_blender.blend(skeleton_3d)
            skeleton_3d = self._velocity_clamp.clamp(skeleton_3d)
            skeleton_3d = self._bone_constraints.enforce(skeleton_3d)
            skeleton_3d = self._position_smoother.smooth(skeleton_3d)
            skeleton_3d = self._bone_constraints.enforce(skeleton_3d)
            latency_ms["pre_ik_filters"] = (time.perf_counter() - t0) * 1000.0

            # Apply body-proportion scaling once after bone calibration
            if (
                not self._proportions_applied
                and self._bone_constraints.is_calibrated
                and self._bone_constraints.body_proportions is not None
            ):
                proportions = self._bone_constraints.body_proportions
                self._rule_engine.apply_body_proportion_scaling(proportions)
                self._ik_solver.set_body_proportions(proportions)
                self._proportions_applied = True

        # --- IK solve ---
        t0 = time.perf_counter()
        raw_angles = self._ik_solver.solve(skeleton_3d)

        # Apply temporal filter for stability
        angles = self._angle_filter.filter_angles(raw_angles)

        # Compute derivatives (velocity, acceleration)
        derivatives = self._derivative_tracker.update(angles)
        latency_ms["ik"] = (time.perf_counter() - t0) * 1000.0

        # --- Compute rep signal (exercise-specific, from profile) ---
        rep_signal = self._profile.get_rep_signal(skeleton_3d, angles)

        # --- Fault detection + rep counting ---
        t0 = time.perf_counter()

        # Use predicted angles for fault evaluation when pre-IK filters are on,
        # otherwise use actual angles directly.
        if self._preik_enabled:
            eval_angles = self._predictive_estimator.predict(angles, derivatives)
        else:
            eval_angles = angles

        faults = self._rule_engine.evaluate(
            eval_angles,
            in_rep=self._rep_counter.in_rep,
            rep_number=self._rep_counter.rep_count + 1,
            bar_detection=bar_detection,
        )

        # Calibration uses ACTUAL angles
        if not self._rule_engine.calibrated and self._rep_counter.in_rep:
            self._rule_engine.record_frame_for_calibration(angles)

        # Rep counter uses profile-provided signal for state, angles for metrics
        rep_data, feedback = self._rep_counter.update(
            signal_value=rep_signal,
            timestamp=now,
            angles=angles,
            faults=faults,
        )

        # Phase-aware smoothing only when pre-IK filters are active
        if self._preik_enabled:
            self._angle_filter.update_phase(self._rep_counter.phase)

        # If rep completed, check depth faults and advance calibration
        if rep_data is not None:
            depth_faults = self._rule_engine.evaluate_rep_complete(
                rep_data.max_depth_angle, angles, rep_data.rep_number
            )
            faults.extend(depth_faults)
            self._rule_engine.on_rep_complete_calibration(is_clean=rep_data.is_clean)

            # When BiLSTM is active the hip counter's rep_data is suppressed
            # (line below), but it has the correct faults.  Stash them so the
            # BiLSTM path can pick them up via _pending_bilstm_faults.
            if self._bilstm is not None:
                self._pending_bilstm_faults.extend(rep_data.faults)

        latency_ms["faults"] = (time.perf_counter() - t0) * 1000.0

        # Track max knee flexion during BiLSTM rep windows independently
        # of the hip counter, which may be at a different phase.
        if self._bilstm is not None and self._bilstm.in_rep:
            knee = angles.avg_knee_flexion
            if knee > self._bilstm_max_knee_flex:
                self._bilstm_max_knee_flex = knee
            if knee < self._bilstm_min_knee_flex:
                self._bilstm_min_knee_flex = knee

        self._frame_index += 1

        # Use BiLSTM rep data as primary when enabled and available.
        # When BiLSTM is active, suppress rule-based rep events to prevent
        # double-counting when the two counters fire on different frames.
        final_rep_data = rep_data if self._bilstm is None else None
        if self._bilstm is not None and bilstm_rep_data is not None:
            # Enrich BiLSTM RepData with rule-based metrics so downstream
            # consumers (IPC bridge, coaching LLM, set reports) get real
            # angle data, faults, timing, and asymmetry values.
            metrics = self._rep_counter.snapshot_rep_metrics()

            # Use our independently-tracked knee flexion for depth, since
            # the hip counter's snapshot may be desync'd from the BiLSTM's
            # rep boundaries (causing false "quarter" depth classifications).
            bilstm_rep_data.max_depth_angle = self._bilstm_max_knee_flex
            bilstm_rep_data.min_depth_angle = self._bilstm_min_knee_flex
            self._bilstm_max_knee_flex = 0.0
            self._bilstm_min_knee_flex = 180.0

            bilstm_rep_data.descent_time = metrics["descent_time"]
            bilstm_rep_data.ascent_time = metrics["ascent_time"]
            # Combine buffered faults (from hip counter rep completions) with
            # any still in the counter's accumulator.  The hip counter clears
            # _current_faults on rep completion, so metrics["faults"] is often
            # empty — the buffered list has the real data.
            bilstm_rep_data.faults = self._pending_bilstm_faults + metrics["faults"]
            self._pending_bilstm_faults.clear()
            bilstm_rep_data.avg_knee_asymmetry = metrics["avg_knee_asymmetry"]
            bilstm_rep_data.avg_hip_asymmetry = metrics["avg_hip_asymmetry"]
            self._rep_counter.clear_current_faults()

            # Evaluate depth faults for BiLSTM reps (rule-based only runs
            # this when its own counter fires, which may not align)
            depth_faults = self._rule_engine.evaluate_rep_complete(
                bilstm_rep_data.max_depth_angle, angles, bilstm_rep_data.rep_number
            )
            faults.extend(depth_faults)
            bilstm_rep_data.faults.extend(depth_faults)
            self._rule_engine.on_rep_complete_calibration(is_clean=bilstm_rep_data.is_clean)

            final_rep_data = bilstm_rep_data

        return PipelineFrame(
            frame_index=self._frame_index,
            timestamp=now,
            skeleton_2d=skeleton_2d,
            skeleton_3d=skeleton_3d,
            joint_angles=angles,
            faults=faults,
            rep_data=final_rep_data,
            bilstm_probability=bilstm_prob,
            bilstm_rep_data=bilstm_rep_data,
            bilstm_depth_class=bilstm_depth_class,
            bilstm_depth_class_name=bilstm_depth_class_name,
            bilstm_class_probabilities=bilstm_class_probs,
            bar_detection=bar_detection,
            bar_track=bar_track,
            latency_ms=latency_ms,
        )

    def release(self):
        """Release all resources."""
        self._capture_running = False
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
        if self._pose_estimator is not None:
            self._pose_estimator.release()

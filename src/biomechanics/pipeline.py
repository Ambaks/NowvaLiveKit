"""
Biomechanics Pipeline

Wires all processing layers into a single pipeline:
  Webcam capture → Pose estimation → IK solve → Fault detection → Rep counting

Returns a PipelineFrame per iteration with per-layer timing.
"""

import time
from typing import Optional

import cv2
import numpy as np

from biomechanics.config import BiomechanicsConfig, load_pipeline_config
from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver
from biomechanics.faults import RuleEngine, RepCounter, RepCounterConfig
from biomechanics.utils.types import PipelineFrame, Skeleton2D, Skeleton3D, JointAngles, DEPTH_CLASS_NAMES
from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.derivatives import DerivativeTracker


class BiomechanicsPipeline:
    """
    Full biomechanics processing pipeline.

    Captures video, estimates pose, computes joint angles, detects faults,
    and counts reps. Each call to process_frame() runs one iteration and
    returns a PipelineFrame with all results and per-layer timing.
    """

    def __init__(self, config: Optional[BiomechanicsConfig] = None):
        self.config = config or BiomechanicsConfig()
        self._frame_index = 0

        # Layer 1: Capture
        self._cap = cv2.VideoCapture(self.config.capture.device_id)
        w, h = self.config.capture.resolution
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Could not open camera device {self.config.capture.device_id}"
            )

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

        # Layer 4: Fault detection
        self._rule_engine = RuleEngine()

        # Layer 5: Rep counting
        rep_config = RepCounterConfig(
            entry_knee_angle=self.config.rep_detection.entry_threshold,
            min_rep_duration_frames=self.config.rep_detection.min_rep_duration_frames,
        )
        self._rep_counter = RepCounter(rep_config)

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

        # Store last raw frame for dashboard access
        self.last_frame: Optional[np.ndarray] = None

    @property
    def rep_counter(self) -> RepCounter:
        """Expose rep counter for external access (e.g. dashboard)."""
        return self._rep_counter

    def process_frame(self) -> PipelineFrame:
        """
        Run one full pipeline iteration.

        Returns:
            PipelineFrame with all layer outputs and per-layer timing.
        """
        latency_ms = {}
        now = time.time()

        # --- Capture ---
        t0 = time.perf_counter()
        ret, frame = self._cap.read()
        latency_ms["capture"] = (time.perf_counter() - t0) * 1000.0

        if not ret or frame is None:
            self._frame_index += 1
            return PipelineFrame(
                frame_index=self._frame_index,
                timestamp=now,
                latency_ms=latency_ms,
            )

        self.last_frame = frame

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

        # --- IK solve ---
        t0 = time.perf_counter()
        raw_angles = self._ik_solver.solve(skeleton_3d)

        # Apply temporal filter for stability
        angles = self._angle_filter.filter_angles(raw_angles)

        # Compute derivatives (velocity, acceleration)
        derivatives = self._derivative_tracker.update(angles)
        latency_ms["ik"] = (time.perf_counter() - t0) * 1000.0

        # --- Fault detection + rep counting ---
        t0 = time.perf_counter()
        faults = self._rule_engine.evaluate(
            angles,
            in_rep=self._rep_counter.in_rep,
            rep_number=self._rep_counter.rep_count + 1,
        )

        # Track peak angles during reps for baseline calibration
        if not self._rule_engine.calibrated and self._rep_counter.in_rep:
            self._rule_engine.record_frame_for_calibration(angles)

        rep_data, feedback = self._rep_counter.update(angles, derivatives, faults)

        # If rep completed, check depth faults and advance calibration
        if rep_data is not None:
            depth_faults = self._rule_engine.evaluate_rep_complete(
                rep_data.max_depth_angle, angles, rep_data.rep_number
            )
            faults.extend(depth_faults)
            self._rule_engine.on_rep_complete_calibration(is_clean=rep_data.is_clean)

        latency_ms["faults"] = (time.perf_counter() - t0) * 1000.0

        self._frame_index += 1

        # Use BiLSTM rep data as primary when enabled and available
        final_rep_data = rep_data
        if self._bilstm is not None and bilstm_rep_data is not None:
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
            latency_ms=latency_ms,
        )

    def release(self):
        """Release all resources."""
        if self._cap is not None:
            self._cap.release()
        if self._pose_estimator is not None:
            self._pose_estimator.release()

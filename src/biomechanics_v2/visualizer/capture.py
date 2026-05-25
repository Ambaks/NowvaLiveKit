"""Live capture and video processing for the V2 biomechanics pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from biomechanics.utils.types import FaultEvent, PipelineFrame, RepData
from biomechanics_v2.pipeline import BiomechanicsV2Pipeline

logger = logging.getLogger(__name__)

COCO_CONNECTIONS = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (0, 5), (0, 6), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (15, 17), (16, 18),
]


@dataclass
class CaptureResult:
    """Output of a capture / video-processing session."""

    q_trajectory: np.ndarray
    timestamps: np.ndarray
    pipeline_frames: list[PipelineFrame] = field(default_factory=list)
    reps: list[RepData] = field(default_factory=list)
    all_faults: list[FaultEvent] = field(default_factory=list)
    height_m: float = 1.75
    weight_kg: float = 75.0
    fps: float = 30.0


class SquatCaptureSession:
    """Capture and process squat video through the V2 pipeline.

    Handles both live webcam and pre-recorded video files.
    For webcam: shows live preview with skeleton overlay, stops after
    target_reps or ESC.
    For video file: processes all frames, logs progress periodically.
    """

    def __init__(
        self,
        pipeline: BiomechanicsV2Pipeline,
        video_source: int | str = 0,
        target_reps: int = 5,
        show_preview: bool = True,
    ):
        self._pipeline = pipeline
        self._video_source = video_source
        self._target_reps = target_reps
        self._show_preview = show_preview

    def run(self) -> CaptureResult:
        """Process video through the V2 pipeline and return results."""
        cap = cv2.VideoCapture(self._video_source)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {self._video_source}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        is_live = isinstance(self._video_source, int)
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if not is_live else 0

        pipeline_frames: list[PipelineFrame] = []
        reps: list[RepData] = []
        all_faults: list[FaultEvent] = []
        timestamps: list[float] = []
        start_time = time.perf_counter()

        try:
            frame_idx = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                timestamp = (
                    time.perf_counter() - start_time
                    if is_live
                    else frame_idx / fps
                )

                pipeline_frame = self._pipeline.process_frame(frame, timestamp)
                pipeline_frames.append(pipeline_frame)
                timestamps.append(timestamp)

                if pipeline_frame.faults:
                    all_faults.extend(pipeline_frame.faults)
                if pipeline_frame.rep_data is not None:
                    reps.append(pipeline_frame.rep_data)

                if self._show_preview and is_live:
                    self._draw_preview(frame, pipeline_frame, len(reps))
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:
                        break

                if len(reps) >= self._target_reps:
                    logger.info("Reached %d reps — stopping capture", self._target_reps)
                    break

                frame_idx += 1

                if not is_live and frame_idx % 100 == 0:
                    progress = (
                        f" ({100 * frame_idx / total_video_frames:.0f}%)"
                        if total_video_frames > 0
                        else ""
                    )
                    logger.info(
                        "Processed %d frames, %d reps%s",
                        frame_idx,
                        len(reps),
                        progress,
                    )
        finally:
            cap.release()
            if self._show_preview:
                cv2.destroyAllWindows()

        q_trajectory = self._pipeline.get_q_trajectory()

        return CaptureResult(
            q_trajectory=q_trajectory,
            timestamps=np.array(timestamps),
            pipeline_frames=pipeline_frames,
            reps=reps,
            all_faults=all_faults,
            height_m=self._pipeline.get_skeleton().height_m,
            weight_kg=self._pipeline.get_skeleton().weight_kg,
            fps=fps,
        )

    def _draw_preview(
        self,
        frame: np.ndarray,
        pipeline_frame: PipelineFrame,
        rep_count: int,
    ) -> None:
        """Draw skeleton overlay and status text on the preview frame."""
        if pipeline_frame.skeleton_2d is not None:
            keypoints = pipeline_frame.skeleton_2d.keypoints
            for idx_a, idx_b in COCO_CONNECTIONS:
                if idx_a >= len(keypoints) or idx_b >= len(keypoints):
                    continue
                kp_a = keypoints[idx_a]
                kp_b = keypoints[idx_b]
                if kp_a.confidence > 0.3 and kp_b.confidence > 0.3:
                    cv2.line(
                        frame,
                        (int(kp_a.x), int(kp_a.y)),
                        (int(kp_b.x), int(kp_b.y)),
                        (0, 255, 0),
                        2,
                    )
            for kp in keypoints[:19]:
                if kp.confidence > 0.3:
                    cv2.circle(frame, (int(kp.x), int(kp.y)), 4, (0, 255, 0), -1)

        status = f"Rep {rep_count}/{self._target_reps}"
        if pipeline_frame.joint_angles is not None:
            knee = pipeline_frame.joint_angles.knee_flexion_l or 0.0
            status += f" | Knee: {knee:.0f} deg"
        cv2.putText(
            frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
        )

        significant_faults = [
            f for f in pipeline_frame.faults if f.is_significant
        ]
        if significant_faults:
            fault_text = ", ".join(f.fault_type for f in significant_faults[:3])
            cv2.putText(
                frame,
                fault_text,
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                2,
            )

        cv2.imshow("V2 Squat Capture", frame)

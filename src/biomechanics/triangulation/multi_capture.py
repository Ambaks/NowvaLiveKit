"""
Synchronized multi-camera capture.

Opens N cameras by device ID, reads frames in parallel threads, and pairs
them by nearest timestamp within a configurable tolerance.
"""

import logging
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class MultiCameraCapture:
    """
    Synchronized capture from multiple USB cameras.

    Each camera gets its own reader thread that stamps frames with
    time.perf_counter(). A ring buffer per camera holds recent frames.
    get_synced_frames() pairs them by nearest timestamp.
    """

    def __init__(
        self,
        device_ids: List[int],
        resolution: Tuple[int, int] = (1280, 720),
        max_sync_delta_ms: float = 15.0,
        buffer_size: int = 5,
    ):
        self._device_ids = device_ids
        self._resolution = resolution
        self._max_sync_delta_s = max_sync_delta_ms / 1000.0
        self._buffer_size = buffer_size

        self._caps: Dict[str, cv2.VideoCapture] = {}
        self._buffers: Dict[str, deque] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._running = False

        self._frame_counts: Dict[str, int] = {}
        self._start_time: float = 0.0

    def start(self) -> None:
        """Open all cameras and start reader threads."""
        self._running = True
        self._start_time = time.perf_counter()

        for dev_id in self._device_ids:
            cam_id = str(dev_id)
            cap = cv2.VideoCapture(dev_id)

            w, h = self._resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                raise RuntimeError(f"Could not open camera device {dev_id}")

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            logger.info(
                "Camera %s: %dx%d @ %.1f fps", cam_id, actual_w, actual_h, actual_fps
            )

            self._caps[cam_id] = cap
            self._buffers[cam_id] = deque(maxlen=self._buffer_size)
            self._locks[cam_id] = threading.Lock()
            self._frame_counts[cam_id] = 0

            thread = threading.Thread(
                target=self._reader_loop, args=(cam_id,), daemon=True
            )
            self._threads[cam_id] = thread
            thread.start()

    def _reader_loop(self, cam_id: str) -> None:
        """Continuously read frames from one camera."""
        cap = self._caps[cam_id]
        buf = self._buffers[cam_id]
        lock = self._locks[cam_id]

        while self._running:
            ret, frame = cap.read()
            if ret and frame is not None:
                ts = time.perf_counter()
                with lock:
                    buf.append((ts, frame))
                self._frame_counts[cam_id] += 1

    def get_synced_frames(self) -> Optional[Tuple[Dict[str, np.ndarray], float]]:
        """
        Return time-paired frames from all cameras.

        Uses the primary camera (first device ID) as the reference clock.
        For each other camera, picks the frame closest to the reference
        timestamp within the sync tolerance.

        Returns:
            (dict mapping camera_id -> frame, reference_timestamp)
            or None if sync fails.
        """
        primary_id = str(self._device_ids[0])

        with self._locks[primary_id]:
            if not self._buffers[primary_id]:
                return None
            ref_ts, ref_frame = self._buffers[primary_id][-1]

        result = {primary_id: ref_frame}

        for dev_id in self._device_ids[1:]:
            cam_id = str(dev_id)
            with self._locks[cam_id]:
                if not self._buffers[cam_id]:
                    return None

                best_frame = None
                best_delta = float("inf")
                for ts, frame in self._buffers[cam_id]:
                    delta = abs(ts - ref_ts)
                    if delta < best_delta:
                        best_delta = delta
                        best_frame = frame

            if best_frame is None or best_delta > self._max_sync_delta_s:
                logger.debug(
                    "Camera %s sync failed: best delta %.1f ms (max %.1f ms)",
                    cam_id,
                    best_delta * 1000,
                    self._max_sync_delta_s * 1000,
                )
                return None

            result[cam_id] = best_frame

        return result, ref_ts

    def get_fps_stats(self) -> Dict[str, float]:
        """Return achieved FPS per camera since start."""
        elapsed = time.perf_counter() - self._start_time
        if elapsed < 0.01:
            return {cam_id: 0.0 for cam_id in self._frame_counts}
        return {
            cam_id: count / elapsed
            for cam_id, count in self._frame_counts.items()
        }

    def release(self) -> None:
        """Stop threads and release all VideoCapture handles."""
        self._running = False
        for thread in self._threads.values():
            thread.join(timeout=2.0)
        for cap in self._caps.values():
            cap.release()
        self._caps.clear()
        self._buffers.clear()
        self._threads.clear()

    @staticmethod
    def detect_cameras(max_id: int = 10) -> List[int]:
        """
        Probe /dev/video0..N for valid capture devices.

        Linux creates two device nodes per USB camera (capture + metadata).
        This method only returns IDs that can actually capture frames.
        """
        valid = []
        for dev_id in range(max_id):
            cap = cv2.VideoCapture(dev_id)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    valid.append(dev_id)
            cap.release()
        return valid

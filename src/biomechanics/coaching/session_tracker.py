"""
Session Tracker for Set Boundary Detection

Monitors the timing gap between reps to detect when a set ends
(pause > set_timeout_seconds). Accumulates per-set and per-session
statistics and triggers set-complete messages through the IPCBridge.
"""

import statistics
import time
from typing import Any, Dict, List, Optional

from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.config import CoachingConfig
from biomechanics.utils.types import RepData


class SessionTracker:
    """
    Tracks set and session boundaries using rep timing.

    A set boundary is detected when the pause between consecutive reps
    exceeds ``set_timeout_seconds``. When a set ends, a summary is
    sent via the IPCBridge.
    """

    def __init__(
        self,
        ipc_bridge: IPCBridge,
        config: Optional[CoachingConfig] = None,
    ):
        config = config or CoachingConfig()
        self.ipc_bridge = ipc_bridge
        self.set_timeout: float = config.set_timeout_seconds

        # Current set state
        self.current_set_number: int = 0
        self.current_set_reps: List[RepData] = []
        self.last_rep_time: float = 0.0
        self.set_active: bool = False

        # Session-level accumulators
        self.total_reps: int = 0
        self.total_sets: int = 0
        self.all_reps: List[RepData] = []

        # Last completed set summary (populated in _end_current_set)
        self.last_set_summary: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Rep handling
    # ------------------------------------------------------------------

    def on_rep_complete(
        self,
        rep: RepData,
        bottom_kpts: Optional[List] = None,
        bottom_angles: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Process a completed rep. Detects set boundaries and forwards
        the rep to the IPCBridge.
        """
        now = rep.end_time

        # Check if the previous set timed out
        if self.set_active and self.last_rep_time > 0 and now - self.last_rep_time > self.set_timeout:
            self._end_current_set()

        # Start a new set if needed
        if not self.set_active:
            self.current_set_number += 1
            self.current_set_reps = []
            self.set_active = True

        self.current_set_reps.append(rep)
        self.ipc_bridge.send_rep_complete(
            rep, bottom_kpts=bottom_kpts, bottom_angles=bottom_angles,
        )

        self.last_rep_time = now
        self.total_reps += 1
        self.all_reps.append(rep)

    # ------------------------------------------------------------------
    # Set timeout polling
    # ------------------------------------------------------------------

    def check_set_timeout(self, current_time: Optional[float] = None) -> bool:
        """
        Check if the current set has timed out. Call this periodically
        (e.g. every frame) to detect set boundaries between reps.

        Returns:
            True if a set was ended, False otherwise.
        """
        now = current_time if current_time is not None else time.time()

        if self.set_active and self.last_rep_time > 0 and now - self.last_rep_time > self.set_timeout:
            self._end_current_set()
            return True

        return False

    # ------------------------------------------------------------------
    # Set lifecycle
    # ------------------------------------------------------------------

    def _end_current_set(self) -> None:
        """Finalize the current set and send summary via IPC."""
        if self.current_set_reps:
            self.last_set_summary = self._compute_set_summary(
                self.current_set_number, self.current_set_reps
            )
            self.ipc_bridge.send_set_complete(
                self.current_set_number, self.current_set_reps
            )
            self.total_sets += 1
        self.current_set_reps = []
        self.set_active = False

    def _compute_set_summary(
        self, set_number: int, reps: List[RepData]
    ) -> Dict[str, Any]:
        """Compute summary stats for a completed set."""
        depths = [r.max_depth_angle for r in reps]
        avg_depth = statistics.mean(depths) if depths else 0.0
        depth_consistency = statistics.stdev(depths) if len(depths) > 1 else 0.0

        fault_summary: Dict[str, Dict[str, Any]] = {}
        for rep in reps:
            for fault in rep.faults:
                key = fault.fault_type
                if key not in fault_summary:
                    fault_summary[key] = {"count": 0, "total_severity": 0.0}
                fault_summary[key]["count"] += 1
                fault_summary[key]["total_severity"] += fault.severity_score
        for data in fault_summary.values():
            data["avg_severity"] = round(data["total_severity"] / data["count"], 2)

        return {
            "set_number": set_number,
            "total_reps": len(reps),
            "clean_reps": sum(1 for r in reps if r.is_clean),
            "avg_depth": round(avg_depth, 1),
            "depth_consistency": round(depth_consistency, 1),
            "fault_summary": fault_summary,
        }

    def force_end_set(self) -> None:
        """Manually end the current set (e.g. user stops exercising)."""
        self._end_current_set()

    # ------------------------------------------------------------------
    # Session stats
    # ------------------------------------------------------------------

    @property
    def session_stats(self) -> Dict:
        """Aggregate statistics for the entire session."""
        return {
            "total_reps": self.total_reps,
            "total_sets": self.total_sets,
            "avg_depth": (
                sum(r.max_depth_angle for r in self.all_reps) / len(self.all_reps)
                if self.all_reps
                else 0.0
            ),
            "clean_rep_percentage": (
                sum(1 for r in self.all_reps if r.is_clean) / len(self.all_reps) * 100
                if self.all_reps
                else 0.0
            ),
        }

    def reset(self) -> None:
        """Reset all state for a new session."""
        self.current_set_number = 0
        self.current_set_reps = []
        self.last_rep_time = 0.0
        self.set_active = False
        self.total_reps = 0
        self.total_sets = 0
        self.all_reps = []

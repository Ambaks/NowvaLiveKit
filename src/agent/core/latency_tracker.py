"""
Latency Tracker
Tracks per-turn TTFT and end-to-end latency metrics for production monitoring.
Detects progressive degradation in long sessions.
"""

import logging
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Alert thresholds
TTFT_WARN_THRESHOLD = 1.5       # seconds
TTFT_ERROR_THRESHOLD = 3.0      # seconds
E2E_WARN_THRESHOLD = 3.0        # seconds
DEGRADATION_FACTOR = 2.0        # warn if recent TTFT > 2x early TTFT
EARLY_TURN_WINDOW = 5           # first N turns = "early"
RECENT_TURN_WINDOW = 5          # last N turns = "recent"
DEGRADATION_CHECK_INTERVAL = 10 # check every N turns


@dataclass
class TurnMetric:
    turn_number: int
    timestamp: float
    ttft: Optional[float] = None
    e2e_latency: Optional[float] = None


class LatencyTracker:
    """Singleton tracker for per-turn latency metrics."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._metrics: List[TurnMetric] = []
        self._metrics_by_turn: Dict[int, TurnMetric] = {}
        self._turn_counter = 0
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "LatencyTracker":
        return cls()

    def reset(self):
        """Reset all metrics for a new session."""
        with self._lock:
            self._metrics.clear()
            self._metrics_by_turn.clear()
            self._turn_counter = 0

    def record_ttft(self, ttft_seconds: float, turn_number: Optional[int] = None):
        """Record time-to-first-token for an LLM response."""
        with self._lock:
            if turn_number is None:
                self._turn_counter += 1
                turn_number = self._turn_counter

            # Find existing metric for this turn or create new
            metric = self._find_or_create(turn_number)
            metric.ttft = ttft_seconds

        # Alert on high TTFT
        if ttft_seconds > TTFT_ERROR_THRESHOLD:
            logger.error(f"[LATENCY] TTFT={ttft_seconds:.3f}s at turn {turn_number} — exceeds {TTFT_ERROR_THRESHOLD}s threshold")
        elif ttft_seconds > TTFT_WARN_THRESHOLD:
            logger.warning(f"[LATENCY] TTFT={ttft_seconds:.3f}s at turn {turn_number} — exceeds {TTFT_WARN_THRESHOLD}s threshold")

        # Periodic degradation check
        if turn_number % DEGRADATION_CHECK_INTERVAL == 0:
            warning = self.check_degradation()
            if warning:
                logger.warning(warning)

    def record_e2e_latency(self, latency_seconds: float, turn_number: Optional[int] = None):
        """Record end-to-end turn latency (user stops speaking → agent starts speaking)."""
        with self._lock:
            if turn_number is None:
                turn_number = self._turn_counter or 1

            metric = self._find_or_create(turn_number)
            metric.e2e_latency = latency_seconds

        if latency_seconds > E2E_WARN_THRESHOLD:
            logger.warning(f"[LATENCY] E2E={latency_seconds:.3f}s at turn {turn_number} — exceeds {E2E_WARN_THRESHOLD}s threshold")

    def _find_or_create(self, turn_number: int) -> TurnMetric:
        """Find existing metric for turn or create new one. Must hold lock."""
        metric = self._metrics_by_turn.get(turn_number)
        if metric is not None:
            return metric
        metric = TurnMetric(turn_number=turn_number, timestamp=time.time())
        self._metrics.append(metric)
        self._metrics_by_turn[turn_number] = metric
        return metric

    def get_stats(self) -> Dict:
        """Return p50, p90, p99 for TTFT and e2e latency."""
        with self._lock:
            ttfts = [m.ttft for m in self._metrics if m.ttft is not None]
            e2es = [m.e2e_latency for m in self._metrics if m.e2e_latency is not None]

        def _percentiles(values: List[float]) -> Dict:
            if not values:
                return {"p50": None, "p90": None, "p99": None, "count": 0}
            sorted_v = sorted(values)
            n = len(sorted_v)
            return {
                "p50": sorted_v[int(n * 0.5)] if n > 0 else None,
                "p90": sorted_v[int(n * 0.9)] if n > 0 else None,
                "p99": sorted_v[min(int(n * 0.99), n - 1)] if n > 0 else None,
                "count": n,
                "mean": statistics.mean(sorted_v),
            }

        return {
            "ttft": _percentiles(ttfts),
            "e2e": _percentiles(e2es),
            "total_turns": len(self._metrics),
        }

    def check_degradation(self) -> Optional[str]:
        """Check if recent TTFT is significantly worse than early TTFT."""
        with self._lock:
            ttft_metrics = [(m.turn_number, m.ttft) for m in self._metrics if m.ttft is not None]

        if len(ttft_metrics) < EARLY_TURN_WINDOW + RECENT_TURN_WINDOW:
            return None

        ttft_metrics.sort(key=lambda x: x[0])
        early_ttfts = [t for _, t in ttft_metrics[:EARLY_TURN_WINDOW]]
        recent_ttfts = [t for _, t in ttft_metrics[-RECENT_TURN_WINDOW:]]

        early_avg = statistics.mean(early_ttfts)
        recent_avg = statistics.mean(recent_ttfts)

        if early_avg > 0 and recent_avg > early_avg * DEGRADATION_FACTOR:
            return (
                f"[LATENCY] Progressive degradation detected — "
                f"early avg TTFT={early_avg:.3f}s, recent avg TTFT={recent_avg:.3f}s "
                f"({recent_avg / early_avg:.1f}x increase). Consider context pruning."
            )
        return None

    def log_summary(self):
        """Log a summary of all latency metrics for the session."""
        stats = self.get_stats()
        ttft = stats["ttft"]
        e2e = stats["e2e"]

        logger.info(
            f"[LATENCY SUMMARY] {stats['total_turns']} turns | "
            f"TTFT: p50={self._fmt(ttft['p50'])}s, p90={self._fmt(ttft['p90'])}s, p99={self._fmt(ttft['p99'])}s (n={ttft['count']}) | "
            f"E2E: p50={self._fmt(e2e['p50'])}s, p90={self._fmt(e2e['p90'])}s, p99={self._fmt(e2e['p99'])}s (n={e2e['count']})"
        )

        degradation = self.check_degradation()
        if degradation:
            logger.warning(degradation)

    @staticmethod
    def _fmt(val) -> str:
        return f"{val:.3f}" if val is not None else "N/A"

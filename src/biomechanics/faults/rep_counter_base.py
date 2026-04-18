"""
Rep Counter Protocol

Defines the interface that all rep counter implementations must satisfy.
The pipeline interacts with rep counters only through this protocol,
allowing different counting strategies per exercise (signal-based FSM,
BiLSTM classification, etc.).
"""

from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

from biomechanics.utils.types import FaultEvent, JointAngles, RepData, Skeleton3D


@runtime_checkable
class RepCounter(Protocol):
    """Abstract interface every rep counter must satisfy."""

    rep_count: int

    @property
    def in_rep(self) -> bool:
        """Whether currently inside a rep."""
        ...

    @property
    def phase(self) -> str:
        """Current phase name (e.g. 'idle', 'descending', 'bottom', 'ascending')."""
        ...

    def update(
        self,
        signal_value: float,
        timestamp: float,
        angles: Optional[JointAngles] = None,
        faults: Optional[List[FaultEvent]] = None,
    ) -> Tuple[Optional[RepData], Optional[str]]:
        """Process one frame. Returns (RepData, None) on rep completion,
        (None, feedback_str) on rejected rep, or (None, None) otherwise."""
        ...

    def reset(self) -> None:
        """Reset counter state for a new set."""
        ...

    def add_fault(self, fault: FaultEvent) -> None:
        """Attach a fault to the current in-progress rep."""
        ...

    def clear_current_faults(self) -> None:
        """Clear faults accumulated in the current rep."""
        ...

    def snapshot_rep_metrics(self) -> dict:
        """Return a snapshot of current rep metrics (for dashboard/IPC)."""
        ...

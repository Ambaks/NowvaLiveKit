"""
Shared Pydantic Data Types for Biomechanics Pipeline

All data structures used across pipeline layers are defined here for consistency.
Includes to_numpy() methods for interoperability with NumPy-based processing.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
import numpy as np


# =============================================================================
# 2D POSE TYPES
# =============================================================================

class Keypoint2D(BaseModel):
    """Single 2D keypoint with confidence score."""
    x: float
    y: float
    confidence: float = 0.0

    def to_numpy(self) -> np.ndarray:
        """Return as numpy array [x, y, confidence]."""
        return np.array([self.x, self.y, self.confidence])

    @classmethod
    def from_numpy(cls, arr: np.ndarray) -> "Keypoint2D":
        """Create from numpy array [x, y] or [x, y, confidence]."""
        if len(arr) >= 3:
            return cls(x=float(arr[0]), y=float(arr[1]), confidence=float(arr[2]))
        return cls(x=float(arr[0]), y=float(arr[1]))


class Skeleton2D(BaseModel):
    """
    Complete 2D skeleton (COCO 17 keypoint format).

    Keypoint indices:
    0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear,
    5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow,
    9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip,
    13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle
    """
    keypoints: List[Keypoint2D]
    timestamp: float = 0.0
    frame_index: int = 0

    def to_numpy(self) -> np.ndarray:
        """Return as numpy array of shape (N, 3) where columns are [x, y, confidence]."""
        return np.array([kp.to_numpy() for kp in self.keypoints])

    @classmethod
    def from_numpy(cls, arr: np.ndarray, timestamp: float = 0.0, frame_index: int = 0) -> "Skeleton2D":
        """Create from numpy array of shape (N, 2) or (N, 3)."""
        keypoints = [Keypoint2D.from_numpy(row) for row in arr]
        return cls(keypoints=keypoints, timestamp=timestamp, frame_index=frame_index)

    def get_keypoint(self, index: int) -> Optional[Keypoint2D]:
        """Get keypoint by index, returns None if index out of bounds."""
        if 0 <= index < len(self.keypoints):
            return self.keypoints[index]
        return None

    @property
    def mean_confidence(self) -> float:
        """Average confidence across all keypoints."""
        if not self.keypoints:
            return 0.0
        return sum(kp.confidence for kp in self.keypoints) / len(self.keypoints)


# COCO keypoint indices for convenient access
class CocoKeypoints:
    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 3
    RIGHT_EAR = 4
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    LEFT_KNEE = 13
    RIGHT_KNEE = 14
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16


class MultiViewPose(BaseModel):
    """Pose data from multiple camera views for triangulation."""
    views: Dict[str, Skeleton2D]  # camera_id -> Skeleton2D
    timestamp: float = 0.0
    frame_index: int = 0

    @property
    def num_views(self) -> int:
        return len(self.views)


# =============================================================================
# 3D POSE TYPES
# =============================================================================

class Point3D(BaseModel):
    """Single 3D point in world coordinates (meters)."""
    x: float
    y: float
    z: float
    confidence: float = 0.0

    def to_numpy(self) -> np.ndarray:
        """Return as numpy array [x, y, z]."""
        return np.array([self.x, self.y, self.z])

    @classmethod
    def from_numpy(cls, arr: np.ndarray, confidence: float = 1.0) -> "Point3D":
        """Create from numpy array [x, y, z]."""
        return cls(x=float(arr[0]), y=float(arr[1]), z=float(arr[2]), confidence=confidence)

    def distance_to(self, other: "Point3D") -> float:
        """Euclidean distance to another point."""
        return float(np.linalg.norm(self.to_numpy() - other.to_numpy()))


class Skeleton3D(BaseModel):
    """
    Complete 3D skeleton in world coordinates (meters).
    Same keypoint ordering as Skeleton2D (COCO 17).
    """
    keypoints: List[Point3D]
    timestamp: float = 0.0
    frame_index: int = 0

    def to_numpy(self) -> np.ndarray:
        """Return as numpy array of shape (N, 3) where columns are [x, y, z]."""
        return np.array([kp.to_numpy() for kp in self.keypoints])

    @classmethod
    def from_numpy(cls, arr: np.ndarray, confidences: Optional[np.ndarray] = None,
                   timestamp: float = 0.0, frame_index: int = 0) -> "Skeleton3D":
        """Create from numpy array of shape (N, 3)."""
        if confidences is None:
            confidences = np.ones(len(arr))
        keypoints = [Point3D.from_numpy(row, conf) for row, conf in zip(arr, confidences)]
        return cls(keypoints=keypoints, timestamp=timestamp, frame_index=frame_index)

    def get_keypoint(self, index: int) -> Optional[Point3D]:
        """Get keypoint by index, returns None if index out of bounds."""
        if 0 <= index < len(self.keypoints):
            return self.keypoints[index]
        return None


# =============================================================================
# JOINT ANGLES
# =============================================================================

class JointAngles(BaseModel):
    """
    Joint angles computed from inverse kinematics.
    All angles in degrees.
    """
    # Hip angles
    hip_flexion_l: float = 0.0
    hip_flexion_r: float = 0.0
    hip_adduction_l: float = 0.0
    hip_adduction_r: float = 0.0
    hip_rotation_l: float = 0.0
    hip_rotation_r: float = 0.0

    # Knee angles
    knee_flexion_l: float = 0.0
    knee_flexion_r: float = 0.0

    # Ankle angles
    ankle_dorsiflexion_l: float = 0.0
    ankle_dorsiflexion_r: float = 0.0

    # Trunk angles
    trunk_flexion: float = 0.0
    trunk_lateral_flexion: float = 0.0
    trunk_rotation: float = 0.0

    # Pelvis angles (relative to world)
    pelvis_tilt: float = 0.0
    pelvis_list: float = 0.0
    pelvis_rotation: float = 0.0

    timestamp: float = 0.0
    frame_index: int = 0

    def as_dict(self) -> Dict[str, float]:
        """Return all angles as a simple dict (excluding metadata)."""
        return {
            "hip_flexion_l": self.hip_flexion_l,
            "hip_flexion_r": self.hip_flexion_r,
            "hip_adduction_l": self.hip_adduction_l,
            "hip_adduction_r": self.hip_adduction_r,
            "hip_rotation_l": self.hip_rotation_l,
            "hip_rotation_r": self.hip_rotation_r,
            "knee_flexion_l": self.knee_flexion_l,
            "knee_flexion_r": self.knee_flexion_r,
            "ankle_dorsiflexion_l": self.ankle_dorsiflexion_l,
            "ankle_dorsiflexion_r": self.ankle_dorsiflexion_r,
            "trunk_flexion": self.trunk_flexion,
            "trunk_lateral_flexion": self.trunk_lateral_flexion,
            "trunk_rotation": self.trunk_rotation,
            "pelvis_tilt": self.pelvis_tilt,
            "pelvis_list": self.pelvis_list,
            "pelvis_rotation": self.pelvis_rotation,
        }

    def to_numpy(self) -> np.ndarray:
        """Return angles as numpy array in consistent order."""
        return np.array(list(self.as_dict().values()))

    @property
    def avg_knee_flexion(self) -> float:
        """Average knee flexion (useful for squat depth)."""
        return (self.knee_flexion_l + self.knee_flexion_r) / 2

    @property
    def knee_asymmetry(self) -> float:
        """Absolute difference in knee flexion between sides."""
        return abs(self.knee_flexion_l - self.knee_flexion_r)

    @property
    def hip_asymmetry(self) -> float:
        """Absolute difference in hip flexion between sides."""
        return abs(self.hip_flexion_l - self.hip_flexion_r)


# =============================================================================
# FAULT DETECTION
# =============================================================================

class FaultSeverity(str, Enum):
    """Severity levels for detected faults."""
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"

    @classmethod
    def from_score(cls, score: float) -> "FaultSeverity":
        """Convert numeric score (0-3) to severity level."""
        if score < 0.5:
            return cls.NONE
        elif score < 1.5:
            return cls.MILD
        elif score < 2.5:
            return cls.MODERATE
        else:
            return cls.SEVERE


class FaultEvent(BaseModel):
    """A detected fault/form error during exercise."""
    fault_type: str  # e.g., "knee_valgus", "forward_lean", "heel_rise"
    severity: FaultSeverity
    severity_score: float = Field(ge=0.0, le=3.0)  # 0=none, 1=mild, 2=moderate, 3=severe
    message: str  # Human-readable description
    timestamp: float = 0.0
    frame_index: int = 0
    rep_number: int = 0

    # Optional details for specific fault types
    details: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_significant(self) -> bool:
        """Return True if fault is moderate or severe."""
        return self.severity in (FaultSeverity.MODERATE, FaultSeverity.SEVERE)


class FaultType:
    """Known fault type constants."""
    KNEE_VALGUS = "knee_valgus"
    KNEE_VARUS = "knee_varus"
    FORWARD_LEAN = "forward_lean"
    HEEL_RISE = "heel_rise"
    DEPTH = "depth"
    BILATERAL_ASYMMETRY = "bilateral_asymmetry"
    BACK_ROUNDING = "back_rounding"
    HIP_SHIFT = "hip_shift"


# =============================================================================
# REP AND SESSION TRACKING
# =============================================================================

# =============================================================================
# DEPTH CLASS CONSTANTS (5-class squat depth classification)
# =============================================================================

DEPTH_CLASS_NAMES = {
    0: "Standing",
    1: "Quarter",
    2: "Half",
    3: "Parallel",
    4: "Deep",
}

DEPTH_CLASS_BINS_DEG = [
    (0.0, 40.0),     # 0 = Standing
    (40.0, 60.0),    # 1 = Quarter
    (60.0, 80.0),    # 2 = Half
    (80.0, 100.0),   # 3 = Parallel
    (100.0, 180.0),  # 4 = Deep
]

NUM_DEPTH_CLASSES = len(DEPTH_CLASS_BINS_DEG)


def depth_class_from_angle(knee_angle_deg: float) -> int:
    """Return the depth class (0-4) for a given knee flexion angle in degrees."""
    for cls_idx in range(len(DEPTH_CLASS_BINS_DEG) - 1, -1, -1):
        lo, _ = DEPTH_CLASS_BINS_DEG[cls_idx]
        if knee_angle_deg >= lo:
            return cls_idx
    return 0


class RepPhase(str, Enum):
    """Phase of a rep in the movement cycle."""
    STANDING = "standing"  # Starting position
    DESCENDING = "descending"  # Eccentric phase
    BOTTOM = "bottom"  # Lowest point
    ASCENDING = "ascending"  # Concentric phase


class RepData(BaseModel):
    """Data for a single completed rep."""
    rep_number: int
    start_time: float
    end_time: float
    start_frame: int
    end_frame: int

    # Depth metrics (for squats)
    max_depth_angle: float = 0.0  # Maximum knee flexion achieved
    min_depth_angle: float = 0.0  # Starting knee flexion

    # Timing
    descent_time: float = 0.0  # Time in seconds for eccentric phase
    ascent_time: float = 0.0  # Time in seconds for concentric phase

    # Quality
    faults: List[FaultEvent] = Field(default_factory=list)

    # Symmetry
    avg_knee_asymmetry: float = 0.0
    avg_hip_asymmetry: float = 0.0

    # 5-class depth classification (from BiLSTM)
    depth_class: Optional[int] = None
    depth_class_name: Optional[str] = None
    max_depth_class: Optional[int] = None

    @property
    def duration(self) -> float:
        """Total rep duration in seconds."""
        return self.end_time - self.start_time

    @property
    def is_clean(self) -> bool:
        """Return True if rep had no significant faults."""
        return not any(f.is_significant for f in self.faults)

    @property
    def tempo_ratio(self) -> float:
        """Ratio of descent to ascent time (ideal is ~1.5-2.0 for controlled squats)."""
        if self.ascent_time > 0:
            return self.descent_time / self.ascent_time
        return 0.0


class SessionState(BaseModel):
    """State of the current workout session for biomechanics tracking."""
    exercise_name: str
    set_number: int = 1
    rep_number: int = 0
    current_phase: RepPhase = RepPhase.STANDING

    # Rep tracking
    reps: List[RepData] = Field(default_factory=list)
    current_rep_start_time: Optional[float] = None
    current_rep_start_frame: Optional[int] = None

    # Set tracking
    set_start_time: float = 0.0
    last_movement_time: float = 0.0  # For detecting set boundaries

    # Accumulated faults in current rep
    current_rep_faults: List[FaultEvent] = Field(default_factory=list)

    @property
    def total_faults(self) -> int:
        """Total faults across all completed reps."""
        return sum(len(r.faults) for r in self.reps)

    @property
    def avg_depth(self) -> float:
        """Average depth across completed reps."""
        if not self.reps:
            return 0.0
        return sum(r.max_depth_angle for r in self.reps) / len(self.reps)


# =============================================================================
# PIPELINE OUTPUT
# =============================================================================

class PipelineFrame(BaseModel):
    """
    Complete output from one pipeline iteration.
    Contains all data from each processing layer.
    """
    frame_index: int
    timestamp: float

    # Layer 1: 2D Pose
    skeleton_2d: Optional[Skeleton2D] = None
    multi_view: Optional[MultiViewPose] = None

    # Layer 2: 3D Reconstruction
    skeleton_3d: Optional[Skeleton3D] = None

    # Layer 3: Kinematics
    joint_angles: Optional[JointAngles] = None

    # Layer 4: Fault Detection
    faults: List[FaultEvent] = Field(default_factory=list)
    rep_data: Optional[RepData] = None  # Set when rep completes

    # BiLSTM rep counting (optional, populated when bilstm.enabled=True)
    bilstm_probability: Optional[float] = None
    bilstm_rep_data: Optional[RepData] = None
    bilstm_depth_class: Optional[int] = None
    bilstm_depth_class_name: Optional[str] = None
    bilstm_class_probabilities: Optional[List[float]] = None

    # Metadata
    latency_ms: Dict[str, float] = Field(default_factory=dict)  # Per-layer timing

    @property
    def success(self) -> bool:
        """Return True if pipeline produced valid output."""
        return self.joint_angles is not None

    @property
    def total_latency_ms(self) -> float:
        """Total pipeline latency in milliseconds."""
        return sum(self.latency_ms.values())


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_empty_skeleton_2d(num_keypoints: int = 17) -> Skeleton2D:
    """Create an empty 2D skeleton with zero-confidence keypoints."""
    keypoints = [Keypoint2D(x=0.0, y=0.0, confidence=0.0) for _ in range(num_keypoints)]
    return Skeleton2D(keypoints=keypoints)


def create_empty_skeleton_3d(num_keypoints: int = 17) -> Skeleton3D:
    """Create an empty 3D skeleton with zero-confidence keypoints."""
    keypoints = [Point3D(x=0.0, y=0.0, z=0.0, confidence=0.0) for _ in range(num_keypoints)]
    return Skeleton3D(keypoints=keypoints)


def depth_category(knee_angle: float) -> str:
    """
    Categorize squat depth based on knee flexion angle.

    Args:
        knee_angle: Knee flexion angle in degrees

    Returns:
        Depth category string
    """
    if knee_angle >= 100:
        return "below_parallel"
    elif knee_angle >= 90:
        return "parallel"
    elif knee_angle >= 60:
        return "half"
    else:
        return "quarter"

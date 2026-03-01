"""
Shared Pytest Fixtures for Biomechanics Tests

Provides common test data and utilities used across test modules.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.utils.types import (
    Keypoint2D,
    Skeleton2D,
    Point3D,
    Skeleton3D,
    JointAngles,
    FaultEvent,
    FaultSeverity,
    RepData,
    PipelineFrame,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_keypoints_2d() -> np.ndarray:
    """
    Load sample 2D keypoints (COCO 17 format) for a half-squat pose.

    Returns:
        numpy array of shape (17, 3) where columns are [x, y, confidence]
    """
    with open(FIXTURES_DIR / "sample_keypoints.json") as f:
        data = json.load(f)
    return np.array(data["keypoints"])


@pytest.fixture
def sample_skeleton_2d(sample_keypoints_2d) -> Skeleton2D:
    """Sample 2D skeleton from fixture keypoints."""
    return Skeleton2D.from_numpy(sample_keypoints_2d)


@pytest.fixture
def sample_3d_points() -> np.ndarray:
    """
    Load sample 3D points (same pose in meters).

    Returns:
        numpy array of shape (17, 3) where columns are [x, y, z]
    """
    with open(FIXTURES_DIR / "sample_3d_points.json") as f:
        data = json.load(f)
    return np.array(data["points"])


@pytest.fixture
def sample_skeleton_3d(sample_3d_points) -> Skeleton3D:
    """Sample 3D skeleton from fixture points."""
    return Skeleton3D.from_numpy(sample_3d_points)


@pytest.fixture
def sample_joint_angles() -> JointAngles:
    """
    Load expected joint angles for the sample pose.

    These are the "ground truth" angles for the half-squat pose.
    """
    with open(FIXTURES_DIR / "sample_angles.json") as f:
        data = json.load(f)
    return JointAngles(**data["angles"])


@pytest.fixture
def expected_angles_dict() -> dict:
    """Expected angles as a dict for comparison."""
    with open(FIXTURES_DIR / "sample_angles.json") as f:
        data = json.load(f)
    return data["angles"]


@pytest.fixture
def sample_fault_event() -> FaultEvent:
    """Sample fault event for testing."""
    return FaultEvent(
        fault_type="knee_valgus",
        severity=FaultSeverity.MODERATE,
        severity_score=2.0,
        message="Knees tracking inward",
        rep_number=1,
    )


@pytest.fixture
def sample_rep_data(sample_fault_event) -> RepData:
    """Sample rep data for testing."""
    return RepData(
        rep_number=1,
        start_time=0.0,
        end_time=2.5,
        start_frame=0,
        end_frame=75,
        max_depth_angle=85.0,
        min_depth_angle=15.0,
        descent_time=1.2,
        ascent_time=1.0,
        faults=[sample_fault_event],
    )


@pytest.fixture
def sample_pipeline_frame(
    sample_skeleton_2d, sample_skeleton_3d, sample_joint_angles
) -> PipelineFrame:
    """Sample complete pipeline frame for testing."""
    return PipelineFrame(
        frame_index=100,
        timestamp=3.33,
        skeleton_2d=sample_skeleton_2d,
        skeleton_3d=sample_skeleton_3d,
        joint_angles=sample_joint_angles,
        faults=[],
        latency_ms={"pose": 8.0, "ik": 4.0, "faults": 1.0},
    )


# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def angle_tolerance() -> float:
    """Tolerance for angle comparisons (degrees)."""
    return 5.0


@pytest.fixture
def position_tolerance() -> float:
    """Tolerance for position comparisons (meters)."""
    return 0.01


# =============================================================================
# MOCK FIXTURES
# =============================================================================

@pytest.fixture
def mock_ipc_client():
    """Mock IPC client for testing coaching integration."""
    class MockIPCClient:
        def __init__(self):
            self.messages = []
            self.connected = True

        def send_message(self, message):
            self.messages.append(message)

        def connect(self, timeout=10):
            return True

        def disconnect(self):
            self.connected = False

    return MockIPCClient()

"""
Tests for Coaching Module

Tests CueCache, IPCBridge, and SessionTracker with a mock IPC client.
Verifies cue mapping, rate limiting, message formatting, and set detection.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.coaching.cue_cache import (
    DEADLIFT_CUES,
    DEFAULT_CUES,
    POSITIVE_CUE_KEYS,
    SQUAT_CUES,
    CueCache,
)
from biomechanics.coaching.ipc_bridge import IPCBridge
from biomechanics.coaching.session_tracker import SessionTracker
from biomechanics.config import CoachingConfig, IPCConfig
from biomechanics.utils.types import (
    FaultEvent,
    FaultSeverity,
    JointAngles,
    PipelineFrame,
    RepData,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def coaching_config():
    """CoachingConfig with short set timeout for faster tests."""
    return CoachingConfig(min_cue_gap_seconds=2.0, set_timeout_seconds=5.0)


@pytest.fixture
def ipc_config():
    return IPCConfig(frame_send_interval=10, fault_cooldown_seconds=3.0)


@pytest.fixture
def cue_cache(coaching_config):
    return CueCache(coaching_config)


@pytest.fixture
def ipc_bridge(mock_ipc_client, coaching_config, ipc_config):
    return IPCBridge(mock_ipc_client, coaching_config, ipc_config)


@pytest.fixture
def session_tracker(ipc_bridge, coaching_config):
    return SessionTracker(ipc_bridge, coaching_config)


# =============================================================================
# HELPERS
# =============================================================================


def make_rep(
    rep_number,
    start_time=0.0,
    duration=2.5,
    depth=95.0,
    faults=None,
):
    """Create a RepData for testing."""
    return RepData(
        rep_number=rep_number,
        start_time=start_time,
        end_time=start_time + duration,
        start_frame=0,
        end_frame=75,
        max_depth_angle=depth,
        min_depth_angle=15.0,
        descent_time=duration * 0.48,
        ascent_time=duration * 0.4,
        faults=faults or [],
    )


def make_fault(fault_type="knee_valgus", severity=FaultSeverity.MODERATE, timestamp=0.0):
    """Create a FaultEvent for testing."""
    return FaultEvent(
        fault_type=fault_type,
        severity=severity,
        severity_score=float({"none": 0, "mild": 1, "moderate": 2, "severe": 3}[severity.value]),
        message=f"Test fault: {fault_type}",
        timestamp=timestamp,
        rep_number=1,
    )


# =============================================================================
# TEST CUE CACHE
# =============================================================================


class TestCueCache:
    """Test CueCache cue management and rate limiting."""

    def test_prepare_squat_cues(self, cue_cache):
        """prepare_for_exercise with 'squat' should load SQUAT_CUES."""
        cues = cue_cache.prepare_for_exercise("squat")
        assert "knees_out" in cues
        assert "deeper" in cues
        assert "rep_1" in cues
        assert "rep_20" in cues
        assert cue_cache.current_exercise == "squat"

    def test_prepare_barbell_back_squat(self, cue_cache):
        """'Barbell Back Squat' normalizes to 'barbell_back_squat' — not in map, gets DEFAULT_CUES.
        But 'Back Squat' normalizes to 'back_squat' which IS in the map."""
        cues = cue_cache.prepare_for_exercise("Back Squat")
        assert "knees_out" in cues  # SQUAT_CUES
        assert cue_cache.current_exercise == "back_squat"

    def test_prepare_deadlift(self, cue_cache):
        """Should load DEADLIFT_CUES for deadlift variants."""
        cues = cue_cache.prepare_for_exercise("romanian_deadlift")
        assert "hips_through" in cues
        assert "flat_back" in cues
        assert "knees_out" not in cues

    def test_prepare_unknown_exercise_gets_defaults(self, cue_cache):
        """Unknown exercise should fall back to DEFAULT_CUES."""
        cues = cue_cache.prepare_for_exercise("overhead_press")
        assert "good_rep" in cues
        assert "knees_out" not in cues
        assert "rep_1" in cues

    def test_get_cue_for_fault_mapping(self, cue_cache):
        """Should map fault types to correct cue keys."""
        cue_cache.prepare_for_exercise("squat")
        assert cue_cache.get_cue_for_fault("knee_valgus", 10.0) == "knees_out"

    def test_get_cue_for_fault_rate_limited(self, cue_cache):
        """Second call within min_cue_gap should return None."""
        cue_cache.prepare_for_exercise("squat")
        cue1 = cue_cache.get_cue_for_fault("knee_valgus", 10.0)
        assert cue1 == "knees_out"
        # Only 1s later — needs 2s gap
        cue2 = cue_cache.get_cue_for_fault("forward_lean", 11.0)
        assert cue2 is None

    def test_get_cue_for_fault_after_gap(self, cue_cache):
        """Cue should be returned after sufficient time gap."""
        cue_cache.prepare_for_exercise("squat")
        cue_cache.get_cue_for_fault("knee_valgus", 10.0)
        cue = cue_cache.get_cue_for_fault("forward_lean", 12.5)
        assert cue == "chest_up"

    def test_get_cue_for_unknown_fault(self, cue_cache):
        """Unknown fault type should return None."""
        cue_cache.prepare_for_exercise("squat")
        assert cue_cache.get_cue_for_fault("unknown_fault", 10.0) is None

    def test_get_cue_fault_not_in_exercise_cues(self, cue_cache):
        """Fault maps to cue key not in current exercise cues → None."""
        cue_cache.prepare_for_exercise("deadlift")
        # "depth" → "deeper", but "deeper" is not in DEADLIFT_CUES
        assert cue_cache.get_cue_for_fault("depth", 10.0) is None

    def test_get_rep_cue_valid(self, cue_cache):
        """Should return rep cue key for valid rep numbers."""
        cue_cache.prepare_for_exercise("squat")
        assert cue_cache.get_rep_cue(1) == "rep_1"
        assert cue_cache.get_rep_cue(20) == "rep_20"

    def test_get_rep_cue_out_of_range(self, cue_cache):
        """Should return None for rep > 20."""
        cue_cache.prepare_for_exercise("squat")
        assert cue_cache.get_rep_cue(21) is None

    def test_get_positive_cue(self, cue_cache):
        """Should return one of the positive cue keys."""
        cue_cache.prepare_for_exercise("squat")
        positive = cue_cache.get_positive_cue()
        assert positive in POSITIVE_CUE_KEYS

    def test_get_positive_cue_deadlift(self, cue_cache):
        """Deadlift has fewer positive cues — should still work."""
        cue_cache.prepare_for_exercise("deadlift")
        positive = cue_cache.get_positive_cue()
        assert positive in {"good_rep", "strong"}

    def test_returned_dict_is_copy(self, cue_cache):
        """Returned dict should not mutate internal state."""
        cues = cue_cache.prepare_for_exercise("squat")
        cues["injected"] = "bad"
        assert "injected" not in cue_cache.cues


# =============================================================================
# TEST IPC BRIDGE
# =============================================================================


class TestIPCBridge:
    """Test IPCBridge message formatting and throttling."""

    def test_prepare_exercise_sends_cache_cues(self, ipc_bridge, mock_ipc_client):
        """prepare_exercise should send cache_cues message."""
        ipc_bridge.prepare_exercise("squat")
        msg = mock_ipc_client.messages[-1]
        assert msg["type"] == "cache_cues"
        assert msg["exercise_name"] == "squat"
        assert "knees_out" in msg["cues"]

    def test_send_frame_data_throttled(self, ipc_bridge, mock_ipc_client):
        """Should only send every Nth frame."""
        for i in range(25):
            frame = PipelineFrame(
                frame_index=i,
                timestamp=i * 0.033,
                joint_angles=JointAngles(knee_flexion_l=90.0, knee_flexion_r=90.0),
                latency_ms={"pose": 8.0, "ik": 4.0},
            )
            ipc_bridge.send_frame_data(frame)

        frame_msgs = [m for m in mock_ipc_client.messages if m["type"] == "frame_data"]
        # counter starts at 0, increments to 1..25; fires at 10 and 20
        assert len(frame_msgs) == 2

    def test_send_frame_data_skips_no_angles(self, ipc_bridge, mock_ipc_client):
        """Should not send when joint_angles is None."""
        ipc_bridge.frame_counter = 9  # next increment → 10
        frame = PipelineFrame(frame_index=10, timestamp=0.33)
        ipc_bridge.send_frame_data(frame)
        frame_msgs = [m for m in mock_ipc_client.messages if m["type"] == "frame_data"]
        assert len(frame_msgs) == 0

    def test_send_fault_with_cue(self, ipc_bridge, mock_ipc_client):
        """send_fault should include cue from cue_cache."""
        ipc_bridge.prepare_exercise("squat")
        fault = make_fault("knee_valgus", timestamp=10.0)
        ipc_bridge.send_fault(fault)
        fault_msgs = [m for m in mock_ipc_client.messages if m["type"] == "fault"]
        assert len(fault_msgs) == 1
        assert fault_msgs[0]["cue"] == "knees_out"
        assert fault_msgs[0]["severity"] == "moderate"

    def test_send_fault_cooldown_same_type(self, ipc_bridge, mock_ipc_client):
        """Same fault_type within cooldown should be suppressed."""
        ipc_bridge.prepare_exercise("squat")
        ipc_bridge.send_fault(make_fault("knee_valgus", timestamp=10.0))
        ipc_bridge.send_fault(make_fault("knee_valgus", timestamp=11.0))  # 1s < 3s cooldown
        fault_msgs = [m for m in mock_ipc_client.messages if m["type"] == "fault"]
        assert len(fault_msgs) == 1

    def test_send_fault_different_types_no_shared_cooldown(self, ipc_bridge, mock_ipc_client):
        """Different fault types should not share cooldown."""
        ipc_bridge.prepare_exercise("squat")
        ipc_bridge.send_fault(make_fault("knee_valgus", timestamp=10.0))
        ipc_bridge.send_fault(make_fault("forward_lean", severity=FaultSeverity.MILD, timestamp=10.5))
        fault_msgs = [m for m in mock_ipc_client.messages if m["type"] == "fault"]
        assert len(fault_msgs) == 2

    def test_send_rep_complete_messages(self, ipc_bridge, mock_ipc_client):
        """Should send rep_complete and legacy rep_count (no play_cue — orchestrator handles those)."""
        ipc_bridge.prepare_exercise("squat")
        rep = make_rep(rep_number=1, depth=95.0)
        ipc_bridge.send_rep_complete(rep)

        types = [m["type"] for m in mock_ipc_client.messages]
        assert "rep_complete" in types
        assert "rep_count" in types
        assert "play_cue" not in types  # Orchestrator handles cue dispatch now

        rep_msg = next(m for m in mock_ipc_client.messages if m["type"] == "rep_complete")
        assert rep_msg["depth_category"] == "parallel"
        assert rep_msg["rep_number"] == 1
        assert rep_msg["is_clean"] is True

    def test_send_rep_complete_no_play_cue_messages(self, ipc_bridge, mock_ipc_client):
        """IPCBridge should not send play_cue — CoachingOrchestrator handles cue dispatch."""
        ipc_bridge.prepare_exercise("squat")
        rep = make_rep(rep_number=1, depth=105.0)
        ipc_bridge.send_rep_complete(rep)

        play_cues = [m for m in mock_ipc_client.messages if m["type"] == "play_cue"]
        assert len(play_cues) == 0

    def test_send_set_complete(self, ipc_bridge, mock_ipc_client):
        """Should compute and send set summary."""
        ipc_bridge.prepare_exercise("squat")
        reps = [make_rep(1, depth=90.0), make_rep(2, depth=100.0), make_rep(3, depth=95.0)]
        ipc_bridge.send_set_complete(1, reps)

        set_msg = next(m for m in mock_ipc_client.messages if m["type"] == "set_complete")
        assert set_msg["set_number"] == 1
        assert set_msg["total_reps"] == 3
        assert 90.0 <= set_msg["avg_depth"] <= 100.0
        assert set_msg["clean_reps"] == 3

    def test_send_set_complete_empty_reps(self, ipc_bridge, mock_ipc_client):
        """Should not send anything for empty rep list."""
        initial_count = len(mock_ipc_client.messages)
        ipc_bridge.send_set_complete(1, [])
        assert len(mock_ipc_client.messages) == initial_count

    def test_send_pipeline_status(self, ipc_bridge, mock_ipc_client):
        """Should send pipeline status message."""
        ipc_bridge.send_pipeline_status("running", {"pose": 8.0, "ik": 4.0})
        msg = mock_ipc_client.messages[-1]
        assert msg["type"] == "pipeline_status"
        assert msg["status"] == "running"
        assert msg["latency_ms"]["pose"] == 8.0

    def test_depth_categories(self):
        """Verify depth category thresholds."""
        assert IPCBridge._depth_category(105.0) == "below_parallel"
        assert IPCBridge._depth_category(95.0) == "parallel"
        assert IPCBridge._depth_category(75.0) == "half"
        assert IPCBridge._depth_category(45.0) == "quarter"


# =============================================================================
# TEST SESSION TRACKER
# =============================================================================


class TestSessionTracker:
    """Test SessionTracker set boundary detection and session stats."""

    def test_first_rep_starts_set(self, session_tracker, mock_ipc_client):
        """First rep should start set 1."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        assert session_tracker.current_set_number == 1
        assert session_tracker.set_active is True
        assert session_tracker.total_reps == 1

    def test_consecutive_reps_same_set(self, session_tracker):
        """Reps within timeout should stay in same set."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        session_tracker.on_rep_complete(make_rep(2, start_time=3.0))
        session_tracker.on_rep_complete(make_rep(3, start_time=6.0))
        assert session_tracker.current_set_number == 1
        assert len(session_tracker.current_set_reps) == 3

    def test_timeout_triggers_new_set(self, session_tracker, mock_ipc_client):
        """Gap > set_timeout between reps should end set and start new one."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        session_tracker.on_rep_complete(make_rep(2, start_time=3.0))
        # Rep 3 arrives after >5s gap (timeout is 5s in fixture)
        session_tracker.on_rep_complete(make_rep(3, start_time=11.0))

        assert session_tracker.current_set_number == 2
        assert session_tracker.total_sets == 1
        set_msgs = [m for m in mock_ipc_client.messages if m["type"] == "set_complete"]
        assert len(set_msgs) == 1
        assert set_msgs[0]["total_reps"] == 2

    def test_check_set_timeout_expired(self, session_tracker):
        """check_set_timeout should detect timeout and end set."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        # end_time = 2.5, so we need current_time > 2.5 + 5.0 = 7.5
        ended = session_tracker.check_set_timeout(current_time=8.0)
        assert ended is True
        assert session_tracker.set_active is False
        assert session_tracker.total_sets == 1

    def test_check_set_timeout_not_expired(self, session_tracker):
        """check_set_timeout should return False if not expired."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        # end_time = 2.5, gap = 4.0 - 2.5 = 1.5 < 5.0 timeout
        ended = session_tracker.check_set_timeout(current_time=4.0)
        assert ended is False
        assert session_tracker.set_active is True

    def test_force_end_set(self, session_tracker, mock_ipc_client):
        """force_end_set should immediately end the current set."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        session_tracker.on_rep_complete(make_rep(2, start_time=3.0))
        session_tracker.force_end_set()
        assert session_tracker.set_active is False
        set_msgs = [m for m in mock_ipc_client.messages if m["type"] == "set_complete"]
        assert len(set_msgs) == 1

    def test_session_stats(self, session_tracker):
        """session_stats should aggregate across all reps."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0, depth=90.0))
        session_tracker.on_rep_complete(make_rep(2, start_time=3.0, depth=100.0))
        stats = session_tracker.session_stats
        assert stats["total_reps"] == 2
        assert stats["avg_depth"] == 95.0
        assert stats["clean_rep_percentage"] == 100.0

    def test_reset(self, session_tracker):
        """reset should clear all session state."""
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0))
        session_tracker.reset()
        assert session_tracker.total_reps == 0
        assert session_tracker.total_sets == 0
        assert session_tracker.current_set_number == 0
        assert session_tracker.all_reps == []

    def test_multiple_sets_full_workflow(self, session_tracker, mock_ipc_client):
        """Full workflow: 2 sets with timeout between them."""
        # Set 1: 3 reps
        session_tracker.on_rep_complete(make_rep(1, start_time=0.0, depth=90.0))
        session_tracker.on_rep_complete(make_rep(2, start_time=2.5, depth=95.0))
        session_tracker.on_rep_complete(make_rep(3, start_time=5.0, depth=92.0))

        # Timeout detected
        session_tracker.check_set_timeout(current_time=12.0)

        # Set 2: 2 reps
        session_tracker.on_rep_complete(make_rep(4, start_time=15.0, depth=100.0))
        session_tracker.on_rep_complete(make_rep(5, start_time=17.5, depth=98.0))
        session_tracker.force_end_set()

        assert session_tracker.total_sets == 2
        assert session_tracker.total_reps == 5
        set_msgs = [m for m in mock_ipc_client.messages if m["type"] == "set_complete"]
        assert len(set_msgs) == 2
        assert set_msgs[0]["total_reps"] == 3
        assert set_msgs[1]["total_reps"] == 2

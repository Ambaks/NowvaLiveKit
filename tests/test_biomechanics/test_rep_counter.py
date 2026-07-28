"""
Tests for Rep Counter

Tests the RepCounter state machine with synthetic angle sequences.
Verifies rep detection, timing, and depth tracking.
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.utils.types import JointAngles, FaultEvent, FaultSeverity
from biomechanics.faults.rep_counter import RepCounter, RepCounterConfig, RepState


class TestRepCounterBasics:
    """Test basic RepCounter functionality."""

    def test_initial_state(self):
        """RepCounter should start in IDLE state with 0 reps."""
        counter = RepCounter()
        assert counter.state == RepState.IDLE
        assert counter.rep_count == 0
        assert not counter.in_rep

    def test_custom_config(self):
        """RepCounter should accept custom configuration."""
        config = RepCounterConfig(
            entry_hip_angle=40.0,
            min_rep_duration_frames=30,
        )
        counter = RepCounter(config)
        assert counter.config.entry_hip_angle == 40.0
        assert counter.config.min_rep_duration_frames == 30

    def test_reset(self):
        """Reset should return counter to initial state."""
        counter = RepCounter()
        counter.rep_count = 5
        counter.state = RepState.DESCENDING
        counter.reset()
        assert counter.state == RepState.IDLE
        assert counter.rep_count == 0


class TestRepDetection:
    """Test rep detection state transitions."""

    def create_angles(
        self,
        frame: int,
        hip_flexion: float = 0.0,
        knee_flexion: float = 0.0,
        timestamp: float = 0.0,
    ) -> JointAngles:
        """Create JointAngles with specified hip/knee flexion."""
        return JointAngles(
            hip_flexion_l=hip_flexion,
            hip_flexion_r=hip_flexion,
            knee_flexion_l=knee_flexion,
            knee_flexion_r=knee_flexion,
            frame_index=frame,
            timestamp=timestamp,
        )

    def test_rep_entry(self):
        """Counter should transition to DESCENDING when threshold crossed (without derivatives)."""
        counter = RepCounter()

        # Start below threshold
        angles = self.create_angles(0, hip_flexion=15.0, knee_flexion=15.0)
        result, feedback = counter.update(angles)
        assert counter.state == RepState.IDLE
        assert result is None

        # Cross threshold (without derivatives, just position-based)
        angles = self.create_angles(1, hip_flexion=25.0, knee_flexion=30.0)
        result, feedback = counter.update(angles)
        assert counter.state == RepState.DESCENDING
        assert result is None  # Rep not complete yet

    def test_rep_exit_minimum_duration(self):
        """Rep should only count if minimum duration met."""
        config = RepCounterConfig(min_rep_duration_frames=20, min_depth_knee_angle=30.0)
        counter = RepCounter(config)

        # Enter rep
        angles = self.create_angles(0, hip_flexion=25.0, knee_flexion=40.0)
        counter.update(angles)
        assert counter.in_rep  # Could be DESCENDING, BOTTOM, or ASCENDING

        # Exit immediately (duration too short)
        angles = self.create_angles(5, hip_flexion=10.0, knee_flexion=10.0)
        result, feedback = counter.update(angles)
        # State should either be IDLE or transitioning through ASCENDING
        assert counter.state in (RepState.IDLE, RepState.ASCENDING)
        assert counter.rep_count == 0
        assert result is None  # Rep not counted due to short duration

    def test_full_rep_cycle(self):
        """Complete rep cycle should increment count and return RepData."""
        config = RepCounterConfig(
            entry_hip_angle=20.0,
            exit_hip_angle=18.0,
            min_rep_duration_frames=10,
            min_depth_knee_angle=90.0,
        )
        counter = RepCounter(config)

        # Standing
        counter.update(self.create_angles(0, hip_flexion=10.0, knee_flexion=10.0, timestamp=0.0))
        assert counter.state == RepState.IDLE

        # Enter rep (descending)
        counter.update(self.create_angles(1, hip_flexion=25.0, knee_flexion=40.0, timestamp=0.033))
        assert counter.in_rep

        # Continue descending to max depth
        for i in range(2, 8):
            depth = 40.0 + (i - 2) * 15  # 40 -> 130 degrees
            counter.update(self.create_angles(i, hip_flexion=depth * 0.8, knee_flexion=depth, timestamp=i * 0.033))

        # Start ascending
        for i in range(8, 12):
            depth = 130.0 - (i - 8) * 25  # 130 -> 30 degrees
            counter.update(self.create_angles(i, hip_flexion=depth * 0.8, knee_flexion=depth, timestamp=i * 0.033))

        # Exit rep
        result, feedback = counter.update(self.create_angles(12, hip_flexion=10.0, knee_flexion=10.0, timestamp=0.4))

        assert counter.state == RepState.IDLE
        assert counter.rep_count == 1
        assert result is not None
        assert result.rep_number == 1
        assert result.max_depth_angle > 90.0  # Should track max depth

    def test_three_reps_sequence(self):
        """Simulate 3 complete reps and verify count and depth tracking."""
        config = RepCounterConfig(
            entry_hip_angle=20.0,
            exit_hip_angle=18.0,
            min_rep_duration_frames=10,
            min_depth_knee_angle=80.0,
        )
        counter = RepCounter(config)

        depths = [95.0, 100.0, 88.0]  # Different depths for each rep
        reps_completed = []

        frame = 0
        for rep_idx in range(3):
            target_depth = depths[rep_idx]

            # Descent phase
            for step in range(15):
                hip = min(10.0 + step * 6, target_depth * 0.9)
                knee = min(10.0 + step * 7, target_depth)
                counter.update(self.create_angles(frame, hip_flexion=hip, knee_flexion=knee, timestamp=frame * 0.033))
                frame += 1

            # Ascent phase
            for step in range(15):
                knee = max(target_depth - step * 7, 10.0)
                hip = max(target_depth * 0.9 - step * 6, 10.0)
                result, feedback = counter.update(self.create_angles(frame, hip_flexion=hip, knee_flexion=knee, timestamp=frame * 0.033))
                frame += 1
                if result is not None:
                    reps_completed.append(result)

        assert counter.rep_count == 3
        assert len(reps_completed) == 3

        # Verify depth tracking
        for i, rep_data in enumerate(reps_completed):
            assert rep_data.rep_number == i + 1
            # Max depth should be close to target
            assert abs(rep_data.max_depth_angle - depths[i]) < 15.0

    def test_depth_tracking(self):
        """RepCounter should track maximum depth angle during rep."""
        config = RepCounterConfig(min_rep_duration_frames=5, min_depth_knee_angle=80.0)
        counter = RepCounter(config)

        # Enter rep
        counter.update(self.create_angles(0, hip_flexion=25.0, knee_flexion=40.0))

        # Go to specific depth
        counter.update(self.create_angles(1, hip_flexion=50.0, knee_flexion=60.0))
        counter.update(self.create_angles(2, hip_flexion=70.0, knee_flexion=85.0))  # Max depth
        counter.update(self.create_angles(3, hip_flexion=65.0, knee_flexion=80.0))  # Coming up
        counter.update(self.create_angles(4, hip_flexion=50.0, knee_flexion=60.0))
        counter.update(self.create_angles(5, hip_flexion=25.0, knee_flexion=35.0))

        # Complete rep
        result, feedback = counter.update(self.create_angles(6, hip_flexion=10.0, knee_flexion=15.0))

        assert result is not None
        assert result.max_depth_angle == 85.0


class TestRepTiming:
    """Test rep timing calculations."""

    def create_angles(self, frame: int, hip_flexion: float, timestamp: float) -> JointAngles:
        """Create JointAngles with timing info."""
        return JointAngles(
            hip_flexion_l=hip_flexion,
            hip_flexion_r=hip_flexion,
            knee_flexion_l=hip_flexion * 1.2,
            knee_flexion_r=hip_flexion * 1.2,
            frame_index=frame,
            timestamp=timestamp,
        )

    def test_rep_duration(self):
        """RepData should track total rep duration."""
        config = RepCounterConfig(min_rep_duration_frames=5, min_depth_knee_angle=80.0)
        counter = RepCounter(config)

        # Rep from t=0 to t=2.0 seconds
        counter.update(self.create_angles(0, hip_flexion=25.0, timestamp=0.0))
        counter.update(self.create_angles(1, hip_flexion=50.0, timestamp=0.5))
        counter.update(self.create_angles(2, hip_flexion=70.0, timestamp=1.0))  # Bottom
        counter.update(self.create_angles(3, hip_flexion=50.0, timestamp=1.3))
        counter.update(self.create_angles(4, hip_flexion=25.0, timestamp=1.6))
        result, feedback = counter.update(self.create_angles(5, hip_flexion=10.0, timestamp=2.0))

        assert result is not None
        assert abs(result.duration - 2.0) < 0.1

    def test_descent_ascent_timing(self):
        """RepData should track descent and ascent phases separately."""
        config = RepCounterConfig(min_rep_duration_frames=5, min_depth_knee_angle=80.0)
        counter = RepCounter(config)

        # Descent: 0-1.0s, Ascent: 1.0-2.0s
        counter.update(self.create_angles(0, hip_flexion=25.0, timestamp=0.0))
        counter.update(self.create_angles(1, hip_flexion=50.0, timestamp=0.4))
        counter.update(self.create_angles(2, hip_flexion=80.0, timestamp=1.0))  # Bottom
        counter.update(self.create_angles(3, hip_flexion=50.0, timestamp=1.4))
        counter.update(self.create_angles(4, hip_flexion=25.0, timestamp=1.7))
        result, feedback = counter.update(self.create_angles(5, hip_flexion=10.0, timestamp=2.0))

        assert result is not None
        assert abs(result.descent_time - 1.0) < 0.2
        assert abs(result.ascent_time - 1.0) < 0.2


class TestFaultIntegration:
    """Test fault tracking during reps."""

    def create_angles(self, frame: int, hip_flexion: float) -> JointAngles:
        """Create simple JointAngles."""
        return JointAngles(
            hip_flexion_l=hip_flexion,
            hip_flexion_r=hip_flexion,
            knee_flexion_l=hip_flexion * 1.2,
            knee_flexion_r=hip_flexion * 1.2,
            frame_index=frame,
            timestamp=frame * 0.033,
        )

    def test_add_fault_during_rep(self):
        """Faults added during rep should appear in RepData."""
        config = RepCounterConfig(min_rep_duration_frames=5, min_depth_knee_angle=80.0)
        counter = RepCounter(config)

        # Start rep
        counter.update(self.create_angles(0, hip_flexion=25.0))

        # Add a fault
        fault = FaultEvent(
            fault_type="knee_valgus",
            severity=FaultSeverity.MODERATE,
            severity_score=2.0,
            message="Test fault",
        )
        counter.add_fault(fault)

        # Continue and complete rep
        counter.update(self.create_angles(1, hip_flexion=50.0))
        counter.update(self.create_angles(2, hip_flexion=70.0))
        counter.update(self.create_angles(3, hip_flexion=50.0))
        counter.update(self.create_angles(4, hip_flexion=25.0))
        result, feedback = counter.update(self.create_angles(5, hip_flexion=10.0))

        assert result is not None
        assert len(result.faults) == 1
        assert result.faults[0].fault_type == "knee_valgus"

    def test_faults_passed_to_update(self):
        """Faults passed to update() should appear in RepData."""
        config = RepCounterConfig(min_rep_duration_frames=5, min_depth_knee_angle=80.0)
        counter = RepCounter(config)

        fault1 = FaultEvent(
            fault_type="forward_lean",
            severity=FaultSeverity.MILD,
            severity_score=1.0,
            message="Test fault 1",
        )
        fault2 = FaultEvent(
            fault_type="knee_valgus",
            severity=FaultSeverity.MODERATE,
            severity_score=2.0,
            message="Test fault 2",
        )

        # Start rep and add faults via update
        counter.update(self.create_angles(0, hip_flexion=25.0), faults=[fault1])
        counter.update(self.create_angles(1, hip_flexion=50.0))
        counter.update(self.create_angles(2, hip_flexion=70.0), faults=[fault2])
        counter.update(self.create_angles(3, hip_flexion=50.0))
        counter.update(self.create_angles(4, hip_flexion=25.0))
        result, feedback = counter.update(self.create_angles(5, hip_flexion=10.0))

        assert result is not None
        assert len(result.faults) == 2
        fault_types = {f.fault_type for f in result.faults}
        assert "forward_lean" in fault_types
        assert "knee_valgus" in fault_types


class TestAsymmetryTracking:
    """Test bilateral asymmetry tracking during reps."""

    def create_asymmetric_angles(
        self,
        frame: int,
        hip_l: float,
        hip_r: float,
        knee_l: float,
        knee_r: float,
    ) -> JointAngles:
        """Create JointAngles with asymmetry."""
        return JointAngles(
            hip_flexion_l=hip_l,
            hip_flexion_r=hip_r,
            knee_flexion_l=knee_l,
            knee_flexion_r=knee_r,
            frame_index=frame,
            timestamp=frame * 0.033,
        )

    def test_asymmetry_averaging(self):
        """RepData should track average asymmetry during rep."""
        config = RepCounterConfig(min_rep_duration_frames=5, min_depth_knee_angle=70.0)
        counter = RepCounter(config)

        # Rep with consistent 10° knee asymmetry
        counter.update(self.create_asymmetric_angles(0, 25, 25, 45, 35))  # 10° diff
        counter.update(self.create_asymmetric_angles(1, 50, 50, 75, 65))  # 10° diff
        counter.update(self.create_asymmetric_angles(2, 60, 60, 85, 75))  # 10° diff
        counter.update(self.create_asymmetric_angles(3, 50, 50, 65, 55))
        counter.update(self.create_asymmetric_angles(4, 25, 25, 45, 35))
        result, feedback = counter.update(self.create_asymmetric_angles(5, 10, 10, 15, 15))

        assert result is not None
        assert result.avg_knee_asymmetry > 5.0  # Should show asymmetry


class TestDerivativeIntegration:
    """Test derivative-based state machine."""

    def create_angles(self, frame: int, hip_flexion: float, knee_flexion: float, timestamp: float) -> JointAngles:
        """Create JointAngles."""
        return JointAngles(
            hip_flexion_l=hip_flexion,
            hip_flexion_r=hip_flexion,
            knee_flexion_l=knee_flexion,
            knee_flexion_r=knee_flexion,
            frame_index=frame,
            timestamp=timestamp,
        )

    def test_phase_property(self):
        """RepCounter should expose current phase."""
        counter = RepCounter()
        assert counter.phase == "idle"

        # Enter rep
        counter.update(self.create_angles(0, 25.0, 40.0, 0.0))
        assert counter.phase in ["descending", "bottom", "ascending"]

    def test_go_deeper_feedback(self):
        """Should return 'go_deeper' feedback when depth not reached."""
        config = RepCounterConfig(
            entry_hip_angle=20.0,
            exit_hip_angle=18.0,
            min_rep_duration_frames=5,
            min_depth_knee_angle=100.0,  # High threshold
        )
        counter = RepCounter(config)

        # Do a shallow rep that doesn't hit depth
        counter.update(self.create_angles(0, 25.0, 40.0, 0.0))
        counter.update(self.create_angles(1, 40.0, 60.0, 0.1))
        counter.update(self.create_angles(2, 50.0, 70.0, 0.2))  # Max depth = 70°, below 100°
        counter.update(self.create_angles(3, 40.0, 60.0, 0.3))
        counter.update(self.create_angles(4, 25.0, 40.0, 0.4))
        result, feedback = counter.update(self.create_angles(5, 10.0, 15.0, 0.5))

        # Rep should not count, feedback should be "go_deeper"
        assert result is None
        assert feedback == "go_deeper"
        assert counter.rep_count == 0

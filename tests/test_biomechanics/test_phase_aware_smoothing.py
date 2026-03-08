"""Tests for phase-aware smoothing in JointAngleFilter."""

import pytest

from biomechanics.utils.filters import JointAngleFilter
from biomechanics.utils.types import JointAngles


class TestPhaseAwareSmoothing:

    def test_idle_sets_heavy_smoothing(self):
        """Idle phase should set heavy smoothing parameters."""
        filt = JointAngleFilter()
        filt.update_phase("idle")

        assert filt.min_cutoff == pytest.approx(0.3)
        assert filt.beta == pytest.approx(0.003)

    def test_descending_sets_standard(self):
        """Descending phase should set standard smoothing parameters."""
        filt = JointAngleFilter()
        # First set to idle so we can verify a change happens
        filt.update_phase("idle")
        filt.update_phase("descending")

        assert filt.min_cutoff == pytest.approx(1.0)
        assert filt.beta == pytest.approx(0.007)

    def test_unknown_phase_uses_default(self):
        """Unknown phase string should fall back to DEFAULT_PARAMS."""
        filt = JointAngleFilter()
        # First set to idle so defaults would be a change
        filt.update_phase("idle")
        filt.update_phase("unknown_phase")

        assert filt.min_cutoff == pytest.approx(1.0)
        assert filt.beta == pytest.approx(0.007)

    def test_existing_filters_updated(self):
        """Underlying OneEuroFilter instances should be updated on phase change."""
        filt = JointAngleFilter()

        # Filter some angles to create underlying filter instances
        angles = JointAngles(
            knee_flexion_l=45.0, knee_flexion_r=44.0,
            hip_flexion_l=30.0, timestamp=1.0, frame_index=0,
        )
        filt.filter_angles(angles, timestamp=1.0)

        # Verify filters were created
        assert len(filt._filters) > 0

        # Now change phase to idle
        filt.update_phase("idle")

        # Check that each underlying OneEuroFilter was updated
        for name, one_euro in filt._filters.items():
            assert one_euro.min_cutoff == pytest.approx(0.3), f"Filter {name} min_cutoff not updated"
            assert one_euro.beta == pytest.approx(0.003), f"Filter {name} beta not updated"

    def test_no_update_when_same_phase(self):
        """Calling update_phase twice with same phase should not error."""
        filt = JointAngleFilter()
        filt.update_phase("idle")
        filt.update_phase("idle")  # Second call — no change needed

        assert filt.min_cutoff == pytest.approx(0.3)
        assert filt.beta == pytest.approx(0.003)

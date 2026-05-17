"""Tests for the Gaussian temporal taper function."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.optimizer.temporal import gaussian_taper


class TestGaussianTaper:
    def test_peak_at_bottom_frame(self):
        taper = gaussian_taper(60, bottom_frame=30)
        assert taper[30] == pytest.approx(1.0)

    def test_peak_at_first_frame(self):
        taper = gaussian_taper(60, bottom_frame=0)
        assert taper[0] == pytest.approx(1.0)

    def test_peak_at_last_frame(self):
        taper = gaussian_taper(60, bottom_frame=59)
        assert taper[59] == pytest.approx(1.0)

    def test_decays_away_from_peak(self):
        taper = gaussian_taper(60, bottom_frame=30)
        assert taper[30] > taper[20]
        assert taper[30] > taper[40]

    def test_edges_near_zero(self):
        taper = gaussian_taper(60, bottom_frame=30)
        assert taper[0] < 0.05
        assert taper[59] < 0.05

    def test_symmetric_around_center(self):
        taper = gaussian_taper(61, bottom_frame=30)
        np.testing.assert_allclose(taper[30 - 5], taper[30 + 5], atol=1e-12)
        np.testing.assert_allclose(taper[30 - 10], taper[30 + 10], atol=1e-12)

    def test_values_in_zero_one(self):
        taper = gaussian_taper(100, bottom_frame=50)
        assert np.all(taper >= 0.0)
        assert np.all(taper <= 1.0)

    def test_output_shape(self):
        taper = gaussian_taper(120, bottom_frame=60)
        assert taper.shape == (120,)

    def test_custom_sigma_narrow(self):
        wide = gaussian_taper(60, bottom_frame=30, sigma_frames=20.0)
        narrow = gaussian_taper(60, bottom_frame=30, sigma_frames=5.0)
        # Narrow sigma → faster decay → smaller values far from peak
        assert narrow[15] < wide[15]

    def test_custom_sigma_wide(self):
        wide = gaussian_taper(60, bottom_frame=30, sigma_frames=100.0)
        # Very wide sigma → nearly flat
        assert wide[0] > 0.9

    def test_monotonic_descent_from_peak(self):
        taper = gaussian_taper(60, bottom_frame=30)
        # Left side: should be monotonically increasing toward peak
        for i in range(1, 31):
            assert taper[i] >= taper[i - 1]
        # Right side: should be monotonically decreasing from peak
        for i in range(31, 60):
            assert taper[i] <= taper[i - 1]

    def test_default_sigma(self):
        """Default sigma = n_frames / 6 gives sensible decay."""
        taper = gaussian_taper(60, bottom_frame=30)
        # At sigma distance (10 frames), value should be exp(-0.5) ≈ 0.607
        sigma = 60 / 6.0
        idx = int(30 + sigma)
        assert taper[idx] == pytest.approx(np.exp(-0.5), abs=0.01)

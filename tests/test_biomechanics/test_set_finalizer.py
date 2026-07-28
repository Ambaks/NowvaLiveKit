"""
Tests for set finalization output structure: workout/set_<n>/rep_<n> hierarchy.
"""

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from biomechanics.analysis.set_finalizer import SetDataCollector, finalize_set


FPS = 30.0
REP_CENTERS_S = [3.0, 7.0, 11.0]
DURATION_S = 14.0

SET_FILES = [
    "hip_position.png",
    "hip_velocity.png",
    "joint_angles.png",
    "pipeline_angles.png",
    "hip_adduction.png",
    "knee_valgus.png",
    "bilateral_asymmetry.png",
    "segmentation.png",
    "data.json",
    "plot_data.json",
    "report.md",
    "dashboard.html",
]

REP_FILES = [
    "hip_position.png",
    "hip_velocity.png",
    "joint_angles.png",
    "pipeline_angles.png",
    "hip_adduction.png",
    "knee_valgus.png",
    "bilateral_asymmetry.png",
    "metrics.json",
    "data.json",
]


def _synthetic_collector() -> SetDataCollector:
    """Collector holding a clean 3-rep squat: standing at -0.9 m hip-to-ankle,
    smooth bumps to -0.5 m at each rep center."""
    collector = SetDataCollector()
    collector.thresholds = {
        "knee_valgus": {"mild": 10.0, "moderate": 15.0, "severe": 20.0},
    }

    n_samples = int(DURATION_S * FPS)
    for i in range(n_samples):
        t = i / FPS
        bump = sum(
            math.exp(-((t - c) ** 2) / (2 * 0.5**2)) for c in REP_CENTERS_S
        )
        depth_factor = min(1.0, bump)

        collector.timestamps.append(t)
        collector.hip_mid_y.append(-0.9 + 0.4 * depth_factor)
        collector.knee_angles.append(175.0 - 85.0 * depth_factor)
        collector.hip_angles.append(170.0 - 80.0 * depth_factor)
        collector.trunk_angles.append(5.0 + 30.0 * depth_factor)
        collector.pipeline_knee.append(175.0 - 85.0 * depth_factor)
        collector.pipeline_hip.append(170.0 - 80.0 * depth_factor)
        collector.pipeline_trunk.append(5.0 + 30.0 * depth_factor)
        collector.hip_adduction_l.append(3.0 * depth_factor)
        collector.hip_adduction_r.append(2.5 * depth_factor)
        collector.knee_valgus_l.append(4.0 * depth_factor)
        collector.knee_valgus_r.append(3.5 * depth_factor)
        collector.knee_ankle_sep_ratio.append(1.0)
        collector.bilateral_asymmetry.append(1.5 * depth_factor)
        collector.frames_data.append({"timestamp": t, "frame_index": i})

    for rep_num, center in enumerate(REP_CENTERS_S, start=1):
        collector.rep_events.append((center + 1.0, rep_num))

    return collector


class TestFinalizeSetStructure:
    @pytest.fixture(scope="class")
    def finalized(self, tmp_path_factory):
        workout_dir = tmp_path_factory.mktemp("workout")
        collector = _synthetic_collector()
        plot_export = finalize_set(collector, 2, str(workout_dir))
        return workout_dir, plot_export

    def test_returns_plot_export(self, finalized):
        _, plot_export = finalized
        assert plot_export is not None
        assert plot_export["set_number"] == 2

    def test_set_folder_contains_all_outputs(self, finalized):
        workout_dir, _ = finalized
        set_dir = workout_dir / "set_2"
        assert set_dir.is_dir()
        for name in SET_FILES:
            assert (set_dir / name).is_file(), f"missing {name}"

    def test_rep_folders_contain_all_outputs(self, finalized):
        workout_dir, _ = finalized
        set_dir = workout_dir / "set_2"
        rep_dirs = sorted(p.name for p in set_dir.glob("rep_*"))
        assert rep_dirs == ["rep_1", "rep_2", "rep_3"]
        for rep_dir_name in rep_dirs:
            for name in REP_FILES:
                assert (set_dir / rep_dir_name / name).is_file(), (
                    f"missing {rep_dir_name}/{name}"
                )

    def test_rep_metrics_match_segmentation(self, finalized):
        workout_dir, _ = finalized
        rep_dir = workout_dir / "set_2" / "rep_2"

        with open(rep_dir / "metrics.json") as f:
            metrics = json.load(f)
        assert metrics["rep_number"] == 2
        assert metrics["depth_cm"] == pytest.approx(40.0, abs=10.0)
        assert "fault_events" in metrics

        with open(rep_dir / "data.json") as f:
            rep_data = json.load(f)
        assert rep_data["rep_number"] == 2
        expected_frames = metrics["end_idx"] - metrics["start_idx"] + 1
        assert len(rep_data["frames"]) == expected_frames

    def test_collector_reset_after_finalize(self, finalized):
        collector = _synthetic_collector()
        finalize_set(collector, 1, str(finalized[0]))
        assert len(collector.timestamps) == 0
        assert collector.thresholds is not None

    def test_not_enough_data_returns_none(self, tmp_path):
        collector = SetDataCollector()
        collector.timestamps = [0.0, 0.1]
        assert finalize_set(collector, 1, str(tmp_path)) is None
        assert not (tmp_path / "set_1").exists()

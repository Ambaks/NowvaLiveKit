"""Recompute set plots from raw set_data.json using current smoothing settings.

Usage:
    python recompute_set.py output/set_20260310_211631
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import numpy as np

from biomechanics.analysis.set_finalizer import (
    smooth_1d,
    save_set_plots,
    save_pipeline_angles_plot,
    save_hip_adduction_plot,
    save_bilateral_asymmetry_plot,
)
from biomechanics.analysis.rep_segmenter import segment_set, plot_segmentation, write_set_report
from biomechanics.viz.html_dashboard import generate_set_dashboard
from biomechanics.utils.geometry import joint_angle_3_points, calculate_trunk_angle


_VERTICAL_Y_DOWN = np.array([0.0, -1.0, 0.0])


def recompute(out_dir: str):
    out_dir = Path(out_dir)

    # Find all set data files
    data_files = sorted(p for p in out_dir.glob("set*_data.json") if "_plot_data" not in p.name)
    if not data_files:
        print(f"No set*_data.json files found in {out_dir}")
        return

    for data_path in data_files:
        set_num = int(data_path.stem.replace("set", "").replace("_data", ""))
        print(f"\n{'='*50}")
        print(f"  Recomputing Set {set_num} from {data_path.name}")
        print(f"{'='*50}")

        with open(data_path) as f:
            raw = json.load(f)

        frames = raw["frames"]
        rep_events = [(r["timestamp"], r["rep_number"]) for r in raw["rep_events"]]

        if len(frames) <= 10:
            print(f"  Not enough frames ({len(frames)}), skipping")
            continue

        # Reconstruct time series from raw 3D keypoints
        timestamps_list = []
        hip_mid_y_list = []
        knee_angles_list = []
        hip_angles_list = []
        trunk_angles_list = []

        for fr in frames:
            timestamps_list.append(fr["timestamp"])

            hip_l, hip_r = fr["hip_l"], fr["hip_r"]
            knee_l, knee_r = fr["knee_l"], fr["knee_r"]
            ankle_l, ankle_r = fr["ankle_l"], fr["ankle_r"]
            shoulder_l, shoulder_r = fr["shoulder_l"], fr["shoulder_r"]

            hip_mid_y = (hip_l["y"] + hip_r["y"]) / 2.0
            ankle_mid_y = (ankle_l["y"] + ankle_r["y"]) / 2.0
            hip_mid_y_list.append(hip_mid_y - ankle_mid_y)

            shoulder_mid = np.array([(shoulder_l["x"] + shoulder_r["x"]) / 2,
                                     (shoulder_l["y"] + shoulder_r["y"]) / 2,
                                     (shoulder_l["z"] + shoulder_r["z"]) / 2])
            hip_mid = np.array([(hip_l["x"] + hip_r["x"]) / 2,
                                (hip_l["y"] + hip_r["y"]) / 2,
                                (hip_l["z"] + hip_r["z"]) / 2])
            knee_mid = np.array([(knee_l["x"] + knee_r["x"]) / 2,
                                 (knee_l["y"] + knee_r["y"]) / 2,
                                 (knee_l["z"] + knee_r["z"]) / 2])
            ankle_mid = np.array([(ankle_l["x"] + ankle_r["x"]) / 2,
                                  (ankle_l["y"] + ankle_r["y"]) / 2,
                                  (ankle_l["z"] + ankle_r["z"]) / 2])

            knee_angles_list.append(joint_angle_3_points(hip_mid, knee_mid, ankle_mid))
            hip_angles_list.append(joint_angle_3_points(shoulder_mid, hip_mid, knee_mid))
            trunk_angles_list.append(calculate_trunk_angle(shoulder_mid, hip_mid, vertical=_VERTICAL_Y_DOWN))

        timestamps = np.array(timestamps_list)
        t_rel = timestamps - timestamps[0]
        sma_start = int(np.searchsorted(t_rel, 1.5))

        # Smooth with current settings (sma_window=2 for position, 3 for velocity)
        hip_mid = smooth_1d(np.array(hip_mid_y_list), sma_window=2, sma_start=sma_start)
        raw_vel = np.gradient(hip_mid, timestamps)
        vel_mid = smooth_1d(raw_vel, median_window=1, sma_window=3, sma_start=sma_start)

        knee_ang = smooth_1d(np.array(knee_angles_list), sma_window=3, sma_start=sma_start)
        hip_ang = smooth_1d(np.array(hip_angles_list), sma_window=3, sma_start=sma_start)
        trunk_ang = smooth_1d(np.array(trunk_angles_list), sma_window=3, sma_start=sma_start)

        # Generate 3D geometry plots
        save_set_plots(set_num, timestamps, hip_mid, vel_mid,
                       knee_ang, hip_ang, trunk_ang, rep_events, str(out_dir))

        # Load existing plot_data for pipeline angles (can't recompute IK from raw keypoints)
        plot_data_path = out_dir / f"set{set_num}_plot_data.json"
        pipe_knee = pipe_hip = pipe_trunk = None
        adduction_l = adduction_r = bilat_asym = None

        if plot_data_path.exists():
            with open(plot_data_path) as f:
                old_plot = json.load(f)

            # Pipeline angles are already smoothed — re-smooth from the old values
            # (These come from IK solver, not recomputable from raw keypoints alone)
            if old_plot.get("pipeline_knee_flexion_deg"):
                pipe_knee = np.array(old_plot["pipeline_knee_flexion_deg"])
                pipe_hip = np.array(old_plot["pipeline_hip_flexion_deg"])
                pipe_trunk = np.array(old_plot["pipeline_trunk_flexion_deg"])

                save_pipeline_angles_plot(set_num, t_rel, pipe_knee, pipe_hip, pipe_trunk,
                                          rep_events, timestamps, str(out_dir))

            if old_plot.get("hip_adduction_l_deg"):
                adduction_l = np.array(old_plot["hip_adduction_l_deg"])
                adduction_r = np.array(old_plot["hip_adduction_r_deg"])
                save_hip_adduction_plot(set_num, t_rel, adduction_l, adduction_r,
                                        rep_events, timestamps, str(out_dir))

            if old_plot.get("bilateral_asymmetry_deg"):
                bilat_asym = np.array(old_plot["bilateral_asymmetry_deg"])
                save_bilateral_asymmetry_plot(set_num, t_rel, bilat_asym,
                                              rep_events, timestamps, str(out_dir))

        # Save updated plot data
        plot_export = {
            "set_number": set_num,
            "rep_events": [{"timestamp": t, "rep_number": r} for t, r in rep_events],
            "timestamps": t_rel.tolist(),
            "hip_position_cm": (hip_mid * 100.0).tolist(),
            "hip_velocity_cm_s": (vel_mid * 100.0).tolist(),
            "knee_angle_deg": knee_ang.tolist(),
            "hip_angle_deg": hip_ang.tolist(),
            "trunk_angle_deg": trunk_ang.tolist(),
            "pipeline_knee_flexion_deg": pipe_knee.tolist() if pipe_knee is not None else [],
            "pipeline_hip_flexion_deg": pipe_hip.tolist() if pipe_hip is not None else [],
            "pipeline_trunk_flexion_deg": pipe_trunk.tolist() if pipe_trunk is not None else [],
            "hip_adduction_l_deg": adduction_l.tolist() if adduction_l is not None else [],
            "hip_adduction_r_deg": adduction_r.tolist() if adduction_r is not None else [],
            "bilateral_asymmetry_deg": bilat_asym.tolist() if bilat_asym is not None else [],
        }
        plot_path = str(out_dir / f"set{set_num}_plot_data.json")
        with open(plot_path, "w") as f:
            json.dump(plot_export, f, indent=2)
        print(f"  Saved: {plot_path}")

        # Segmentation + report
        seg_result = segment_set(plot_export)
        plot_segmentation(plot_export, seg_result,
                          save_path=out_dir / f"set{set_num}_segmentation.png")
        write_set_report(seg_result, set_number=set_num,
                         save_path=out_dir / f"set{set_num}_report.md")

        # Dashboard
        generate_set_dashboard(plot_export, seg_result, str(out_dir), set_num)

    print(f"\nDone — all outputs in: {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python recompute_set.py <output_dir>")
        sys.exit(1)
    recompute(sys.argv[1])

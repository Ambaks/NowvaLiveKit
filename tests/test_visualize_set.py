#!/usr/bin/env python3
"""
Post-Set Visualization Tool

Runs the biomechanics pipeline on webcam, collects per-frame data during a set,
then plots:
  1. Hip joint flexion angle (position) over time
  2. Hip joint angular velocity over time
  3. Interactive 3D skeleton movement (all landmarks)

Usage:
    python tests/test_visualize_set.py

Controls:
    Press 'q' to stop recording and view the plots.
    Close each plot window to see the next one.
    The 3D plot is interactive — click and drag to rotate.
"""

import sys
import os
import time

import cv2
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (registers 3d projection)

# Add src to path so we can import biomechanics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from biomechanics.pipeline import BiomechanicsPipeline
from biomechanics.utils.types import CocoKeypoints as CK
from biomechanics.viz.set_plots import plot_hip_position, plot_hip_velocity, make_output_dir

# COCO skeleton connections for drawing bones
SKELETON_CONNECTIONS = [
    (CK.LEFT_SHOULDER, CK.RIGHT_SHOULDER),
    (CK.LEFT_SHOULDER, CK.LEFT_ELBOW),
    (CK.LEFT_ELBOW, CK.LEFT_WRIST),
    (CK.RIGHT_SHOULDER, CK.RIGHT_ELBOW),
    (CK.RIGHT_ELBOW, CK.RIGHT_WRIST),
    (CK.LEFT_SHOULDER, CK.LEFT_HIP),
    (CK.RIGHT_SHOULDER, CK.RIGHT_HIP),
    (CK.LEFT_HIP, CK.RIGHT_HIP),
    (CK.LEFT_HIP, CK.LEFT_KNEE),
    (CK.LEFT_KNEE, CK.LEFT_ANKLE),
    (CK.RIGHT_HIP, CK.RIGHT_KNEE),
    (CK.RIGHT_KNEE, CK.RIGHT_ANKLE),
]

KEYPOINT_NAMES = [
    "nose", "L eye", "R eye", "L ear", "R ear",
    "L shoulder", "R shoulder", "L elbow", "R elbow",
    "L wrist", "R wrist", "L hip", "R hip",
    "L knee", "R knee", "L ankle", "R ankle",
]


def collect_set_data():
    """Run the pipeline and collect per-frame data until user presses 'q'."""
    print("Initializing pipeline...")
    pipeline = BiomechanicsPipeline()
    print("Pipeline ready. Recording... Press 'q' to stop.\n")

    # Storage
    timestamps = []
    hip_flexion_l = []
    hip_flexion_r = []
    hip_velocity_l = []
    hip_velocity_r = []
    skeletons_3d = []  # list of (17, 3) arrays
    rep_events = []  # (timestamp, rep_number) for marking on plots

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            pf = pipeline.process_frame()
            frame_count += 1

            # Show live camera feed
            if pipeline.last_frame is not None:
                display = pipeline.last_frame.copy()
                elapsed = time.time() - start_time
                cv2.putText(
                    display,
                    f"Recording: {elapsed:.1f}s | Frames: {frame_count} | Press 'q' to stop",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
                if pf.joint_angles:
                    cv2.putText(
                        display,
                        f"Hip L: {pf.joint_angles.hip_flexion_l:.1f} R: {pf.joint_angles.hip_flexion_r:.1f}",
                        (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255, 255, 0),
                        2,
                    )
                cv2.imshow("Set Recording", display)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            # Only store frames where we got valid data
            if pf.joint_angles is None or pf.skeleton_3d is None:
                continue

            t = pf.timestamp
            timestamps.append(t)

            # Hip angles
            hip_flexion_l.append(pf.joint_angles.hip_flexion_l)
            hip_flexion_r.append(pf.joint_angles.hip_flexion_r)

            # Hip velocity from derivative tracker (computed inside pipeline)
            # We can approximate from angle deltas if needed, but the pipeline
            # computes them internally. We'll compute from our collected angles.
            if len(timestamps) >= 2:
                dt = timestamps[-1] - timestamps[-2]
                if dt > 0:
                    hip_velocity_l.append(
                        (hip_flexion_l[-1] - hip_flexion_l[-2]) / dt
                    )
                    hip_velocity_r.append(
                        (hip_flexion_r[-1] - hip_flexion_r[-2]) / dt
                    )
                else:
                    hip_velocity_l.append(0.0)
                    hip_velocity_r.append(0.0)
            else:
                hip_velocity_l.append(0.0)
                hip_velocity_r.append(0.0)

            # 3D skeleton
            kpts = pf.skeleton_3d.to_numpy()  # (17, 3)
            skeletons_3d.append(kpts)

            # Track rep completions for plot markers
            if pf.rep_data is not None:
                rep_events.append((t, pf.rep_data.rep_number))

    finally:
        cv2.destroyAllWindows()
        pipeline.release()

    print(f"\nRecording complete: {len(timestamps)} valid frames over {frame_count} total")
    print(f"Reps detected: {len(rep_events)}")

    return {
        "timestamps": np.array(timestamps),
        "hip_flexion_l": np.array(hip_flexion_l),
        "hip_flexion_r": np.array(hip_flexion_r),
        "hip_velocity_l": np.array(hip_velocity_l),
        "hip_velocity_r": np.array(hip_velocity_r),
        "skeletons_3d": np.array(skeletons_3d),  # (N, 17, 3)
        "rep_events": rep_events,
    }


def plot_3d_movement(data: dict, out_dir: str):
    """
    Interactive 3D plot of landmark movement over the set.

    - Each keypoint's trajectory is drawn as a colored line
    - First and last skeleton poses are drawn as connected stick figures
    - Click and drag to rotate the view
    """
    skeletons = data["skeletons_3d"]  # (N, 17, 3)
    n_frames = len(skeletons)

    if n_frames == 0:
        print("No 3D data to plot.")
        return

    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection="3d")

    # Color map for time progression
    cmap = plt.cm.viridis
    time_colors = cmap(np.linspace(0, 1, n_frames))

    # Subsample for trajectory lines to avoid overplotting
    step = max(1, n_frames // 200)

    # Draw trajectories for key joints
    tracked_joints = [
        (CK.LEFT_HIP, "L Hip", "#2196F3"),
        (CK.RIGHT_HIP, "R Hip", "#F44336"),
        (CK.LEFT_KNEE, "L Knee", "#4CAF50"),
        (CK.RIGHT_KNEE, "R Knee", "#FF9800"),
        (CK.LEFT_ANKLE, "L Ankle", "#9C27B0"),
        (CK.RIGHT_ANKLE, "R Ankle", "#E91E63"),
        (CK.LEFT_SHOULDER, "L Shoulder", "#00BCD4"),
        (CK.RIGHT_SHOULDER, "R Shoulder", "#FF5722"),
    ]

    for joint_idx, name, color in tracked_joints:
        traj = skeletons[::step, joint_idx, :]  # (M, 3)
        ax.plot(
            traj[:, 0], traj[:, 2], traj[:, 1],  # swap Y/Z for natural viewing
            label=name,
            color=color,
            linewidth=1.0,
            alpha=0.7,
        )

    # Draw stick figure at start (blue) and end (red) of set
    def draw_skeleton(skeleton, color, alpha, label_prefix):
        for i, j in SKELETON_CONNECTIONS:
            xs = [skeleton[i, 0], skeleton[j, 0]]
            ys = [skeleton[i, 2], skeleton[j, 2]]  # Z -> depth
            zs = [skeleton[i, 1], skeleton[j, 1]]  # Y -> vertical
            ax.plot(xs, ys, zs, color=color, linewidth=2.5, alpha=alpha)
        # Draw joints as dots
        ax.scatter(
            skeleton[:, 0],
            skeleton[:, 2],
            skeleton[:, 1],
            c=color,
            s=30,
            alpha=alpha,
            label=label_prefix,
        )

    draw_skeleton(skeletons[0], "blue", 0.9, "Start pose")
    draw_skeleton(skeletons[-1], "red", 0.9, "End pose")

    # If we have enough frames, also draw the bottom-of-squat pose
    # (frame with max average hip flexion)
    avg_hip_flex = (data["hip_flexion_l"] + data["hip_flexion_r"]) / 2
    bottom_idx = np.argmax(avg_hip_flex)
    if bottom_idx not in (0, n_frames - 1):
        draw_skeleton(skeletons[bottom_idx], "orange", 0.7, "Deepest pose")

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z - Depth (m)")
    ax.set_zlabel("Y - Height (m)")
    ax.set_title("3D Landmark Movement During Set\n(drag to rotate)")
    ax.legend(loc="upper left", fontsize=7, ncol=2)

    # Set equal aspect ratio
    all_pts = skeletons.reshape(-1, 3)
    ranges = np.ptp(all_pts, axis=0)
    max_range = ranges.max() / 2
    mid = np.mean(all_pts, axis=0)
    ax.set_xlim(mid[0] - max_range, mid[0] + max_range)
    ax.set_ylim(mid[2] - max_range, mid[2] + max_range)
    ax.set_zlim(mid[1] - max_range, mid[1] + max_range)

    plt.tight_layout()
    path = os.path.join(out_dir, "3d_movement.png")
    fig.savefig(path, dpi=150)
    print(f"  Saved: {path}")
    plt.show()


def main():
    data = collect_set_data()

    if len(data["timestamps"]) < 10:
        print("Not enough data collected (need at least 10 valid frames).")
        return

    out_dir = make_output_dir()
    print(f"\nPlots will be saved to: {out_dir}\n")

    print("Plotting hip position...")
    plot_hip_position(data, out_dir)

    print("Plotting hip velocity...")
    plot_hip_velocity(data, out_dir)

    print("Plotting 3D movement (interactive — drag to rotate)...")
    plot_3d_movement(data, out_dir)

    print(f"\nDone. All plots saved in: {out_dir}")


if __name__ == "__main__":
    main()

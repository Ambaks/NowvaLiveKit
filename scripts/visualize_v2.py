#!/usr/bin/env python3
"""Biomechanics V2 Squat Visualizer — MuJoCo Physics Pipeline

Captures or processes squat video through the V2 MuJoCo pipeline, then
launches an interactive 3D viewer for trajectory playback and what-if
perturbation exploration. Uses MuJoCo offscreen renderer + OpenCV display.

Usage:
    PYTHONPATH=src python scripts/visualize_v2.py [options]

Examples:
    # Webcam capture (default)
    PYTHONPATH=src python scripts/visualize_v2.py --height 188.5 --weight 85

    # Process existing video
    PYTHONPATH=src python scripts/visualize_v2.py --source path/to/squat.mp4

    # Synthetic trajectory (no camera or video needed)
    PYTHONPATH=src python scripts/visualize_v2.py --synthetic --height 188.5

Options:
    --height HEIGHT_CM    Athlete height in cm (default: 175)
    --weight WEIGHT_KG    Athlete weight in kg (default: 75)
    --source SOURCE       Video source: 0 (webcam), or path to video file
    --reps N              Number of reps to capture (default: 5)
    --no-preview          Disable live camera preview
    --synthetic           Use synthetic trajectory (no capture needed)
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np

from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.solver.mujoco_whatif import MujocoWhatIfSolver
from biomechanics_v2.visualizer.mujoco_viewer import (
    SquatViewer,
    generate_synthetic_trajectory,
)


def main():
    parser = argparse.ArgumentParser(
        description="V2 Squat Visualizer (MuJoCo)"
    )
    parser.add_argument(
        "--height", type=float, default=175.0, help="Height in cm"
    )
    parser.add_argument(
        "--weight", type=float, default=75.0, help="Weight in kg"
    )
    parser.add_argument(
        "--source",
        default="0",
        help="Video source (0 for webcam, or file path)",
    )
    parser.add_argument(
        "--reps", type=int, default=5, help="Target number of reps"
    )
    parser.add_argument(
        "--no-preview", action="store_true", help="Disable camera preview"
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic trajectory (skip capture)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Output Three.js HTML viewer instead of MuJoCo viewer",
    )
    parser.add_argument(
        "--html-output",
        default=None,
        help="Path for HTML output (default: recordings/v2_squat_TIMESTAMP.html)",
    )
    parser.add_argument(
        "--refit",
        default=None,
        nargs="?",
        const="latest",
        metavar="HTML",
        help="Re-run V2 IK on keypoints from a V1 HTML recording (default: latest)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    height_m = args.height / 100.0
    weight_kg = args.weight

    if args.refit is not None:
        _run_refit(height_m, weight_kg, args.refit, args.html_output)
    elif args.synthetic:
        _run_synthetic(height_m, weight_kg, args.html, args.html_output)
    else:
        _run_capture(height_m, weight_kg, args.source, args.reps,
                     args.no_preview, args.html, args.html_output)


def _run_refit(
    height_m: float,
    weight_kg: float,
    html_source: str,
    html_output: str | None = None,
) -> None:
    """Re-run V2 MuJoCo IK on keypoints pulled from a V1 HTML recording."""
    import webbrowser
    from datetime import datetime
    from biomechanics_v2.solver.mujoco_ik import MujocoIKSolver
    from biomechanics_v2.solver.angle_extract import q_to_joint_angles
    from biomechanics_v2.visualizer.html_bridge import (
        v2_frame_to_v1_frame_data,
        _build_skeleton_def,
    )

    recordings_dir = Path(__file__).parent.parent / "recordings"

    if html_source == "latest":
        html_path = _find_latest_v1_html(recordings_dir)
        if html_path is None:
            print("Error: no V1 HTML recordings found in recordings/")
            sys.exit(1)
    else:
        html_path = Path(html_source)
        if not html_path.exists():
            print(f"Error: HTML file not found: {html_path}")
            sys.exit(1)

    print(f"Refitting from: {html_path}")
    data = _extract_data_from_html(html_path)
    v1_reps = data["reps"]
    fps = data.get("fps", 30.0)

    skeleton = MujocoSkeleton(height_m=height_m, weight_kg=weight_kg)
    ik_solver = MujocoIKSolver(skeleton)

    replay_reps_data = []
    q_trajectory_per_rep = []
    rep_boundaries = []

    for rep_idx, rep_frames in enumerate(v1_reps):
        valid_frames = [f for f in rep_frames if f is not None and f.get("kpts")]
        if not valid_frames:
            continue

        num_frames = len(valid_frames)
        landmarks = _vis_kpts_to_ik_landmarks(valid_frames, skeleton)

        print(f"  Rep {rep_idx + 1}: fitting {num_frames} frames through V2 IK...")
        q_trajectory = ik_solver.fit_trajectory(landmarks, smooth_sigma=1.5)
        q_trajectory_per_rep.append(q_trajectory)

        refit_frames = []
        for frame_idx in range(num_frames):
            angles = q_to_joint_angles(
                skeleton, q_trajectory[frame_idx],
                timestamp=frame_idx / fps,
                frame_index=frame_idx,
            )
            frame_dict = v2_frame_to_v1_frame_data(
                skeleton, q_trajectory[frame_idx], angles, frame_idx,
            )
            refit_frames.append(frame_dict)

        from visualize_video_squats import ground_and_center, add_phase_to_rep
        ground_and_center(refit_frames)
        add_phase_to_rep(refit_frames)
        replay_reps_data.append(refit_frames)

        knee_idx = skeleton.get_joint_index("L_knee", "rx")
        bottom_offset = int(np.argmax(q_trajectory[:, knee_idx]))
        rep_boundaries.append([0, num_frames - 1, bottom_offset])

    if not replay_reps_data:
        print("No valid reps found in HTML. Exiting.")
        sys.exit(1)

    from visualize_video_squats import build_html, compute_baseline

    baseline = compute_baseline(replay_reps_data[0])
    skeleton_def = _build_skeleton_def(skeleton)
    kinodynamics_state = {
        "skeleton_def": skeleton_def,
        "reps": [{"q_trajectory": qt.tolist()} for qt in q_trajectory_per_rep],
        "rep_boundaries": rep_boundaries,
    }

    html_content = build_html(
        baseline, replay_reps_data, fps,
        athlete_params=None,
        kinodynamics_state=kinodynamics_state,
    )

    recordings_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(html_output) if html_output else recordings_dir / f"v2_refit_{timestamp}.html"
    output_path.write_text(html_content)
    print(f"HTML viewer saved: {output_path}")
    webbrowser.open(f"file://{output_path.resolve()}")


def _find_latest_v1_html(recordings_dir: Path) -> Path | None:
    """Return the most recent squat_*.html (V1 format) in recordings/."""
    htmls = sorted(
        recordings_dir.glob("squat_*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return htmls[0] if htmls else None


def _extract_data_from_html(html_path: Path) -> dict:
    """Extract the embedded DATA JSON from an existing HTML file."""
    text = html_path.read_text()
    match = re.search(r'const DATA = ({.*?});\s*\n', text, re.DOTALL)
    if not match:
        print("Error: could not find embedded DATA in HTML file.")
        sys.exit(1)
    return json.loads(match.group(1))


def _vis_kpts_to_ik_landmarks(
    frames: list[dict],
    skeleton: MujocoSkeleton,
) -> np.ndarray:
    """Convert V1 vis-space keypoints to (T, 17, 4) IK landmarks in MuJoCo Z-up space.

    V1 vis-space: X=lateral, Y=up, Z=forward
    MuJoCo:       X=lateral, Y=forward, Z=up
    So: mj_x = vis_x, mj_y = vis_z, mj_z = vis_y
    Then map 19 COCO keypoints → 17 IK targets (pelvis, trunk computed from hips/shoulders).
    """
    trunk_shoulder_fraction = 0.58
    num_frames = len(frames)
    landmarks = np.zeros((num_frames, 17, 4))

    for frame_idx, frame in enumerate(frames):
        kpts_vis = np.array(frame["kpts"])
        kpts_mj = np.zeros_like(kpts_vis)
        kpts_mj[:, 0] = kpts_vis[:, 0]  # mj_x = vis_x (lateral)
        kpts_mj[:, 1] = kpts_vis[:, 2]  # mj_y = vis_z (forward)
        kpts_mj[:, 2] = kpts_vis[:, 1]  # mj_z = vis_y (up)

        left_hip = kpts_mj[11]
        right_hip = kpts_mj[12]
        left_shoulder = kpts_mj[5]
        right_shoulder = kpts_mj[6]

        hip_mid = (left_hip + right_hip) / 2.0
        shoulder_mid = (left_shoulder + right_shoulder) / 2.0
        trunk = hip_mid * (1.0 - trunk_shoulder_fraction) + shoulder_mid * trunk_shoulder_fraction

        # 0: pelvis, 1: trunk, 2-3: hips, 4-5: knees, 6-7: ankles,
        # 8: head, 9-10: toes, 11-12: shoulders, 13-14: elbows, 15-16: wrists
        landmarks[frame_idx, 0, :3] = hip_mid
        landmarks[frame_idx, 1, :3] = trunk
        landmarks[frame_idx, 2, :3] = left_hip
        landmarks[frame_idx, 3, :3] = right_hip
        landmarks[frame_idx, 4, :3] = kpts_mj[13]   # L_knee
        landmarks[frame_idx, 5, :3] = kpts_mj[14]   # R_knee
        landmarks[frame_idx, 6, :3] = kpts_mj[15]   # L_ankle
        landmarks[frame_idx, 7, :3] = kpts_mj[16]   # R_ankle
        landmarks[frame_idx, 8, :3] = kpts_mj[0]    # head (nose)
        landmarks[frame_idx, 9, :3] = kpts_mj[17]   # L_toe
        landmarks[frame_idx, 10, :3] = kpts_mj[18]  # R_toe
        landmarks[frame_idx, 11, :3] = left_shoulder
        landmarks[frame_idx, 12, :3] = right_shoulder
        landmarks[frame_idx, 13, :3] = kpts_mj[7]   # L_elbow
        landmarks[frame_idx, 14, :3] = kpts_mj[8]   # R_elbow
        landmarks[frame_idx, 15, :3] = kpts_mj[9]   # L_wrist
        landmarks[frame_idx, 16, :3] = kpts_mj[10]  # R_wrist

        landmarks[frame_idx, :, 3] = 1.0

    return landmarks


def _run_synthetic(
    height_m: float,
    weight_kg: float,
    use_html: bool = False,
    html_output: str | None = None,
) -> None:
    """Launch viewer with a synthetic standing-squat-standing trajectory."""
    print(f"Generating synthetic trajectory (height={height_m:.2f}m, weight={weight_kg:.0f}kg)")

    skeleton = MujocoSkeleton(height_m=height_m, weight_kg=weight_kg)
    num_reps = 3
    frames_per_rep = 60
    standing_frames = 30
    q_trajectory = generate_synthetic_trajectory(
        skeleton, num_reps=num_reps,
        frames_per_rep=frames_per_rep,
        standing_frames=standing_frames,
    )

    print(f"Trajectory: {len(q_trajectory)} frames, {num_reps} synthetic reps")

    if use_html:
        import webbrowser
        from datetime import datetime
        from biomechanics_v2.visualizer.html_bridge import v2_synthetic_to_v1_html

        html_content = v2_synthetic_to_v1_html(
            skeleton, q_trajectory,
            fps=30.0,
            frames_per_rep=frames_per_rep,
            standing_frames=standing_frames,
            num_reps=num_reps,
        )
        recordings_dir = Path(__file__).parent.parent / "recordings"
        recordings_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(html_output) if html_output else recordings_dir / f"v2_squat_{timestamp}.html"
        output_path.write_text(html_content)
        print(f"HTML viewer saved: {output_path}")
        webbrowser.open(f"file://{output_path.resolve()}")
        return

    whatif_solver = MujocoWhatIfSolver(skeleton)

    viewer = SquatViewer(
        skeleton=skeleton,
        q_trajectory=q_trajectory,
        whatif_solver=whatif_solver,
        fps=30.0,
    )
    viewer.run()


def _run_capture(
    height_m: float,
    weight_kg: float,
    source: str,
    target_reps: int,
    no_preview: bool,
    use_html: bool = False,
    html_output: str | None = None,
) -> None:
    """Capture/process video and launch viewer with the results."""
    from biomechanics_v2.pipeline import BiomechanicsV2Pipeline
    from biomechanics_v2.visualizer.capture import SquatCaptureSession

    try:
        video_source: int | str = int(source)
    except ValueError:
        video_source = source
        if not Path(video_source).exists():
            print(f"Error: video file not found: {video_source}")
            sys.exit(1)

    pipeline = BiomechanicsV2Pipeline(
        height_m=height_m,
        weight_kg=weight_kg,
    )

    session = SquatCaptureSession(
        pipeline=pipeline,
        video_source=video_source,
        target_reps=target_reps,
        show_preview=not no_preview,
    )

    print(f"Processing video from: {video_source}")
    result = session.run()
    print(
        f"Capture complete: {len(result.q_trajectory)} frames, "
        f"{len(result.reps)} reps, {len(result.all_faults)} faults"
    )

    if len(result.q_trajectory) == 0:
        print("No valid frames captured. Exiting.")
        sys.exit(1)

    skeleton = pipeline.get_skeleton()

    if use_html:
        import webbrowser
        from datetime import datetime
        from biomechanics_v2.visualizer.html_bridge import v2_capture_to_v1_html

        html_content = v2_capture_to_v1_html(result, skeleton)
        recordings_dir = Path(__file__).parent.parent / "recordings"
        recordings_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(html_output) if html_output else recordings_dir / f"v2_squat_{timestamp}.html"
        output_path.write_text(html_content)
        print(f"HTML viewer saved: {output_path}")
        webbrowser.open(f"file://{output_path.resolve()}")
        return

    whatif_solver = MujocoWhatIfSolver(skeleton)

    viewer = SquatViewer(
        skeleton=skeleton,
        q_trajectory=result.q_trajectory,
        reps=result.reps,
        pipeline_frames=result.pipeline_frames,
        whatif_solver=whatif_solver,
        fps=result.fps,
    )
    viewer.run()


if __name__ == "__main__":
    main()

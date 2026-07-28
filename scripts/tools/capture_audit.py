"""Record a short webcam clip and build a self-contained HTML audit page
showing every pre-IK skeleton filter stage frame by frame, with gate,
confidence, and displacement data for auditing the filtering pipeline."""

from __future__ import annotations

import argparse
import base64
import json
import math
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from biomechanics.config import BiomechanicsConfig, load_pipeline_config  # noqa: E402
from biomechanics.kinematics.analytical_ik import AnalyticalIKSolver  # noqa: E402
from biomechanics.pose.mediapipe_fallback import MediaPipePoseEstimator  # noqa: E402
from biomechanics.utils.bone_constraints import BoneLengthConstraints  # noqa: E402
from biomechanics.utils.confidence_blend import ConfidenceBlender  # noqa: E402
from biomechanics.utils.ground_clamp import GroundClamp  # noqa: E402
from biomechanics.utils.position_filter import KeypointPositionSmoother  # noqa: E402
from biomechanics.utils.standing_gate import StandingPoseGate  # noqa: E402
from biomechanics.utils.types import CocoKeypoints as CK, Skeleton3D  # noqa: E402
from biomechanics.utils.velocity_clamp import VelocityClamp  # noqa: E402

RECORDINGS_DIR = _REPO_ROOT / "scripts" / "recordings"
TEMPLATE_PATH = Path(__file__).with_name("capture_audit_template.html")

# Pre-IK chain order must match biomechanics.utils.preik_chain.apply_preik_filters.
STAGE_ORDER = [
    ("confidence_blend", "Confidence Blend"),
    ("velocity_clamp", "Velocity Clamp"),
    ("bone_constraints", "Bone Constraints"),
    ("ground_clamp", "Ground Clamp"),
    ("position_smoother", "Position Smoother"),
    ("bone_reenforce", "Bone Re-enforce"),
]

# Validated dark-mode categorical palette; stage identity keeps a fixed slot.
PANEL_COLORS = {
    "raw2d": "#c3c2b7",
    "raw3d": "#3987e5",
    "confidence_blend": "#d95926",
    "velocity_clamp": "#199e70",
    "bone_constraints": "#c98500",
    "ground_clamp": "#d55181",
    "position_smoother": "#008300",
    "bone_reenforce": "#9085e9",
}

KEYPOINT_NAMES = [
    "nose", "l_eye", "r_eye", "l_ear", "r_ear",
    "l_shoulder", "r_shoulder", "l_elbow", "r_elbow", "l_wrist", "r_wrist",
    "l_hip", "r_hip", "l_knee", "r_knee", "l_ankle", "r_ankle",
    "l_foot", "r_foot",
]

ANGLE_KEYS = [
    "hip_flexion_l", "hip_flexion_r",
    "knee_flexion_l", "knee_flexion_r",
    "ankle_dorsiflexion_l", "ankle_dorsiflexion_r",
    "hip_adduction_l", "hip_adduction_r",
]

JPEG_QUALITY = 92
MIN_PROJECTION_POINTS = 4
PREVIEW_WINDOW = "Nowva Capture Audit"
STATIC_FEED_DIFF_THRESHOLD = 0.5
MAX_SCAN_DEVICES = 4


def _make_gate(gate_config) -> StandingPoseGate:
    return StandingPoseGate(
        min_confidence=gate_config.min_confidence,
        max_knee_flexion_deg=gate_config.max_knee_flexion_deg,
        max_trunk_flexion_deg=gate_config.max_trunk_flexion_deg,
        min_torso_length_m=gate_config.min_torso_length_m,
        max_torso_length_m=gate_config.max_torso_length_m,
        min_leg_extension_ratio=gate_config.min_leg_extension_ratio,
        required_consecutive_frames=gate_config.required_consecutive_frames,
    )


def _build_stage_fns(
    config: BiomechanicsConfig, standing_gate: StandingPoseGate
) -> tuple[dict, BoneLengthConstraints, GroundClamp]:
    blender = ConfidenceBlender(
        min_confidence=config.confidence_blend.min_confidence,
        max_confidence=config.confidence_blend.max_confidence,
    )
    velocity_clamp = VelocityClamp(
        max_velocity_m_per_s=config.velocity_clamp.max_velocity_m_per_s,
        target_fps=config.pipeline.target_fps,
    )
    bones = BoneLengthConstraints(
        calibration_frames=config.bone_constraints.calibration_frames,
        tolerance=config.bone_constraints.tolerance,
        standing_gate=standing_gate,
    )
    ground = GroundClamp(
        calibration_frames=config.ground_clamp.calibration_frames,
        stance_width_tolerance_m=config.ground_clamp.stance_width_tolerance_m,
        ankle_y_tolerance_m=config.ground_clamp.ankle_y_tolerance_m,
        min_leg_extension_ratio=config.ground_clamp.min_leg_extension_ratio,
        standing_gate=standing_gate,
    )
    smoother = KeypointPositionSmoother(
        min_cutoff=config.position_filter.min_cutoff,
        beta=config.position_filter.beta,
        d_cutoff=config.position_filter.d_cutoff,
    )
    stage_fns = {
        "confidence_blend": blender.blend,
        "velocity_clamp": velocity_clamp.clamp,
        "bone_constraints": bones.enforce,
        "ground_clamp": ground.clamp,
        "position_smoother": smoother.smooth,
        "bone_reenforce": bones.enforce,
    }
    return stage_fns, bones, ground


def _fit_projection(
    points_3d: np.ndarray,
    points_2d: np.ndarray,
    conf_3d: np.ndarray,
    conf_2d: np.ndarray,
    min_confidence: float,
) -> tuple[float, np.ndarray] | None:
    """Least-squares uniform scale + offset mapping 3D (x, y) to image pixels."""
    valid = (conf_3d >= min_confidence) & (conf_2d >= min_confidence)
    if int(valid.sum()) < MIN_PROJECTION_POINTS:
        return None
    src = points_3d[valid][:, :2]
    dst = points_2d[valid][:, :2]
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_centered = src - src_mean
    dst_centered = dst - dst_mean
    denom = float((src_centered ** 2).sum())
    if denom < 1e-9:
        return None
    scale = float((src_centered * dst_centered).sum()) / denom
    offset = dst_mean - scale * src_mean
    return scale, offset


def _project(points_3d: np.ndarray, scale: float, offset: np.ndarray) -> list:
    projected = points_3d[:, :2] * scale + offset
    return [[round(float(x), 1), round(float(y), 1)] for x, y in projected]


def _gate_state(gate: StandingPoseGate) -> dict:
    passes, required = gate.progress
    return {
        "ready": gate.is_ready,
        "passes": passes,
        "required": required,
        "failure": gate.last_failure,
    }


def _hip_position_cm(points: np.ndarray) -> float:
    hip_mid_y = (points[CK.LEFT_HIP][1] + points[CK.RIGHT_HIP][1]) / 2.0
    ankle_mid_y = (points[CK.LEFT_ANKLE][1] + points[CK.RIGHT_ANKLE][1]) / 2.0
    return round((hip_mid_y - ankle_mid_y) * 100.0, 1)


def _angles_dict(solver: AnalyticalIKSolver, skeleton: Skeleton3D) -> dict:
    angles = solver.solve(skeleton).as_dict()
    return {key: round(float(angles[key]), 1) for key in ANGLE_KEYS if key in angles}


def _show_preview(frame: np.ndarray, headline: str, subline: str) -> bool:
    """Draw status text on a copy of the frame and display it. Returns False on quit."""
    display = frame.copy()
    cv2.putText(display, headline, (40, 90), cv2.FONT_HERSHEY_SIMPLEX,
                2.2, (0, 0, 0), 10)
    cv2.putText(display, headline, (40, 90), cv2.FONT_HERSHEY_SIMPLEX,
                2.2, (255, 255, 255), 4)
    if subline:
        cv2.putText(display, subline, (40, 140), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (0, 0, 0), 5)
        cv2.putText(display, subline, (40, 140), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (255, 255, 255), 2)
    cv2.imshow(PREVIEW_WINDOW, display)
    key = cv2.waitKey(1) & 0xFF
    return key not in (ord("q"), 27)


def _mean_abs_diff(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    return float(np.abs(frame_a.astype(np.int16) - frame_b.astype(np.int16)).mean())


def _scan_live_devices(exclude: int) -> list[int]:
    live = []
    for dev in range(MAX_SCAN_DEVICES):
        if dev == exclude:
            continue
        cap = cv2.VideoCapture(dev)
        if not cap.isOpened():
            continue
        frames = [f for ok, f in (cap.read() for _ in range(5)) if ok and f is not None]
        cap.release()
        if len(frames) >= 2 and _mean_abs_diff(frames[0], frames[-1]) >= STATIC_FEED_DIFF_THRESHOLD:
            live.append(dev)
    return live


def record_session(
    seconds: float,
    device_id: int,
    resolution: tuple[int, int],
    countdown_seconds: float,
    preview: bool,
) -> Path:
    session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = RECORDINGS_DIR / f"audit_{session_name}"
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(device_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    if not cap.isOpened():
        raise ValueError(f"Could not open camera device {device_id}")

    warmup = [f for ok, f in (cap.read() for _ in range(10)) if ok and f is not None]
    if len(warmup) >= 2 and _mean_abs_diff(warmup[0], warmup[-1]) < STATIC_FEED_DIFF_THRESHOLD:
        cap.release()
        live = _scan_live_devices(exclude=device_id)
        hint = f" Live camera(s): device {live}." if live else ""
        raise ValueError(
            f"Camera device {device_id} is returning a frozen frame — it looks like a "
            f"virtual/placeholder camera, not a real feed.{hint} Re-run with --device N."
        )

    print(f"Recording to {session_dir}")
    print("Get in frame — full body visible, standing.")

    try:
        countdown_start = time.perf_counter()
        while (elapsed := time.perf_counter() - countdown_start) < countdown_seconds:
            ret, frame = cap.read()
            if not ret:
                continue
            if preview:
                remaining = math.ceil(countdown_seconds - elapsed)
                if not _show_preview(frame, str(remaining), "Get ready — full body in frame"):
                    raise KeyboardInterrupt

        timestamps: list[float] = []
        frame_shape = None
        start = time.perf_counter()
        index = 0
        while (elapsed := time.perf_counter() - start) < seconds:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            cv2.imwrite(
                str(frames_dir / f"{index:05d}.jpg"),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
            )
            timestamps.append(round(elapsed, 4))
            frame_shape = frame.shape
            index += 1
            if preview:
                if not _show_preview(frame, "REC", f"{elapsed:.1f}s / {seconds:.0f}s"):
                    break
    finally:
        cap.release()
        if preview:
            cv2.destroyAllWindows()
            cv2.waitKey(1)

    if not timestamps or frame_shape is None:
        raise ValueError("No frames captured — check the camera device")

    meta = {
        "session": session_name,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "device_id": device_id,
        "seconds": seconds,
        "width": int(frame_shape[1]),
        "height": int(frame_shape[0]),
        "timestamps": timestamps,
    }
    (session_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Captured {len(timestamps)} frames in {timestamps[-1]:.2f}s")
    return session_dir


def _encode_video(frames_dir: Path, fps: float, out_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg, "-y",
                "-framerate", f"{fps:.3f}",
                "-i", str(frames_dir / "%05d.jpg"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "23", "-movflags", "+faststart",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
        return

    frame_paths = sorted(frames_dir.glob("*.jpg"))
    first = cv2.imread(str(frame_paths[0]))
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(
        str(out_path), cv2.VideoWriter_fourcc(*"avc1"), fps, (width, height)
    )
    if not writer.isOpened():
        raise ValueError("No ffmpeg and OpenCV avc1 writer unavailable — install ffmpeg")
    for path in frame_paths:
        writer.write(cv2.imread(str(path)))
    writer.release()


def process_session(
    session_dir: Path, disabled: list[str], open_html: bool = True
) -> Path:
    meta = json.loads((session_dir / "meta.json").read_text())
    frames_dir = session_dir / "frames"
    frame_paths = sorted(frames_dir.glob("*.jpg"))
    if not frame_paths:
        raise ValueError(f"No frames found in {frames_dir}")

    timestamps = meta["timestamps"]
    if len(timestamps) > 1:
        fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
    else:
        fps = 30.0
    fps = round(fps, 2)

    config = load_pipeline_config()
    estimator = MediaPipePoseEstimator(
        confidence_threshold=config.pose.confidence_threshold,
        model_complexity=config.pose.model_complexity,
    )
    estimator.initialize()
    standing_gate = _make_gate(config.standing_gate)
    readiness_gate = _make_gate(config.readiness_gate)
    stage_fns, bones, ground = _build_stage_fns(config, standing_gate)
    ik_solver = AnalyticalIKSolver()
    proportions_applied = False

    enabled_stages = [key for key, _ in STAGE_ORDER if key not in disabled]
    min_conf = config.pose.confidence_threshold
    last_transform: tuple[float, np.ndarray] | None = None

    milestones: dict[str, int | None] = {
        "standing_pass": None,
        "readiness_pass": None,
        "bones_calibrated": None,
        "ground_calibrated": None,
    }

    frames: list[dict] = []
    print(f"Processing {len(frame_paths)} frames ({fps} fps)...")
    for index, path in enumerate(frame_paths):
        image = cv2.imread(str(path))
        skeleton_2d, skeleton_3d = estimator.estimate_both(image)

        entry: dict = {"detected": skeleton_3d is not None, "gated": True}
        if skeleton_3d is None:
            frames.append(entry)
            continue

        standing_gate.check(skeleton_3d)
        readiness_gate.check(skeleton_3d)
        if milestones["standing_pass"] is None and standing_gate.is_ready:
            milestones["standing_pass"] = index
        if milestones["readiness_pass"] is None and readiness_gate.is_ready:
            milestones["readiness_pass"] = index

        raw_points = skeleton_3d.to_numpy()
        conf_3d = np.array([kp.confidence for kp in skeleton_3d.keypoints])
        points_2d = skeleton_2d.to_numpy() if skeleton_2d is not None else np.zeros((19, 3))

        transform = _fit_projection(
            raw_points, points_2d, conf_3d, points_2d[:, 2], min_conf
        )
        if transform is not None:
            last_transform = transform
        transform = last_transform

        entry["gated"] = not readiness_gate.is_ready
        entry["k2d"] = [
            [round(float(x), 1), round(float(y), 1), round(float(c), 2)]
            for x, y, c in points_2d
        ]
        entry["conf3d"] = [round(float(c), 2) for c in conf_3d]
        entry["gates"] = {
            "standing": _gate_state(standing_gate),
            "readiness": _gate_state(readiness_gate),
        }
        entry["angles"] = {"raw": _angles_dict(ik_solver, skeleton_3d)}
        entry["hip_cm"] = {"raw": _hip_position_cm(raw_points)}

        stages_proj: dict = {}
        if transform is not None:
            stages_proj["raw3d"] = _project(raw_points, *transform)

        if readiness_gate.is_ready:
            displacement: dict = {}
            previous_points = raw_points
            current = skeleton_3d
            for key in enabled_stages:
                current = stage_fns[key](current)
                points = current.to_numpy()
                displacement[key] = [
                    round(float(d), 1)
                    for d in np.linalg.norm(points - previous_points, axis=1) * 100.0
                ]
                if transform is not None:
                    stages_proj[key] = _project(points, *transform)
                if key == "confidence_blend":
                    entry["conf_blend"] = [
                        round(float(kp.confidence), 2) for kp in current.keypoints
                    ]
                previous_points = points
            entry["disp"] = displacement
            entry["angles"]["filtered"] = _angles_dict(ik_solver, current)
            entry["hip_cm"]["filtered"] = _hip_position_cm(previous_points)

            if milestones["bones_calibrated"] is None and bones.is_calibrated:
                milestones["bones_calibrated"] = index
            if milestones["ground_calibrated"] is None and ground.is_calibrated:
                milestones["ground_calibrated"] = index
            if (
                not proportions_applied
                and bones.is_calibrated
                and bones.body_proportions is not None
            ):
                ik_solver.set_body_proportions(bones.body_proportions)
                proportions_applied = True
            entry["bones"] = {
                "calibrated": bones.is_calibrated,
                "progress": list(bones.progress),
            }
            entry["ground"] = {"calibrated": ground.is_calibrated}

        entry["stages"] = stages_proj
        frames.append(entry)
        if (index + 1) % 50 == 0:
            print(f"  {index + 1}/{len(frame_paths)}")

    estimator.release()

    body_proportions = None
    if bones.body_proportions is not None:
        body_proportions = {
            key: round(float(value), 4)
            for key, value in vars(bones.body_proportions).items()
        }

    panels = [{"key": "raw2d", "label": "Raw 2D Pose", "color": PANEL_COLORS["raw2d"]},
              {"key": "raw3d", "label": "Raw 3D (filter input)", "color": PANEL_COLORS["raw3d"]}]
    for key, label in STAGE_ORDER:
        if key in enabled_stages:
            panels.append({"key": key, "label": label, "color": PANEL_COLORS[key]})

    data = {
        "session": meta["session"],
        "recorded_at": meta["recorded_at"],
        "fps": fps,
        "width": meta["width"],
        "height": meta["height"],
        "n_frames": len(frames),
        "panels": panels,
        "stage_keys": enabled_stages,
        "disabled": sorted(disabled),
        "milestones": milestones,
        "body_proportions": body_proportions,
        "keypoint_names": KEYPOINT_NAMES,
        "config": {
            "pose": config.pose.model_dump(),
            "standing_gate": config.standing_gate.model_dump(),
            "readiness_gate": config.readiness_gate.model_dump(),
            "confidence_blend": config.confidence_blend.model_dump(),
            "velocity_clamp": config.velocity_clamp.model_dump(),
            "bone_constraints": config.bone_constraints.model_dump(),
            "ground_clamp": config.ground_clamp.model_dump(),
            "position_filter": config.position_filter.model_dump(),
        },
        "frames": frames,
    }
    (session_dir / "data.json").write_text(json.dumps(data))

    video_path = session_dir / "video.mp4"
    print("Encoding video...")
    _encode_video(frames_dir, fps, video_path)

    print("Building HTML...")
    video_b64 = base64.b64encode(video_path.read_bytes()).decode("ascii")
    html = TEMPLATE_PATH.read_text()
    html = html.replace("__TITLE__", f"Filter Audit — {meta['session']}")
    html = html.replace("__VIDEO_B64__", video_b64)
    html = html.replace("__DATA_JSON__", json.dumps(data, separators=(",", ":")))
    html_path = session_dir / "audit.html"
    html_path.write_text(html)

    print(f"Audit page: {html_path}")
    if open_html:
        webbrowser.open(html_path.as_uri())
    return html_path


def _latest_session() -> Path:
    sessions = sorted(RECORDINGS_DIR.glob("audit_*"))
    if not sessions:
        raise ValueError(f"No audit sessions found in {RECORDINGS_DIR}")
    return sessions[-1]


def _parse_disabled(raw: str) -> list[str]:
    if not raw:
        return []
    valid = {key for key, _ in STAGE_ORDER}
    disabled = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in disabled if item not in valid]
    if unknown:
        raise ValueError(f"Unknown stage(s) {unknown}. Valid: {sorted(valid)}")
    return disabled


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record a webcam clip and audit the pre-IK skeleton filter chain.",
    )
    subparsers = parser.add_subparsers(dest="command")

    record_parser = subparsers.add_parser("record", help="Record and process a new session")
    record_parser.add_argument("--seconds", type=float, default=10.0)
    record_parser.add_argument("--device", type=int, default=None)
    record_parser.add_argument("--delay", type=float, default=3.0,
                               help="Countdown before recording starts")
    record_parser.add_argument("--no-preview", action="store_true")

    process_parser = subparsers.add_parser(
        "process", help="Re-process a recorded session (e.g. with stages disabled)"
    )
    process_parser.add_argument("session_dir", nargs="?", default=None,
                                help="Session directory (default: most recent)")

    for sub in (record_parser, process_parser):
        sub.add_argument(
            "--disable", type=str, default="",
            help="Comma-separated stages to disable: "
                 + ",".join(key for key, _ in STAGE_ORDER),
        )
        sub.add_argument("--no-open", action="store_true")

    argv = sys.argv[1:]
    if not argv or argv[0] not in ("record", "process"):
        argv = ["record", *argv]
    args = parser.parse_args(argv)
    disabled = _parse_disabled(args.disable)

    if args.command == "record":
        config = load_pipeline_config()
        device = args.device if args.device is not None else config.capture.device_id
        session_dir = record_session(
            seconds=args.seconds,
            device_id=device,
            resolution=config.capture.resolution,
            countdown_seconds=args.delay,
            preview=not args.no_preview,
        )
    else:
        session_dir = Path(args.session_dir) if args.session_dir else _latest_session()

    process_session(session_dir, disabled, open_html=not args.no_open)


if __name__ == "__main__":
    main()

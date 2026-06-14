#!/usr/bin/env python3
"""Replay the DemoChoreographer animation offline with enhanced visuals."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import cv2
import numpy as np

from biomechanics.diagnosis import HypothesisEngine
from biomechanics.diagnosis.bridge import build_set_features, find_bottom_frame
from biomechanics.diagnosis.demo_builder import DemoData, build_demo_data
from biomechanics.diagnosis.rep_scoring import score_set
from biomechanics.viz.demo_renderer import (
    DEMO_CONNECTIONS,
    DRAWN_JOINTS,
    FINAL_HOLD_SECONDS,
    HIGHLIGHT_JOINTS,
    MORPH_IN_SECONDS,
    MORPH_OUT_SECONDS,
    SETTLE_SECONDS,
    YOYO_HOLD_SECONDS,
    YOYO_TRAVEL_SECONDS,
    ease_in_out,
    interpolate_pose,
    yoyo_weight,
)

SESSION_VERSION = 1
LAST_SESSION_POINTER = "last_session.path"

FRAME_WIDTH = 960
FRAME_HEIGHT = 720
PANEL_W = 480
WINDOW_NAME = "Choreographer Debug"
POSE_HEIGHT_FRAC = 0.55
POSE_Y_CENTER_FRAC = 0.42

VIEW_FRONT = 0
VIEW_DIAG = 1
VIEW_SIDE = 2
VIEW_ALL = 3
VIEW_ANGLES_DEG = [0.0, -45.0, 90.0]
VIEW_LABELS = ["FRONT", "DIAGONAL", "SIDE"]

BG_TOP = np.array([26, 12, 10], dtype=np.uint8)
BG_BOTTOM = np.array([42, 28, 18], dtype=np.uint8)
FLOOR_TINT = np.array([32, 24, 16], dtype=np.uint8)
GRID_COLOR = (55, 40, 32)
HORIZON_COLOR = (70, 50, 38)

BONE_CLR = (210, 145, 48)
JOINT_CLR = (160, 224, 64)
HIGHLIGHT_BONE_CLR = (80, 140, 255)
HIGHLIGHT_JOINT_CLR = (80, 170, 255)
GHOST_BONE_CLR = (90, 75, 60)
GHOST_JOINT_CLR = (100, 85, 68)

CAPTION_BG_CLR = np.array([40, 30, 22], dtype=np.uint8)
CAPTION_TEXT_CLR = (230, 230, 230)
LABEL_CLR = (180, 200, 220)

BONE_W = 4
JOINT_R = 7
HIGHLIGHT_R = 10
GHOST_BONE_W = 2
GHOST_JOINT_R = 4

GRID_H_COUNT = 16
GRID_V_COUNT = 12

_HIP_L, _HIP_R = 11, 12

CUE_LABELS: dict[str, str] = {
    "narrow_stance": "STANCE WIDTH",
    "narrow_foot_angle": "FOOT ANGLE",
    "knee_track_cue": "KNEE TRACKING",
    "weight_shift_cue": "WEIGHT BALANCE",
    "depth_cue_unfamiliar": "SQUAT DEPTH",
}


class _Phase(Enum):
    FADE_IN = auto()
    CUE_LOOP = auto()
    SETTLE = auto()
    FINAL_HOLD = auto()
    FADE_OUT = auto()
    DONE = auto()


@dataclass
class _ViewState:
    stack_px: np.ndarray
    ground_y: float
    bg: np.ndarray
    buf: np.ndarray
    settle_from: np.ndarray | None = None
    settle_to: np.ndarray | None = None


# ── Projection ───────────────────────────────────────────────────────────────

def _project(
    pose_stack: np.ndarray, frame_w: int, frame_h: int,
    view_angle_deg: float = 0.0,
) -> tuple[np.ndarray, float]:
    ref = pose_stack[0]
    lateral = ref[_HIP_R] - ref[_HIP_L]
    lat_xz = np.array([lateral[0], lateral[2]], dtype=np.float64)
    norm = np.linalg.norm(lat_xz)
    lat_xz = lat_xz / norm if norm > 1e-9 else np.array([0.0, 1.0])

    if view_angle_deg != 0.0:
        theta = math.radians(view_angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        lat_xz = np.array([
            lat_xz[0] * cos_t - lat_xz[1] * sin_t,
            lat_xz[0] * sin_t + lat_xz[1] * cos_t,
        ])

    hip_mid = (ref[_HIP_L] + ref[_HIP_R]) / 2.0
    y_vals = ref[:, 1]
    y_min, y_max = float(y_vals.min()), float(y_vals.max())
    pose_h = max(y_max - y_min, 1e-6)
    scale = POSE_HEIGHT_FRAC * frame_h / pose_h
    y_mid = (y_min + y_max) / 2.0

    offsets = pose_stack - hip_mid
    lat_px = (offsets[:, :, 0] * lat_xz[0] + offsets[:, :, 2] * lat_xz[1]) * scale
    vert_px = (pose_stack[:, :, 1] - y_mid) * scale

    cx, cy = frame_w / 2.0, frame_h * POSE_Y_CENTER_FRAC
    proj = np.empty((pose_stack.shape[0], pose_stack.shape[1], 2), dtype=np.float32)
    proj[:, :, 0] = cx + lat_px
    proj[:, :, 1] = cy - vert_px
    ground_y = cy + (pose_h / 2.0) * scale
    return proj, ground_y


# ── Background ───────────────────────────────────────────────────────────────

def _build_background(w: int, h: int, ground_y: float) -> np.ndarray:
    bg = np.zeros((h, w, 3), dtype=np.uint8)
    gy = int(min(ground_y, h))

    if gy > 0:
        t = np.linspace(0.0, 1.0, gy, dtype=np.float32)[:, np.newaxis]
        sky = BG_TOP.astype(np.float32) + t * (BG_BOTTOM.astype(np.float32) - BG_TOP.astype(np.float32))
        bg[:gy, :] = sky.astype(np.uint8)[:, np.newaxis, :]

    if gy < h:
        t = np.linspace(0.0, 1.0, h - gy, dtype=np.float32)[:, np.newaxis]
        floor = BG_BOTTOM.astype(np.float32) + t * (FLOOR_TINT.astype(np.float32) - BG_BOTTOM.astype(np.float32))
        bg[gy:, :] = floor.astype(np.uint8)[:, np.newaxis, :]

    vy = np.linspace(-1.0, 1.0, h, dtype=np.float32) ** 2
    vx = np.linspace(-1.0, 1.0, w, dtype=np.float32) ** 2
    vignette = 1.0 - np.add.outer(vy, vx) * 0.2
    np.clip(vignette, 0.55, 1.0, out=vignette)
    bg = (bg.astype(np.float32) * vignette[:, :, np.newaxis]).astype(np.uint8)
    return bg


def _draw_ground_grid(canvas: np.ndarray, ground_y: float) -> None:
    h, w = canvas.shape[:2]
    gy = int(ground_y)
    floor_h = h - gy
    if floor_h <= 10:
        return

    cv2.line(canvas, (0, gy), (w, gy), HORIZON_COLOR, 1, cv2.LINE_AA)

    vp_x = w // 2
    for i in range(1, GRID_H_COUNT + 1):
        t = (i / GRID_H_COUNT) ** 1.6
        y = int(gy + t * floor_h)
        fade = max(0.3, 1.0 - t * 0.6)
        color = tuple(int(c * fade) for c in GRID_COLOR)
        cv2.line(canvas, (0, y), (w, y), color, 1, cv2.LINE_AA)

    for i in range(-GRID_V_COUNT, GRID_V_COUNT + 1):
        if i == 0:
            continue
        spread = (i / GRID_V_COUNT) * w * 0.55
        bx = int(vp_x + spread)
        fade = max(0.3, 1.0 - abs(i / GRID_V_COUNT) * 0.5)
        color = tuple(int(c * fade) for c in GRID_COLOR)
        cv2.line(canvas, (bx, h), (vp_x, gy), color, 1, cv2.LINE_AA)


# ── Shadow ───────────────────────────────────────────────────────────────────

def _draw_shadow(canvas: np.ndarray, pts: np.ndarray, ground_y: float) -> None:
    foot_xs = [float(pts[i, 0]) for i in DRAWN_JOINTS if i >= 15]
    if not foot_xs:
        return
    cx = int(sum(foot_xs) / len(foot_xs))
    cy = int(ground_y + 3)
    rx = max(25, int((max(foot_xs) - min(foot_xs)) * 0.5 + 35))
    ry = max(6, rx // 8)

    overlay = canvas.copy()
    cv2.ellipse(overlay, (cx, cy), (rx, ry), 0, 0, 360, (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.3, canvas, 0.7, 0, dst=canvas)


# ── Skeleton Drawing ─────────────────────────────────────────────────────────

def _scale_clr(color: tuple, a: float) -> tuple:
    return (int(color[0] * a), int(color[1] * a), int(color[2] * a))


def _draw_skeleton(
    canvas: np.ndarray,
    pts: np.ndarray,
    bone_clr: tuple = BONE_CLR,
    joint_clr: tuple = JOINT_CLR,
    bone_w: int = BONE_W,
    joint_r: int = JOINT_R,
    highlight: tuple[int, ...] = (),
    highlight_r: int = HIGHLIGHT_R,
    alpha: float = 1.0,
) -> None:
    if alpha < 0.02:
        return
    bc = _scale_clr(bone_clr, alpha)
    jc = _scale_clr(joint_clr, alpha)
    hbc = _scale_clr(HIGHLIGHT_BONE_CLR, alpha)
    hjc = _scale_clr(HIGHLIGHT_JOINT_CLR, alpha)

    for a, b in DEMO_CONNECTIONS:
        hi = a in highlight and b in highlight
        p1 = (int(pts[a, 0]), int(pts[a, 1]))
        p2 = (int(pts[b, 0]), int(pts[b, 1]))
        cv2.line(canvas, p1, p2, hbc if hi else bc, bone_w, cv2.LINE_AA)

    for j in DRAWN_JOINTS:
        c = (int(pts[j, 0]), int(pts[j, 1]))
        if j in highlight:
            cv2.circle(canvas, c, highlight_r, hjc, -1, cv2.LINE_AA)
        else:
            cv2.circle(canvas, c, joint_r, jc, -1, cv2.LINE_AA)


# ── Labels ───────────────────────────────────────────────────────────────────

def _draw_pill(canvas: np.ndarray, text: str, cx: int, cy: int, scale: float = 0.85) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, 2)
    pad_x, pad_y = 22, 10
    rx, ry = tw // 2 + pad_x, th // 2 + pad_y + baseline

    x1 = max(0, cx - rx)
    y1 = max(0, cy - ry)
    x2 = min(canvas.shape[1], cx + rx)
    y2 = min(canvas.shape[0], cy + ry)
    if x2 <= x1 or y2 <= y1:
        return

    roi = canvas[y1:y2, x1:x2]
    pill = np.full_like(roi, CAPTION_BG_CLR)
    cv2.addWeighted(pill, 0.7, roi, 0.3, 0, dst=roi)
    cv2.putText(
        canvas, text, (cx - tw // 2, cy + th // 2),
        font, scale, CAPTION_TEXT_CLR, 2, cv2.LINE_AA,
    )


def _draw_cue_label(canvas: np.ndarray, cause_id: str, scale: float = 0.7) -> None:
    label = CUE_LABELS.get(cause_id, cause_id.upper().replace("_", " "))
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(label, font, scale, 2)
    cx = canvas.shape[1] // 2
    cy = 42
    cv2.putText(
        canvas, label, (cx - tw // 2, cy),
        font, scale, LABEL_CLR, 2, cv2.LINE_AA,
    )


# ── State Machine Helpers ────────────────────────────────────────────────────

def _current_pts(
    phase: _Phase,
    cue_idx: int,
    elapsed: float,
    stack_px: np.ndarray,
    buf: np.ndarray,
    settle_from: np.ndarray | None,
    settle_to: np.ndarray | None,
) -> np.ndarray:
    if phase == _Phase.CUE_LOOP:
        w = yoyo_weight(elapsed, YOYO_TRAVEL_SECONDS, YOYO_HOLD_SECONDS)
        return interpolate_pose(stack_px[cue_idx], stack_px[cue_idx + 1], w, buf)
    if phase == _Phase.SETTLE and settle_from is not None and settle_to is not None:
        w = ease_in_out(min(elapsed / SETTLE_SECONDS, 1.0))
        return interpolate_pose(settle_from, settle_to, w, buf)
    if phase == _Phase.FADE_IN:
        return stack_px[0].copy()
    return stack_px[-1].copy()


# ── Panel Rendering ──────────────────────────────────────────────────────────

def _render_panel(
    vs: _ViewState,
    phase: _Phase,
    cue_idx: int,
    elapsed: float,
    cues: list,
    view_label: str | None = None,
    compact: bool = False,
) -> np.ndarray:
    frame_h, frame_w = vs.bg.shape[:2]
    canvas = vs.bg.copy()
    _draw_ground_grid(canvas, vs.ground_y)

    pts = _current_pts(
        phase, cue_idx, elapsed, vs.stack_px, vs.buf,
        vs.settle_from, vs.settle_to,
    )

    alpha = 1.0
    if phase == _Phase.FADE_IN:
        alpha = ease_in_out(min(elapsed / MORPH_IN_SECONDS, 1.0))
    elif phase == _Phase.FADE_OUT:
        alpha = 1.0 - ease_in_out(min(elapsed / MORPH_OUT_SECONDS, 1.0))

    if alpha > 0.2:
        _draw_shadow(canvas, pts, vs.ground_y)

    skel_bone_w = max(2, BONE_W - 1) if compact else BONE_W
    skel_joint_r = max(4, JOINT_R - 2) if compact else JOINT_R
    skel_highlight_r = max(6, HIGHLIGHT_R - 3) if compact else HIGHLIGHT_R
    ghost_bone_w = max(1, GHOST_BONE_W) if compact else GHOST_BONE_W
    ghost_joint_r = max(2, GHOST_JOINT_R - 1) if compact else GHOST_JOINT_R

    if phase == _Phase.CUE_LOOP:
        _draw_skeleton(
            canvas, vs.stack_px[cue_idx],
            bone_clr=GHOST_BONE_CLR, joint_clr=GHOST_JOINT_CLR,
            bone_w=ghost_bone_w, joint_r=ghost_joint_r,
            alpha=alpha * 0.5,
        )
    elif phase == _Phase.FINAL_HOLD:
        _draw_skeleton(
            canvas, vs.stack_px[0],
            bone_clr=GHOST_BONE_CLR, joint_clr=GHOST_JOINT_CLR,
            bone_w=ghost_bone_w, joint_r=ghost_joint_r,
            alpha=alpha * 0.5,
        )

    highlight = ()
    if phase == _Phase.CUE_LOOP and cue_idx < len(cues):
        highlight = HIGHLIGHT_JOINTS.get(cues[cue_idx].cause_id, ())
    _draw_skeleton(
        canvas, pts, highlight=highlight, alpha=alpha,
        bone_w=skel_bone_w, joint_r=skel_joint_r, highlight_r=skel_highlight_r,
    )

    pill_scale = 0.55 if compact else 0.85
    label_scale = 0.5 if compact else 0.7

    if alpha > 0.5:
        if phase == _Phase.CUE_LOOP and cue_idx < len(cues):
            cue = cues[cue_idx]
            _draw_cue_label(canvas, cue.cause_id, scale=label_scale)
            _draw_pill(
                canvas, cue.magnitude_text,
                frame_w // 2, frame_h - 50, scale=pill_scale,
            )
        elif phase == _Phase.FINAL_HOLD:
            _draw_pill(
                canvas, "Corrected form",
                frame_w // 2, frame_h - 50, scale=pill_scale + 0.05,
            )

    if view_label:
        font = cv2.FONT_HERSHEY_SIMPLEX
        vl_scale = 0.45 if compact else 0.5
        (tw, th), _ = cv2.getTextSize(view_label, font, vl_scale, 1)
        cv2.putText(
            canvas, view_label, (frame_w - tw - 10, th + 10),
            font, vl_scale, (140, 140, 160), 1, cv2.LINE_AA,
        )

    return canvas


# ── Session / Diagnosis ──────────────────────────────────────────────────────

def _resolve_last_session(recordings_dir: Path) -> Path | None:
    pointer = recordings_dir / LAST_SESSION_POINTER
    if pointer.exists():
        pointed = Path(pointer.read_text().strip())
        if pointed.exists():
            return pointed
    candidates = sorted(
        recordings_dir.glob("*.session.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_session(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: Session file not found: {path}")
        sys.exit(1)
    payload = json.loads(path.read_text())
    if payload.get("version") != SESSION_VERSION:
        print(f"ERROR: Unsupported session version {payload.get('version')!r}")
        sys.exit(1)
    for key in ("baseline", "replay_reps", "fps"):
        if key not in payload:
            print(f"ERROR: Session missing field: {key}")
            sys.exit(1)
    if not payload["replay_reps"]:
        print("ERROR: Session has no replay reps")
        sys.exit(1)
    return payload


def _build_demo(
    replay_reps: list, athlete_params: dict, baseline: dict,
) -> tuple[DemoData | None, dict]:
    set_features = build_set_features(replay_reps, athlete_params, baseline)
    engine = HypothesisEngine()
    diagnosis = engine.diagnose(set_features)
    score_summary = score_set(
        set_features.per_rep_kinematics,
        set_features.anthropometry,
        set_features.rom,
    )
    worst_idx = max(0, min(score_summary.worst_rep_number - 2, len(replay_reps) - 1))
    bottom = find_bottom_frame(replay_reps[worst_idx])
    demo = build_demo_data(
        bottom["kpts"], diagnosis,
        anthro=set_features.anthropometry, rom=set_features.rom,
    )
    info = {
        "confidence": diagnosis.confidence,
        "symptoms": [s.symptom_id for s in diagnosis.detected_symptoms],
        "causes": [c.cause_id for c in diagnosis.immediate_causes],
        "worst_rep": score_summary.worst_rep_number,
        "worst_score": round(
            score_summary.per_rep_scores[worst_idx].composite_score * 100,
        ),
        "mean_score": round(score_summary.mean_score * 100),
    }
    return demo, info


# ── View State Init ──────────────────────────────────────────────────────────

def _init_view(
    pose_stack: np.ndarray, w: int, h: int, angle_deg: float,
) -> _ViewState:
    stack_px, ground_y = _project(pose_stack, w, h, angle_deg)
    bg = _build_background(w, h, ground_y)
    buf = np.empty((pose_stack.shape[1], 2), dtype=np.float32)
    return _ViewState(stack_px, ground_y, bg, buf)


# ── Main Loop ────────────────────────────────────────────────────────────────

def _play(demo: DemoData, cycles_per_cue: int) -> None:
    yoyo_period = 2.0 * (YOYO_TRAVEL_SECONDS + YOYO_HOLD_SECONDS)
    dwell = cycles_per_cue * yoyo_period

    single_views = [
        _init_view(demo.pose_stack, FRAME_WIDTH, FRAME_HEIGHT, a)
        for a in VIEW_ANGLES_DEG
    ]
    panel_views = [
        _init_view(demo.pose_stack, PANEL_W, FRAME_HEIGHT, a)
        for a in VIEW_ANGLES_DEG
    ]
    all_views = single_views + panel_views

    events: list[tuple[float, _Phase, int]] = []
    t = 0.0
    events.append((t, _Phase.FADE_IN, 0))
    t += MORPH_IN_SECONDS
    for i in range(len(demo.cues)):
        if i > 0:
            events.append((t, _Phase.SETTLE, i))
            t += SETTLE_SECONDS
        events.append((t, _Phase.CUE_LOOP, i))
        t += dwell
    events.append((t, _Phase.SETTLE, -1))
    t += SETTLE_SECONDS
    events.append((t, _Phase.FINAL_HOLD, -1))
    t += FINAL_HOLD_SECONDS
    events.append((t, _Phase.FADE_OUT, -1))
    t += MORPH_OUT_SECONDS
    events.append((t, _Phase.DONE, -1))
    total_duration = t

    view_mode = VIEW_FRONT
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, FRAME_WIDTH, FRAME_HEIGHT)

    loop_start = time.monotonic()
    phase = _Phase.FADE_IN
    cue_idx = 0
    phase_start = loop_start
    event_ptr = 1

    def _reset_settle() -> None:
        for vs in all_views:
            vs.settle_from = None
            vs.settle_to = None

    _reset_settle()

    while True:
        now = time.monotonic()
        wall = now - loop_start

        if wall >= total_duration:
            loop_start = now
            wall = 0.0
            phase = _Phase.FADE_IN
            cue_idx = 0
            phase_start = now
            event_ptr = 1
            _reset_settle()

        while event_ptr < len(events) and wall >= events[event_ptr][0]:
            _, new_phase, new_cue = events[event_ptr]
            if new_phase == _Phase.SETTLE:
                for vs in all_views:
                    vs.settle_from = _current_pts(
                        phase, cue_idx, now - phase_start, vs.stack_px, vs.buf,
                        vs.settle_from, vs.settle_to,
                    ).copy()
                    vs.settle_to = (
                        vs.stack_px[-1] if new_cue == -1 else vs.stack_px[new_cue]
                    ).copy()
            phase = new_phase
            if new_cue >= 0:
                cue_idx = new_cue
            phase_start = loop_start + events[event_ptr][0]
            event_ptr += 1

        elapsed = now - phase_start

        if view_mode == VIEW_ALL:
            panels = [
                _render_panel(
                    panel_views[i], phase, cue_idx, elapsed, demo.cues,
                    view_label=VIEW_LABELS[i], compact=True,
                )
                for i in range(3)
            ]
            output = np.hstack(panels)
        else:
            output = _render_panel(
                single_views[view_mode], phase, cue_idx, elapsed, demo.cues,
            )

        cv2.imshow(WINDOW_NAME, output)
        key = cv2.waitKey(16) & 0xFF
        if key == ord("q"):
            break

        new_mode = view_mode
        if key == ord("1"):
            new_mode = VIEW_FRONT
        elif key == ord("2"):
            new_mode = VIEW_DIAG
        elif key == ord("3"):
            new_mode = VIEW_SIDE
        elif key == ord("a"):
            new_mode = VIEW_ALL

        if new_mode != view_mode:
            view_mode = new_mode
            if view_mode == VIEW_ALL:
                cv2.resizeWindow(WINDOW_NAME, PANEL_W * 3, FRAME_HEIGHT)
            else:
                cv2.resizeWindow(WINDOW_NAME, FRAME_WIDTH, FRAME_HEIGHT)

    cv2.destroyAllWindows()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay DemoChoreographer animation from a session file",
    )
    parser.add_argument(
        "session", nargs="?", default=None,
        help="Path to .session.json (default: latest)",
    )
    parser.add_argument(
        "--cycles", type=int, default=2,
        help="Yoyo cycles per cue (default: 2)",
    )
    args = parser.parse_args()

    recordings_dir = Path(__file__).parent.parent / "recordings"
    if args.session:
        session_path = Path(args.session)
    else:
        session_path = _resolve_last_session(recordings_dir)
        if session_path is None:
            print("ERROR: No saved session found. Run a full capture first.")
            sys.exit(1)

    payload = _load_session(session_path)
    athlete_params = payload.get("athlete_params")
    if not athlete_params:
        print("ERROR: Session has no athlete params")
        sys.exit(1)

    print(f"Session: {session_path}")
    print(f"Reps: {len(payload['replay_reps'])}")
    print()

    demo, info = _build_demo(
        payload["replay_reps"], athlete_params, payload["baseline"],
    )

    print(f"  Confidence: {info['confidence']:.0%}")
    print(f"  Symptoms: {info['symptoms']}")
    print(f"  Tier-1 causes: {info['causes']}")
    print(f"  Worst rep: {info['worst_rep']} (score {info['worst_score']}/100)")
    print(f"  Mean score: {info['mean_score']}/100")

    if demo is None:
        print("\nNo immediate causes — nothing to animate.")
        return

    print(f"\nDemo cues ({len(demo.cues)}):")
    for cue in demo.cues:
        print(f"  [{cue.cue_index}] {cue.cause_id} — {cue.magnitude_text}")

    print("\nPlaying choreography (loops until q)...")
    print("  Keys: 1=front  2=diagonal  3=side  a=all three")
    _play(demo, args.cycles)


if __name__ == "__main__":
    main()

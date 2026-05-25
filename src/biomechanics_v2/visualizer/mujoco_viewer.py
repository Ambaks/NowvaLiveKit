"""MuJoCo-based 3D viewer for squat trajectory playback and what-if exploration.

Uses MuJoCo offscreen Renderer for 3D rendering and OpenCV for display.
Keyboard controls handle playback, rep navigation, and perturbation toggling.
"""

from __future__ import annotations

import math
import sys
import time

import cv2
import mujoco
import numpy as np

from biomechanics.utils.types import FaultEvent, PipelineFrame, RepData
from biomechanics_v2.model.skeleton_model import MujocoSkeleton
from biomechanics_v2.solver.angle_extract import q_to_joint_angles
from biomechanics_v2.solver.mujoco_whatif import MujocoWhatIfSolver

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

_PRESET_PERTURBATIONS = [
    {
        "name": "+5 deg dorsiflexion",
        "perturbation": {
            "L_ankle.rx": math.radians(5),
            "R_ankle.rx": math.radians(5),
        },
        "foot_target_delta": None,
    },
    {
        "name": "+5cm stance width",
        "perturbation": {},
        "foot_target_delta": np.array([-0.025, 0.0, 0.0, 0.025, 0.0, 0.0]),
    },
    {
        "name": "+5 deg toe-out",
        "perturbation": {
            "L_ankle.ry": math.radians(-5),
            "R_ankle.ry": math.radians(5),
        },
        "foot_target_delta": None,
    },
]

_CAMERA_PRESETS = {
    "side": {"azimuth": 90.0, "elevation": -20.0, "distance": 3.0},
    "front": {"azimuth": 180.0, "elevation": -15.0, "distance": 3.0},
    "three_quarter": {"azimuth": 135.0, "elevation": -20.0, "distance": 3.2},
}

_CAMERA_ORDER = ["side", "front", "three_quarter"]


class SquatViewer:
    """Interactive MuJoCo viewer for squat trajectory playback and what-if exploration.

    Controls:
        SPACE       Play / Pause
        A / D       Step backward / forward one frame
        W / S       Speed up / slow down playback
        [ / ]       Jump to previous / next rep bottom
        R           Reset to frame 0
        I           Print detailed joint angles for current frame
        1 / 2 / 3   Toggle preset what-if perturbation
        T           Toggle corrected / original pose
        C           Cycle camera view (side / front / three-quarter)
        Q / ESC     Close viewer
    """

    def __init__(
        self,
        skeleton: MujocoSkeleton,
        q_trajectory: np.ndarray,
        reps: list[RepData] | None = None,
        pipeline_frames: list[PipelineFrame] | None = None,
        whatif_solver: MujocoWhatIfSolver | None = None,
        fps: float = 30.0,
    ):
        self._skeleton = skeleton
        self._q_trajectory = q_trajectory
        self._reps = reps or []
        self._pipeline_frames = pipeline_frames or []
        self._whatif_solver = whatif_solver
        self._fps = fps

        self._num_frames = len(q_trajectory)

        self._frame_idx = 0
        self._playing = False
        self._playback_speed = 1.0

        self._show_corrected = False
        self._active_perturbation_idx: int | None = None
        self._cached_warped_trajectories: dict[int, np.ndarray] = {}

        self._rep_bottom_frames = self._find_rep_bottoms()

        self._camera_idx = 0

    def run(self) -> None:
        """Launch the viewer and enter the playback loop."""
        if self._num_frames == 0:
            print("No frames to display.")
            return

        model = self._skeleton.model
        data = self._skeleton.data

        model.vis.global_.offwidth = WINDOW_WIDTH
        model.vis.global_.offheight = WINDOW_HEIGHT

        self._hide_mocap_geoms()
        self._disable_weld_constraints()

        renderer = mujoco.Renderer(model, height=WINDOW_HEIGHT, width=WINDOW_WIDTH)
        camera = mujoco.MjvCamera()
        self._apply_camera_preset(camera)

        scene_option = mujoco.MjvOption()

        self._print_controls()
        self._update_pose()

        last_advance_time = time.perf_counter()
        window_name = "V2 Squat Viewer"

        try:
            while True:
                now = time.perf_counter()
                if self._playing and self._num_frames > 1:
                    frame_duration = 1.0 / (self._fps * self._playback_speed)
                    if now - last_advance_time >= frame_duration:
                        self._frame_idx = (self._frame_idx + 1) % self._num_frames
                        last_advance_time = now

                self._update_pose()
                renderer.update_scene(data, camera, scene_option)
                frame_rgb = renderer.render()
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

                self._draw_overlay(frame_bgr)
                self._draw_scrubber(frame_bgr)

                cv2.imshow(window_name, frame_bgr)

                key = cv2.waitKey(16) & 0xFF
                if not self._handle_key(key, camera):
                    break
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            renderer.close()
            cv2.destroyAllWindows()
            self._restore_mocap_geoms()

    # ------------------------------------------------------------------
    # Keyboard handler
    # ------------------------------------------------------------------

    def _handle_key(self, key: int, camera: mujoco.MjvCamera) -> bool:
        """Process a key press. Returns False to quit."""
        if key == 255:
            return True

        if key == ord("q") or key == 27:
            return False

        elif key == ord(" "):
            self._playing = not self._playing

        elif key == ord("d"):
            self._playing = False
            self._frame_idx = min(self._frame_idx + 1, self._num_frames - 1)

        elif key == ord("a"):
            self._playing = False
            self._frame_idx = max(self._frame_idx - 1, 0)

        elif key == ord("w"):
            self._playback_speed = min(self._playback_speed * 1.5, 8.0)

        elif key == ord("s"):
            self._playback_speed = max(self._playback_speed / 1.5, 0.1)

        elif key == ord("["):
            self._jump_to_prev_rep()

        elif key == ord("]"):
            self._jump_to_next_rep()

        elif key == ord("r"):
            self._frame_idx = 0
            self._playing = False

        elif key == ord("t"):
            if self._active_perturbation_idx is not None:
                self._show_corrected = not self._show_corrected

        elif key == ord("i"):
            self._print_frame_detail()

        elif key == ord("c"):
            self._camera_idx = (self._camera_idx + 1) % len(_CAMERA_ORDER)
            self._apply_camera_preset(camera)

        elif key in (ord("1"), ord("2"), ord("3")):
            self._toggle_preset_perturbation(key - ord("1"))

        return True

    # ------------------------------------------------------------------
    # Pose update
    # ------------------------------------------------------------------

    def _update_pose(self) -> None:
        """Write the current frame's q-vector into the skeleton and run FK."""
        if self._show_corrected and self._active_perturbation_idx is not None:
            warped = self._cached_warped_trajectories.get(
                self._active_perturbation_idx
            )
            if warped is not None:
                q_vector = warped[self._frame_idx]
            else:
                q_vector = self._q_trajectory[self._frame_idx]
        else:
            q_vector = self._q_trajectory[self._frame_idx]

        self._skeleton.set_qpos(q_vector)
        mujoco.mj_forward(self._skeleton.model, self._skeleton.data)

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _apply_camera_preset(self, camera: mujoco.MjvCamera) -> None:
        preset_name = _CAMERA_ORDER[self._camera_idx]
        preset = _CAMERA_PRESETS[preset_name]
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.azimuth = preset["azimuth"]
        camera.elevation = preset["elevation"]
        camera.distance = preset["distance"]
        camera.lookat[:] = [0.0, 0.0, 0.7]

    # ------------------------------------------------------------------
    # What-if perturbations
    # ------------------------------------------------------------------

    def _toggle_preset_perturbation(self, preset_idx: int) -> None:
        if self._whatif_solver is None:
            return
        if preset_idx >= len(_PRESET_PERTURBATIONS):
            return

        if self._active_perturbation_idx == preset_idx:
            self._show_corrected = False
            self._active_perturbation_idx = None
            return

        self._active_perturbation_idx = preset_idx
        self._show_corrected = True

        if preset_idx not in self._cached_warped_trajectories:
            self._compute_warped_trajectory(preset_idx)

    def _compute_warped_trajectory(self, preset_idx: int) -> None:
        preset = _PRESET_PERTURBATIONS[preset_idx]
        print(f"Computing what-if: {preset['name']}...")

        bottom_frame = self._find_global_bottom_frame()
        warped = self._whatif_solver.warp_trajectory(
            q_trajectory=self._q_trajectory,
            bottom_frame=bottom_frame,
            perturbation=preset["perturbation"],
            foot_target_delta=preset["foot_target_delta"],
        )
        self._cached_warped_trajectories[preset_idx] = warped
        print(f"What-if ready: {preset['name']}")

    # ------------------------------------------------------------------
    # Rep navigation
    # ------------------------------------------------------------------

    def _find_rep_bottoms(self) -> list[int]:
        bottoms = []
        knee_idx = self._skeleton.get_joint_index("L_knee", "rx")
        for rep in self._reps:
            start = rep.start_frame
            end = min(rep.end_frame, self._num_frames)
            if start < end:
                rep_slice = self._q_trajectory[start:end, knee_idx]
                bottom = start + int(np.argmax(rep_slice))
                bottoms.append(bottom)
        return bottoms

    def _find_global_bottom_frame(self) -> int:
        knee_idx = self._skeleton.get_joint_index("L_knee", "rx")
        if self._rep_bottom_frames:
            depths = [
                self._q_trajectory[frame, knee_idx]
                for frame in self._rep_bottom_frames
            ]
            return self._rep_bottom_frames[int(np.argmax(depths))]
        return int(np.argmax(self._q_trajectory[:, knee_idx]))

    def _jump_to_prev_rep(self) -> None:
        if not self._rep_bottom_frames:
            return
        earlier = [f for f in self._rep_bottom_frames if f < self._frame_idx]
        self._frame_idx = earlier[-1] if earlier else self._rep_bottom_frames[-1]
        self._playing = False

    def _jump_to_next_rep(self) -> None:
        if not self._rep_bottom_frames:
            return
        later = [f for f in self._rep_bottom_frames if f > self._frame_idx]
        self._frame_idx = later[0] if later else self._rep_bottom_frames[0]
        self._playing = False

    # ------------------------------------------------------------------
    # Visual helpers
    # ------------------------------------------------------------------

    def _hide_mocap_geoms(self) -> None:
        model = self._skeleton.model
        self._saved_mocap_alphas: dict[int, float] = {}
        for geom_id in range(model.ngeom):
            body_id = model.geom_bodyid[geom_id]
            body_name = mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id
            )
            if body_name and body_name.startswith("mocap_"):
                self._saved_mocap_alphas[geom_id] = float(
                    model.geom_rgba[geom_id, 3]
                )
                model.geom_rgba[geom_id, 3] = 0.0

    def _restore_mocap_geoms(self) -> None:
        model = self._skeleton.model
        for geom_id, alpha in self._saved_mocap_alphas.items():
            if geom_id < model.ngeom:
                model.geom_rgba[geom_id, 3] = alpha

    def _disable_weld_constraints(self) -> None:
        data = self._skeleton.data
        if self._skeleton.model.neq > 0:
            data.eq_active[:] = 0

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------

    def _draw_overlay(self, frame: np.ndarray) -> None:
        state_label = "PLAYING" if self._playing else "PAUSED"
        speed_label = f"{self._playback_speed:.1f}x"
        rep_number = self._current_rep_number()
        rep_label = f"Rep {rep_number}" if rep_number else "--"
        camera_label = _CAMERA_ORDER[self._camera_idx]

        line1 = (
            f"Frame {self._frame_idx + 1}/{self._num_frames}  |  "
            f"{rep_label}  |  {state_label} {speed_label}  |  {camera_label}"
        )

        q_vector = self._q_trajectory[self._frame_idx]
        angles = q_to_joint_angles(
            self._skeleton, q_vector, frame_index=self._frame_idx
        )
        line2 = (
            f"Hip: {angles.hip_flexion_l:.0f} deg  "
            f"Knee: {angles.knee_flexion_l:.0f} deg  "
            f"Ankle: {angles.ankle_dorsiflexion_l:.0f} deg  "
            f"Trunk: {angles.trunk_flexion:.0f} deg"
        )

        whatif_label = ""
        if self._show_corrected and self._active_perturbation_idx is not None:
            preset_name = _PRESET_PERTURBATIONS[self._active_perturbation_idx]["name"]
            whatif_label = f"What-If: {preset_name}"

        self._put_text(frame, line1, (10, 25), scale=0.55)
        self._put_text(frame, line2, (10, 50), scale=0.50, color=(180, 220, 255))
        if whatif_label:
            self._put_text(frame, whatif_label, (10, 75), scale=0.50, color=(100, 255, 100))

        faults = self._current_frame_faults()
        significant = [f for f in faults if f.is_significant]
        if significant:
            fault_text = ", ".join(f.fault_type for f in significant[:3])
            self._put_text(frame, fault_text, (10, 100), scale=0.50, color=(80, 80, 255))

    def _draw_scrubber(self, frame: np.ndarray) -> None:
        height, width = frame.shape[:2]
        bar_y = height - 20
        bar_height = 8
        margin = 20

        cv2.rectangle(
            frame, (margin, bar_y), (width - margin, bar_y + bar_height),
            (60, 60, 60), -1
        )

        if self._num_frames > 1:
            progress = self._frame_idx / (self._num_frames - 1)
            cursor_x = int(margin + progress * (width - 2 * margin))
            cv2.rectangle(
                frame, (margin, bar_y), (cursor_x, bar_y + bar_height),
                (100, 200, 100), -1
            )

        for bottom_frame in self._rep_bottom_frames:
            rep_progress = bottom_frame / max(self._num_frames - 1, 1)
            rep_x = int(margin + rep_progress * (width - 2 * margin))
            cv2.line(frame, (rep_x, bar_y - 2), (rep_x, bar_y + bar_height + 2), (80, 180, 255), 1)

    @staticmethod
    def _put_text(
        frame: np.ndarray,
        text: str,
        position: tuple[int, int],
        scale: float = 0.5,
        color: tuple[int, int, int] = (220, 220, 220),
    ) -> None:
        cv2.putText(
            frame, text, position,
            cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA,
        )
        cv2.putText(
            frame, text, position,
            cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA,
        )

    # ------------------------------------------------------------------
    # Terminal output
    # ------------------------------------------------------------------

    def _current_rep_number(self) -> int | None:
        for rep in self._reps:
            if rep.start_frame <= self._frame_idx <= rep.end_frame:
                return rep.rep_number
        return None

    def _current_frame_faults(self) -> list[FaultEvent]:
        if self._frame_idx < len(self._pipeline_frames):
            return self._pipeline_frames[self._frame_idx].faults
        return []

    def _print_frame_detail(self) -> None:
        q_vector = self._q_trajectory[self._frame_idx]
        angles = q_to_joint_angles(
            self._skeleton, q_vector, frame_index=self._frame_idx
        )

        print(f"\n{'=' * 50}")
        print(f"Frame {self._frame_idx + 1}/{self._num_frames}")
        print(f"{'=' * 50}")
        print(
            f"Hip flexion:     L={angles.hip_flexion_l:6.1f} deg"
            f"  R={angles.hip_flexion_r:6.1f} deg"
        )
        print(
            f"Knee flexion:    L={angles.knee_flexion_l:6.1f} deg"
            f"  R={angles.knee_flexion_r:6.1f} deg"
        )
        print(
            f"Ankle DF:        L={angles.ankle_dorsiflexion_l:6.1f} deg"
            f"  R={angles.ankle_dorsiflexion_r:6.1f} deg"
        )
        print(f"Trunk flexion:   {angles.trunk_flexion:6.1f} deg")
        if angles.knee_valgus_l is not None:
            print(
                f"Knee valgus:     L={angles.knee_valgus_l:6.1f} deg"
                f"  R={angles.knee_valgus_r:6.1f} deg"
            )
        if angles.stance_width_ratio is not None:
            print(f"Stance width:    {angles.stance_width_ratio:6.2f}x hip width")
        print(f"{'=' * 50}\n")

    def _print_controls(self) -> None:
        print("\n=== V2 Squat Viewer (MuJoCo) ===")
        print(f"Trajectory: {self._num_frames} frames, {len(self._reps)} reps")
        print()
        print("  SPACE     Play / Pause")
        print("  A / D     Step frame back / forward")
        print("  W / S     Speed up / down")
        print("  [ / ]     Prev / Next rep")
        print("  R         Reset to start")
        print("  I         Print joint angles")
        print("  C         Cycle camera (side / front / 3/4)")
        if self._whatif_solver:
            print("  1         Toggle: +5 deg dorsiflexion")
            print("  2         Toggle: +5cm stance width")
            print("  3         Toggle: +5 deg toe-out")
            print("  T         Toggle what-if on/off")
        print("  Q / ESC   Quit")
        print("=" * 34 + "\n")


def generate_synthetic_trajectory(
    skeleton: MujocoSkeleton,
    num_reps: int = 2,
    frames_per_rep: int = 60,
    standing_frames: int = 30,
) -> np.ndarray:
    """Generate a synthetic standing-squat-standing trajectory.

    Returns (T, N_DOF) q-trajectory in radians.
    """
    total_frames = standing_frames + num_reps * frames_per_rep + standing_frames
    q_trajectory = np.zeros((total_frames, skeleton.n_dof()))

    scale_factor = skeleton.height_m / 1.75
    standing_pelvis_height = 0.95 * scale_factor

    pelvis_tz_idx = skeleton.get_joint_index("pelvis", "tz")
    trunk_rx_idx = skeleton.get_joint_index("trunk", "rx")
    l_hip_rx_idx = skeleton.get_joint_index("L_hip", "rx")
    r_hip_rx_idx = skeleton.get_joint_index("R_hip", "rx")
    l_knee_rx_idx = skeleton.get_joint_index("L_knee", "rx")
    r_knee_rx_idx = skeleton.get_joint_index("R_knee", "rx")
    l_ankle_rx_idx = skeleton.get_joint_index("L_ankle", "rx")
    r_ankle_rx_idx = skeleton.get_joint_index("R_ankle", "rx")
    l_shoulder_rx_idx = skeleton.get_joint_index("L_shoulder", "rx")
    r_shoulder_rx_idx = skeleton.get_joint_index("R_shoulder", "rx")
    l_elbow_rx_idx = skeleton.get_joint_index("L_elbow", "rx")
    r_elbow_rx_idx = skeleton.get_joint_index("R_elbow", "rx")

    for frame_idx in range(total_frames):
        q_vector = np.zeros(skeleton.n_dof())
        q_vector[pelvis_tz_idx] = standing_pelvis_height

        if frame_idx < standing_frames:
            depth = 0.0
        elif frame_idx >= total_frames - standing_frames:
            depth = 0.0
        else:
            rep_frame = frame_idx - standing_frames
            phase_within_rep = (rep_frame % frames_per_rep) / frames_per_rep
            depth = math.sin(phase_within_rep * math.pi)

        hip_flexion = math.radians(100.0 * depth)
        knee_flexion = math.radians(130.0 * depth)
        ankle_dorsiflexion = math.radians(25.0 * depth)
        trunk_lean = math.radians(20.0 * depth)

        pelvis_drop = 0.40 * scale_factor * depth
        q_vector[pelvis_tz_idx] -= pelvis_drop
        q_vector[trunk_rx_idx] = trunk_lean
        q_vector[l_hip_rx_idx] = hip_flexion
        q_vector[r_hip_rx_idx] = hip_flexion
        q_vector[l_knee_rx_idx] = knee_flexion
        q_vector[r_knee_rx_idx] = knee_flexion
        q_vector[l_ankle_rx_idx] = ankle_dorsiflexion
        q_vector[r_ankle_rx_idx] = ankle_dorsiflexion

        shoulder_flexion = math.radians(50.0 * depth)
        elbow_flexion = math.radians(20.0 * depth)
        q_vector[l_shoulder_rx_idx] = shoulder_flexion
        q_vector[r_shoulder_rx_idx] = shoulder_flexion
        q_vector[l_elbow_rx_idx] = elbow_flexion
        q_vector[r_elbow_rx_idx] = elbow_flexion

        q_trajectory[frame_idx] = q_vector

    return q_trajectory

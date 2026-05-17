"""Generate synthetic squat fixtures by running FK on known joint angle trajectories."""

from __future__ import annotations

import json
import numpy as np
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from biomechanics.skeleton.definition import SkeletonModel
from biomechanics.skeleton.anthropometry import scale_skeleton
from biomechanics.skeleton.forward_kin import forward_kinematics


def _make_clean_squat_q(skeleton: SkeletonModel, n_frames: int = 60) -> np.ndarray:
    """A biomechanically good squat: balanced bar path, knees tracking toes, good depth."""
    q_traj = np.zeros((n_frames, skeleton.n_dof))
    q_neutral = skeleton.neutral_q()

    for t in range(n_frames):
        phase = _squat_phase(t, n_frames)
        q = q_neutral.copy()

        # Symmetric hip flexion
        hip_flex = np.radians(100.0 * phase)
        for side in ("L", "R"):
            q[skeleton.dof_index(f"{side}_hip", "rx")] = hip_flex

        # Knee flexion
        knee_flex = np.radians(120.0 * phase)
        for side in ("L", "R"):
            q[skeleton.dof_index(f"{side}_knee", "rx")] = knee_flex

        # Ankle dorsiflexion
        dorsi = np.radians(30.0 * phase)
        for side in ("L", "R"):
            q[skeleton.dof_index(f"{side}_ankle", "rx")] = dorsi

        # Trunk forward lean to keep balance
        trunk_flex = np.radians(40.0 * phase)
        q[skeleton.dof_index("trunk", "rx")] = trunk_flex

        # Pelvis drops with depth (approximate from geometry)
        q[1] = q_neutral[1] - 0.35 * phase

        q_traj[t] = q

    return q_traj


def _make_bad_squat_q(skeleton: SkeletonModel, n_frames: int = 60) -> np.ndarray:
    """Deliberate faults: forward lean, knee valgus, limited dorsiflexion."""
    q_traj = np.zeros((n_frames, skeleton.n_dof))
    q_neutral = skeleton.neutral_q()

    for t in range(n_frames):
        phase = _squat_phase(t, n_frames)
        q = q_neutral.copy()

        hip_flex = np.radians(95.0 * phase)
        for side in ("L", "R"):
            q[skeleton.dof_index(f"{side}_hip", "rx")] = hip_flex

        knee_flex = np.radians(110.0 * phase)
        for side in ("L", "R"):
            q[skeleton.dof_index(f"{side}_knee", "rx")] = knee_flex

        # Limited dorsiflexion (only 15 degrees)
        dorsi = np.radians(15.0 * phase)
        for side in ("L", "R"):
            q[skeleton.dof_index(f"{side}_ankle", "rx")] = dorsi

        # Excessive forward lean
        trunk_flex = np.radians(55.0 * phase)
        q[skeleton.dof_index("trunk", "rx")] = trunk_flex

        # Knee valgus: hips internally rotated
        valgus = np.radians(-12.0 * phase)
        q[skeleton.dof_index("L_hip", "rz")] = valgus
        q[skeleton.dof_index("R_hip", "rz")] = -valgus

        q[1] = q_neutral[1] - 0.30 * phase

        q_traj[t] = q

    return q_traj


def _squat_phase(t: int, n_frames: int) -> float:
    """Smooth descent-bottom-ascent profile. Returns 0 at standing, 1 at bottom."""
    # Bottom at frame n_frames // 2
    center = n_frames / 2.0
    sigma = n_frames / 4.0
    return np.exp(-((t - center) / sigma) ** 2)


def generate_landmarks_from_q(
    skeleton: SkeletonModel,
    q_traj: np.ndarray,
    noise_std: float = 0.0,
) -> np.ndarray:
    """Run FK on each frame to produce synthetic 'landmark' positions.

    Returns (T, n_joints, 4) array with [x, y, z, visibility].
    """
    T, _ = q_traj.shape
    n_joints = skeleton.n_joints
    landmarks = np.zeros((T, n_joints, 4))

    for t in range(T):
        xforms = forward_kinematics(skeleton, q_traj[t])
        for i, jdef in enumerate(skeleton.joints):
            pos = xforms[jdef.name][:3, 3]
            if noise_std > 0:
                pos = pos + np.random.normal(0, noise_std, 3)
            landmarks[t, i, :3] = pos
            landmarks[t, i, 3] = 1.0  # full visibility

    return landmarks


def generate_fixtures(output_dir: Path | None = None):
    """Write synth_clean_squat.json and synth_bad_squat.json."""
    skeleton = scale_skeleton(1.78, 80.0)

    if output_dir is None:
        output_dir = Path(__file__).parent / "fixtures"
    output_dir.mkdir(exist_ok=True)

    for name, gen_fn in [("synth_clean_squat", _make_clean_squat_q),
                          ("synth_bad_squat", _make_bad_squat_q)]:
        q_traj = gen_fn(skeleton, n_frames=60)
        landmarks = generate_landmarks_from_q(skeleton, q_traj)

        data = {
            "q_trajectory": q_traj.tolist(),
            "landmarks": landmarks.tolist(),
            "fps": 30.0,
            "height_m": 1.78,
            "weight_kg": 80.0,
            "n_frames": 60,
        }

        path = output_dir / f"{name}.json"
        with open(path, "w") as f:
            json.dump(data, f)


if __name__ == "__main__":
    generate_fixtures()

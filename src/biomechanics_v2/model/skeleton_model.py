"""MuJoCo skeleton model wrapper — the core physics object for biomechanics V2."""

from __future__ import annotations

import math
from typing import Optional

import mujoco
import numpy as np

from .anthropometry import (
    build_mjcf_xml,
    scale_mjcf_from_proportions,
    HINGE_JOINTS,
    PELVIS_JOINTS,
)

# Ordered DOF names matching the V1 q-vector layout (20 DOF total)
# q[0:5]   = pelvis (tx, ty, tz, rx, ry, rz)
# q[6:7]   = trunk (rx, rz)
# q[8:10]  = L_hip (rx, ry, rz)
# q[11:13] = R_hip (rx, ry, rz)
# q[14]    = L_knee (rx)
# q[15]    = R_knee (rx)
# q[16:17] = L_ankle (rx, ry)
# q[18:19] = R_ankle (rx, ry)
DOF_ORDER = [
    ("pelvis", "tx"), ("pelvis", "ty"), ("pelvis", "tz"),
    ("pelvis", "rx"), ("pelvis", "ry"), ("pelvis", "rz"),
    ("trunk", "rx"), ("trunk", "rz"),
    ("L_hip", "rx"), ("L_hip", "ry"), ("L_hip", "rz"),
    ("R_hip", "rx"), ("R_hip", "ry"), ("R_hip", "rz"),
    ("L_knee", "rx"),
    ("R_knee", "rx"),
    ("L_ankle", "rx"), ("L_ankle", "ry"),
    ("R_ankle", "rx"), ("R_ankle", "ry"),
    ("L_shoulder", "rx"), ("L_shoulder", "rz"), ("L_shoulder", "ry"),
    ("R_shoulder", "rx"), ("R_shoulder", "rz"), ("R_shoulder", "ry"),
    ("L_elbow", "rx"),
    ("R_elbow", "rx"),
]

N_DOF = len(DOF_ORDER)

# Map from (joint_name, axis) to MuJoCo joint name in the XML
_AXIS_TO_LETTER = {
    "1 0 0": "x", "-1 0 0": "x",
    "0 1 0": "y", "0 -1 0": "y",
    "0 0 1": "z", "0 0 -1": "z",
}

_MUJOCO_JOINT_NAMES = {}
for joint_name, joint_type, axis, low, high in PELVIS_JOINTS:
    body = "pelvis"
    axis_letter = _AXIS_TO_LETTER[axis]
    if joint_type == "slide":
        _MUJOCO_JOINT_NAMES[(body, f"t{axis_letter}")] = joint_name
    else:
        _MUJOCO_JOINT_NAMES[(body, f"r{axis_letter}")] = joint_name

for body_name, joints in HINGE_JOINTS.items():
    for mj_joint_name, axis, low, high in joints:
        axis_letter = _AXIS_TO_LETTER[axis]
        _MUJOCO_JOINT_NAMES[(body_name, f"r{axis_letter}")] = mj_joint_name

# Joint bounds in degrees (matching V1 definition.py)
_BOUNDS_DEG = {
    ("pelvis", "tx"): (-float("inf"), float("inf")),
    ("pelvis", "ty"): (-float("inf"), float("inf")),
    ("pelvis", "tz"): (-float("inf"), float("inf")),
    ("pelvis", "rx"): (-45.0, 45.0),
    ("pelvis", "ry"): (-25.0, 25.0),
    ("pelvis", "rz"): (-15.0, 15.0),
    ("trunk", "rx"): (-30.0, 60.0),
    ("trunk", "rz"): (-25.0, 25.0),
    ("L_hip", "rx"): (-15.0, 130.0),
    ("L_hip", "ry"): (-30.0, 45.0),
    ("L_hip", "rz"): (-30.0, 40.0),
    ("L_knee", "rx"): (0.0, 150.0),
    ("L_ankle", "rx"): (-30.0, 40.0),
    ("L_ankle", "ry"): (-20.0, 20.0),
    ("R_hip", "rx"): (-15.0, 130.0),
    ("R_hip", "ry"): (-45.0, 30.0),
    ("R_hip", "rz"): (-40.0, 30.0),
    ("R_knee", "rx"): (0.0, 150.0),
    ("R_ankle", "rx"): (-30.0, 40.0),
    ("R_ankle", "ry"): (-20.0, 20.0),
    ("L_shoulder", "rx"): (-45.0, 180.0),
    ("L_shoulder", "rz"): (-20.0, 180.0),
    ("L_shoulder", "ry"): (-90.0, 90.0),
    ("R_shoulder", "rx"): (-45.0, 180.0),
    ("R_shoulder", "rz"): (-180.0, 20.0),
    ("R_shoulder", "ry"): (-90.0, 90.0),
    ("L_elbow", "rx"): (0.0, 150.0),
    ("R_elbow", "rx"): (0.0, 150.0),
}


class MujocoSkeleton:
    """MuJoCo-based skeleton model for squat biomechanics.

    Wraps a compiled MuJoCo model with the same 20-DOF layout as V1's SkeletonModel.
    """

    def __init__(self, height_m: float = 1.75, weight_kg: float = 75.0):
        self._height_m = height_m
        self._weight_kg = weight_kg
        self._xml = build_mjcf_xml(
            height_m=height_m,
            weight_kg=weight_kg,
            include_mocap_bodies=True,
            include_floor=True,
        )
        self._model = mujoco.MjModel.from_xml_string(self._xml)
        self._data = mujoco.MjData(self._model)

        # Build mapping from our N-DOF index to MuJoCo's qpos index
        self._dof_to_qpos_idx = np.zeros(N_DOF, dtype=np.intp)
        for i, (body_name, axis) in enumerate(DOF_ORDER):
            mj_joint_name = _MUJOCO_JOINT_NAMES[(body_name, axis)]
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, mj_joint_name)
            qpos_adr = self._model.jnt_qposadr[joint_id]
            self._dof_to_qpos_idx[i] = qpos_adr

        # Body name to MuJoCo body id mapping
        self._body_names = [
            "pelvis", "trunk", "head",
            "L_hip", "R_hip", "L_knee", "R_knee",
            "L_ankle", "R_ankle", "L_toe", "R_toe",
            "L_shoulder", "R_shoulder",
            "L_elbow", "R_elbow",
            "L_wrist", "R_wrist",
        ]
        self._body_ids = {}
        for name in self._body_names:
            self._body_ids[name] = mujoco.mj_name2id(
                self._model, mujoco.mjtObj.mjOBJ_BODY, name
            )

    @property
    def model(self) -> mujoco.MjModel:
        return self._model

    @property
    def data(self) -> mujoco.MjData:
        return self._data

    @property
    def height_m(self) -> float:
        return self._height_m

    @property
    def weight_kg(self) -> float:
        return self._weight_kg

    def n_dof(self) -> int:
        return N_DOF

    def set_qpos(self, q: np.ndarray) -> None:
        """Set joint positions from q-vector (radians/meters)."""
        for i in range(N_DOF):
            self._data.qpos[self._dof_to_qpos_idx[i]] = q[i]

    def get_qpos(self) -> np.ndarray:
        """Get q-vector (radians/meters)."""
        q = np.zeros(N_DOF)
        for i in range(N_DOF):
            q[i] = self._data.qpos[self._dof_to_qpos_idx[i]]
        return q

    def forward(self) -> None:
        """Run mj_forward — compute FK + dynamics quantities."""
        mujoco.mj_forward(self._model, self._data)

    def get_body_positions(self) -> dict[str, np.ndarray]:
        """Joint name -> (3,) world position after forward()."""
        positions = {}
        for name in self._body_names:
            body_id = self._body_ids[name]
            positions[name] = self._data.xpos[body_id].copy()
        return positions

    def get_body_com(self) -> np.ndarray:
        """Mass-weighted center of mass (3,). Uses MuJoCo's built-in subtree COM."""
        # subtree_com[0] is the world body's COM = total system COM
        return self._data.subtree_com[0].copy()

    def get_joint_index(self, joint_name: str, axis: str) -> int:
        """Map 'L_hip', 'rx' -> index into our 20-DOF q-vector."""
        target = (joint_name, axis)
        for i, dof in enumerate(DOF_ORDER):
            if dof == target:
                return i
        raise KeyError(f"No DOF found for ({joint_name}, {axis})")

    def get_bounds(self) -> list[tuple[float, float]]:
        """Per-DOF bounds in radians (or meters for translation), same order as q-vector."""
        bounds = []
        for body_name, axis in DOF_ORDER:
            low_deg, high_deg = _BOUNDS_DEG[(body_name, axis)]
            if axis.startswith("t"):
                bounds.append((low_deg, high_deg))
            else:
                bounds.append((math.radians(low_deg), math.radians(high_deg)))
        return bounds

    def scale_from_proportions(self, proportions) -> None:
        """Re-scale model using calibrated BodyProportions. Recompiles model."""
        self._xml = scale_mjcf_from_proportions(
            self._xml, proportions, self._weight_kg
        )
        self._model = mujoco.MjModel.from_xml_string(self._xml)
        self._data = mujoco.MjData(self._model)

        # Rebuild qpos mapping (joint ids may have changed after recompile)
        for i, (body_name, axis) in enumerate(DOF_ORDER):
            mj_joint_name = _MUJOCO_JOINT_NAMES[(body_name, axis)]
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, mj_joint_name)
            self._dof_to_qpos_idx[i] = self._model.jnt_qposadr[joint_id]

        for name in self._body_names:
            self._body_ids[name] = mujoco.mj_name2id(
                self._model, mujoco.mjtObj.mjOBJ_BODY, name
            )

    def to_xml(self) -> str:
        """Export current model as MJCF XML string."""
        return self._xml

    def neutral_q(self) -> np.ndarray:
        """Neutral pose: pelvis at default height, all rotations zero."""
        q = np.zeros(N_DOF)
        scale_factor = self._height_m / 1.75
        q[0] = 0.0   # tx
        q[1] = 0.0   # ty
        q[2] = 0.95 * scale_factor  # tz (pelvis height, Z-up)
        return q

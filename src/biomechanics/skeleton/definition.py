"""20-DOF articulated skeleton for squat biomechanics."""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field


@dataclass(frozen=True)
class JointDef:
    name: str
    parent: str | None
    offset: tuple[float, float, float]
    dof_axes: tuple[str, ...]
    limits: tuple[tuple[float, float], ...]


JOINT_DEFS_20DOF: tuple[JointDef, ...] = (
    JointDef("pelvis", None, (0.0, 0.95, 0.0),
             ("tx", "ty", "tz", "rx", "ry", "rz"),
             ((-np.inf, np.inf), (-np.inf, np.inf), (-np.inf, np.inf),
              (-45.0, 45.0), (-25.0, 25.0), (-15.0, 15.0))),
    JointDef("trunk", "pelvis", (0.0, 0.28, 0.0),
             ("rx", "rz"),
             ((-30.0, 60.0), (-25.0, 25.0))),
    JointDef("L_hip", "pelvis", (-0.10, 0.0, 0.0),
             ("rx", "ry", "rz"),
             ((-15.0, 130.0), (-30.0, 45.0), (-30.0, 40.0))),
    JointDef("R_hip", "pelvis", (0.10, 0.0, 0.0),
             ("rx", "ry", "rz"),
             ((-15.0, 130.0), (-45.0, 30.0), (-40.0, 30.0))),
    JointDef("L_knee", "L_hip", (0.0, 0.0, -0.45),
             ("rx",),
             ((0.0, 150.0),)),
    JointDef("R_knee", "R_hip", (0.0, 0.0, -0.45),
             ("rx",),
             ((0.0, 150.0),)),
    JointDef("L_ankle", "L_knee", (0.0, 0.0, 0.43),
             ("rx", "ry"),
             ((-30.0, 40.0), (-20.0, 20.0))),
    JointDef("R_ankle", "R_knee", (0.0, 0.0, 0.43),
             ("rx", "ry"),
             ((-30.0, 40.0), (-20.0, 20.0))),
    JointDef("head", "trunk", (0.0, 0.40, 0.0),
             (), ()),
    JointDef("L_toe", "L_ankle", (0.0, -0.20, 0.0),
             (), ()),
    JointDef("R_toe", "R_ankle", (0.0, -0.20, 0.0),
             (), ()),
)


class SkeletonModel:
    def __init__(self, joint_defs: tuple[JointDef, ...] = JOINT_DEFS_20DOF):
        self.joints = joint_defs
        self._name_to_idx: dict[str, int] = {}
        self._dof_map: dict[tuple[str, str], int] = {}
        self._joint_dof_slices: dict[str, slice] = {}
        self._parent_indices: np.ndarray
        self._offsets: np.ndarray

        dof_cursor = 0
        for i, jd in enumerate(joint_defs):
            self._name_to_idx[jd.name] = i
            start = dof_cursor
            for axis in jd.dof_axes:
                self._dof_map[(jd.name, axis)] = dof_cursor
                dof_cursor += 1
            self._joint_dof_slices[jd.name] = slice(start, dof_cursor)

        self._n_dof = dof_cursor

        self._parent_indices = np.full(len(joint_defs), -1, dtype=np.intp)
        self._offsets = np.zeros((len(joint_defs), 3))
        for i, jd in enumerate(joint_defs):
            if jd.parent is not None:
                self._parent_indices[i] = self._name_to_idx[jd.parent]
            self._offsets[i] = jd.offset

        self._joint_masses: np.ndarray | None = None

    @property
    def n_dof(self) -> int:
        return self._n_dof

    @property
    def n_joints(self) -> int:
        return len(self.joints)

    @property
    def joint_names(self) -> list[str]:
        return [j.name for j in self.joints]

    def dof_index(self, joint_name: str, axis: str) -> int:
        return self._dof_map[(joint_name, axis)]

    def joint_dofs(self, joint_name: str) -> slice:
        return self._joint_dof_slices[joint_name]

    def joint_index(self, joint_name: str) -> int:
        return self._name_to_idx[joint_name]

    def parent_index(self, joint_idx: int) -> int:
        return int(self._parent_indices[joint_idx])

    def offset(self, joint_idx: int) -> np.ndarray:
        return self._offsets[joint_idx]

    def bounds(self) -> list[tuple[float, float]]:
        result = []
        for jd in self.joints:
            for (lo, hi), axis in zip(jd.limits, jd.dof_axes):
                if axis.startswith("t"):
                    result.append((lo, hi))
                else:
                    result.append((np.radians(lo), np.radians(hi)))
        return result

    def neutral_q(self) -> np.ndarray:
        """T-pose with pelvis at default offset, all rotations zero."""
        q = np.zeros(self._n_dof)
        pelvis_def = self.joints[0]
        q[0] = pelvis_def.offset[0]
        q[1] = pelvis_def.offset[1]
        q[2] = pelvis_def.offset[2]
        return q

    def dof_axes_for_joint(self, joint_name: str) -> tuple[str, ...]:
        idx = self._name_to_idx[joint_name]
        return self.joints[idx].dof_axes

    def scale_offsets(self, factor: float) -> None:
        """Scale all bone offsets in-place (for anthropometric scaling)."""
        self._offsets *= factor
        for i, jd in enumerate(self.joints):
            object.__setattr__(
                jd, "offset",
                (self._offsets[i, 0], self._offsets[i, 1], self._offsets[i, 2]),
            )

    def set_offset(self, joint_name: str, offset: tuple[float, float, float]) -> None:
        """Set an individual joint's offset in-place."""
        idx = self._name_to_idx[joint_name]
        self._offsets[idx] = offset
        object.__setattr__(self.joints[idx], "offset", offset)

    def set_joint_masses(self, masses: dict[str, float]) -> None:
        self._joint_masses = np.zeros(self.n_joints)
        for name, mass in masses.items():
            if name in self._name_to_idx:
                self._joint_masses[self._name_to_idx[name]] = mass

    @property
    def joint_masses(self) -> np.ndarray | None:
        return self._joint_masses

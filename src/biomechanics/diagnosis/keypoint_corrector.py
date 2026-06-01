"""Geometric keypoint corrections for diagnosed squat faults.

Applies tier-1 (cue-correctable) fixes using the same delta-FK approach
as the viewer's bottomUpBuild / deformLowerBody JS functions. Stance width
and toe-out changes propagate identically to the sandbox sliders.

Joint indices (COCO 19-keypoint):
    0=nose, 1=L_eye, 2=R_eye, 3=L_ear, 4=R_ear,
    5=L_shoulder, 6=R_shoulder, 7=L_elbow, 8=R_elbow,
    9=L_wrist, 10=R_wrist, 11=L_hip, 12=R_hip,
    13=L_knee, 14=R_knee, 15=L_ankle, 16=R_ankle,
    17=L_foot_index, 18=R_foot_index
"""

from __future__ import annotations

import math

import numpy as np

from .types import DiagnosisResult

UPPER_BODY_INDICES = list(range(0, 11))
HIP_L, HIP_R = 11, 12
KNEE_L, KNEE_R = 13, 14
ANKLE_L, ANKLE_R = 15, 16
FOOT_L, FOOT_R = 17, 18


def solve_knee(
    hip: np.ndarray,
    ankle: np.ndarray,
    thigh_length: float,
    shin_length: float,
    ref_knee: np.ndarray,
) -> np.ndarray:
    """2-link IK: place knee so |hip-knee|==thigh and |knee-ankle|==shin."""
    ha_vec = ankle - hip
    distance = np.linalg.norm(ha_vec)
    if distance < 1e-9:
        distance = 1e-9
    unit_ha = ha_vec / distance

    distance_min = abs(thigh_length - shin_length) + 1e-4
    distance_max = thigh_length + shin_length - 1e-4
    distance_clamped = max(distance_min, min(distance_max, distance))

    cos_angle = (thigh_length**2 + distance_clamped**2 - shin_length**2) / (
        2.0 * thigh_length * distance_clamped
    )
    cos_angle = max(-1.0, min(1.0, cos_angle))
    sin_angle = math.sin(math.acos(cos_angle))

    pole = ref_knee - hip
    dot_proj = np.dot(pole, unit_ha)
    pole = pole - dot_proj * unit_ha
    pole_length = np.linalg.norm(pole)

    if pole_length < 1e-6:
        pole = np.array([-unit_ha[0] * unit_ha[1],
                         1.0 - unit_ha[1]**2,
                         -unit_ha[2] * unit_ha[1]])
        pole_length = np.linalg.norm(pole)
        if pole_length < 1e-9:
            pole_length = 1e-9
    pole = pole / pole_length

    return hip + thigh_length * cos_angle * unit_ha + thigh_length * sin_angle * pole


def rotate_y(vec: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate a 3D vector about the Y axis."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return np.array([
        cos_a * vec[0] + sin_a * vec[2],
        vec[1],
        -sin_a * vec[0] + cos_a * vec[2],
    ])


def rotate_about_axis(vec: np.ndarray, axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rodrigues rotation of vec about an arbitrary axis."""
    axis_len = np.linalg.norm(axis)
    if axis_len < 1e-9:
        return vec.copy()
    k = axis / axis_len
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    cross = np.cross(k, vec)
    dot = np.dot(k, vec)
    return vec * cos_a + cross * sin_a + k * dot * (1.0 - cos_a)


def bottom_up_build(
    captured: np.ndarray,
    stance_width: float,
    baseline_stance_width: float,
    toe_out_delta_rad: float,
    dorsi_delta_rad: float,
    knee_flex_delta_rad: float,
) -> np.ndarray | None:
    """Python port of the viewer's bottomUpBuild JS function.

    Rebuilds lower body (11-18) bottom-up from grounded feet using captured
    bone vectors, overriding stance / toe-out / dorsiflexion. Hips fall out
    of leg geometry (rigid pelvis reconciled by averaging).

    Returns (19, 3) array or None if degenerate.
    """
    for idx in [HIP_L, HIP_R, KNEE_L, KNEE_R, ANKLE_L, ANKLE_R]:
        if np.all(captured[idx] == 0):
            return None

    out = captured.copy()

    hip_l = captured[HIP_L]
    hip_r = captured[HIP_R]
    lat_vec = np.array([hip_r[0] - hip_l[0], 0.0, hip_r[2] - hip_l[2]])
    lat_len = np.linalg.norm(lat_vec)
    if lat_len < 1e-9:
        lat_len = 1e-9
    lat_u = lat_vec / lat_len

    ank_l = captured[ANKLE_L]
    ank_r = captured[ANKLE_R]
    ank_mid = np.array([(ank_l[0] + ank_r[0]) / 2.0, 0.0, (ank_l[2] + ank_r[2]) / 2.0])
    span_vec = np.array([ank_r[0] - ank_l[0], 0.0, ank_r[2] - ank_l[2]])
    span_len = np.linalg.norm(span_vec)
    if span_len < 1e-9:
        span_len = 1e-9
    span_u = span_vec / span_len

    span_scale = stance_width / max(baseline_stance_width, 1e-9)

    sides = [
        {"a_idx": ANKLE_L, "k_idx": KNEE_L, "h_idx": HIP_L, "t_idx": FOOT_L, "sign": -1.0},
        {"a_idx": ANKLE_R, "k_idx": KNEE_R, "h_idx": HIP_R, "t_idx": FOOT_R, "sign": 1.0},
    ]

    hip_estimates = []
    for side in sides:
        a_idx = side["a_idx"]
        k_idx = side["k_idx"]
        h_idx = side["h_idx"]
        t_idx = side["t_idx"]
        sign = side["sign"]

        a0 = captured[a_idx]
        k0 = captured[k_idx]
        h0 = captured[h_idx]

        # 1. New grounded ankle: scale lateral span about ankle midpoint
        half_dist = (span_len / 2.0) * span_scale * sign
        new_ankle = np.array([
            ank_mid[0] + span_u[0] * half_dist,
            a0[1],
            ank_mid[2] + span_u[2] * half_dist,
        ])

        # 2-3. Shin = captured (knee-ankle), yawed by toe-out, tilted by dorsi
        shin = k0 - a0
        shin = rotate_y(shin, sign * toe_out_delta_rad)
        shin = rotate_about_axis(shin, lat_u, dorsi_delta_rad)
        new_knee = new_ankle + shin

        # 4. Thigh = captured (hip-knee), yawed with the leg
        thigh = h0 - k0
        thigh = rotate_y(thigh, sign * toe_out_delta_rad)
        if abs(knee_flex_delta_rad) > 1e-9:
            thigh = rotate_about_axis(thigh, lat_u, knee_flex_delta_rad)
        hip_estimates.append(new_knee + thigh)

        out[a_idx] = new_ankle
        out[k_idx] = new_knee

        # Foot vector yawed with the leg
        t0 = captured[t_idx]
        foot_vec = t0 - a0
        foot_vec = rotate_y(foot_vec, sign * toe_out_delta_rad)
        out[t_idx] = new_ankle + foot_vec

    # 5. Rigid pelvis reconciliation: hip-mid = avg estimate, keep captured half-vector
    hip_mid = (hip_estimates[0] + hip_estimates[1]) / 2.0
    half_vec = (hip_r - hip_l) / 2.0
    out[HIP_L] = hip_mid - half_vec
    out[HIP_R] = hip_mid + half_vec

    # 6. Re-ground guard
    min_ankle_y = min(out[ANKLE_L][1], out[ANKLE_R][1])
    if min_ankle_y < 0:
        for idx in range(HIP_L, FOOT_R + 1):
            out[idx][1] -= min_ankle_y

    return out


class KeypointCorrector:
    """Applies geometric corrections to 19 keypoints based on diagnosis."""

    def correct(
        self,
        observed_kpts: list[list[float]],
        diagnosis: DiagnosisResult,
        anthro: dict | None = None,
        rom: dict | None = None,
    ) -> list[list[float]] | None:
        """Apply tier-1 corrections. Returns corrected kpts or None if no fixes needed."""
        tier1_causes = {
            cause.cause_id: cause
            for cause in diagnosis.immediate_causes
        }

        if not tier1_causes:
            return None

        kpts = np.array(observed_kpts, dtype=float)

        original_thigh_l = np.linalg.norm(kpts[KNEE_L] - kpts[HIP_L])
        original_shin_l = np.linalg.norm(kpts[ANKLE_L] - kpts[KNEE_L])
        original_thigh_r = np.linalg.norm(kpts[KNEE_R] - kpts[HIP_R])
        original_shin_r = np.linalg.norm(kpts[ANKLE_R] - kpts[KNEE_R])

        # Stance width + toe-out via delta-FK (same as sandbox sliders)
        has_stance = "narrow_stance" in tier1_causes
        has_toe_out = "narrow_foot_angle" in tier1_causes
        if has_stance or has_toe_out:
            self._apply_stance_toe_out_delta_fk(kpts, tier1_causes)

        if "depth_cue_unfamiliar" in tier1_causes:
            self._lower_to_depth(
                kpts, tier1_causes["depth_cue_unfamiliar"],
                original_thigh_l, original_shin_l,
                original_thigh_r, original_shin_r,
            )

        if "knee_track_cue" in tier1_causes:
            self._push_knees_out(kpts, tier1_causes["knee_track_cue"])

        if "weight_shift_cue" in tier1_causes:
            self._center_weight(kpts, tier1_causes["weight_shift_cue"])

        if "bracing_failure" in tier1_causes:
            self._reduce_trunk_lean(kpts, tier1_causes["bracing_failure"])

        self._enforce_bone_lengths(
            kpts, original_thigh_l, original_shin_l,
            original_thigh_r, original_shin_r,
        )

        max_dorsi_deg = rom.get("dorsiflexion_drop") if rom else None
        if max_dorsi_deg is not None:
            self._enforce_dorsi_cap(
                kpts, max_dorsi_deg,
                original_thigh_l, original_shin_l,
                original_thigh_r, original_shin_r,
            )

        self._reground(kpts)

        return kpts.tolist()

    def _apply_stance_toe_out_delta_fk(
        self, kpts: np.ndarray, tier1_causes: dict
    ) -> None:
        """Apply stance width + toe-out via delta-FK matching sandbox sliders."""
        captured = kpts.copy()

        # Compute baseline stance width from captured ankle span
        ank_l = captured[ANKLE_L]
        ank_r = captured[ANKLE_R]
        span_dx = ank_r[0] - ank_l[0]
        span_dz = ank_r[2] - ank_l[2]
        baseline_stance = math.sqrt(span_dx**2 + span_dz**2)
        if baseline_stance < 1e-6:
            baseline_stance = 1e-6

        # Target stance width from foot_target_delta
        stance_delta = 0.0
        if "narrow_stance" in tier1_causes:
            delta = tier1_causes["narrow_stance"].parameter_delta or {}
            foot_delta = delta.get("__foot_target_delta")
            if foot_delta:
                # Z shifts: left goes negative, right goes positive
                stance_delta = foot_delta[5] - foot_delta[2]
        target_stance = baseline_stance + stance_delta

        # Toe-out delta from narrow_foot_angle
        toe_out_delta_rad = 0.0
        if "narrow_foot_angle" in tier1_causes:
            delta = tier1_causes["narrow_foot_angle"].parameter_delta or {}
            # L_ankle.ry is positive (external rotation left), use it as the per-side delta
            toe_out_delta_rad = delta.get("L_ankle.ry", 0.0)

        # Delta-FK: build base (identity) and mod (with corrections)
        base = bottom_up_build(captured, baseline_stance, baseline_stance, 0.0, 0.0, 0.0)
        mod = bottom_up_build(captured, target_stance, baseline_stance, toe_out_delta_rad, 0.0, 0.0)

        if base is None or mod is None:
            return

        # Apply delta to lower body (indices 11-18)
        for idx in range(HIP_L, FOOT_R + 1):
            delta_vec = mod[idx] - base[idx]
            kpts[idx] += delta_vec

        # Re-solve knees to preserve captured bone lengths
        thigh_l = np.linalg.norm(captured[KNEE_L] - captured[HIP_L])
        shin_l = np.linalg.norm(captured[ANKLE_L] - captured[KNEE_L])
        thigh_r = np.linalg.norm(captured[KNEE_R] - captured[HIP_R])
        shin_r = np.linalg.norm(captured[ANKLE_R] - captured[KNEE_R])

        kpts[KNEE_L] = solve_knee(
            kpts[HIP_L], kpts[ANKLE_L], thigh_l, shin_l, kpts[KNEE_L],
        )
        kpts[KNEE_R] = solve_knee(
            kpts[HIP_R], kpts[ANKLE_R], thigh_r, shin_r, kpts[KNEE_R],
        )

        # Upper body rides rigidly with the pelvis shift
        cap_hip_mid = (captured[HIP_L] + captured[HIP_R]) / 2.0
        new_hip_mid = (kpts[HIP_L] + kpts[HIP_R]) / 2.0
        pelvis_shift = new_hip_mid - cap_hip_mid

        for idx in UPPER_BODY_INDICES:
            kpts[idx] += pelvis_shift

    def _push_knees_out(self, kpts: np.ndarray, cause) -> None:
        """Nudge knees laterally along the hip-lateral axis."""
        delta = cause.parameter_delta or {}
        delta_l_rad = abs(delta.get("L_hip.ry", 0.0))
        delta_r_rad = abs(delta.get("R_hip.ry", 0.0))

        hip_lateral = kpts[HIP_R] - kpts[HIP_L]
        hip_lateral[1] = 0.0
        hip_lat_norm = np.linalg.norm(hip_lateral)
        if hip_lat_norm < 1e-6:
            return
        hip_lateral_unit = hip_lateral / hip_lat_norm

        thigh_l = np.linalg.norm(kpts[KNEE_L] - kpts[HIP_L])
        nudge_l = thigh_l * math.sin(delta_l_rad)
        kpts[KNEE_L] -= hip_lateral_unit * nudge_l

        thigh_r = np.linalg.norm(kpts[KNEE_R] - kpts[HIP_R])
        nudge_r = thigh_r * math.sin(delta_r_rad)
        kpts[KNEE_R] += hip_lateral_unit * nudge_r

    def _center_weight(self, kpts: np.ndarray, cause) -> None:
        """Shift pelvis + upper body laterally."""
        delta = cause.parameter_delta or {}
        shift_x = delta.get("pelvis.tx", 0.0)
        if abs(shift_x) < 1e-6:
            return

        shift_vec = np.array([0.0, 0.0, shift_x])

        for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
            kpts[idx] += shift_vec

    def _reduce_trunk_lean(self, kpts: np.ndarray, cause) -> None:
        """Rotate upper body about hip midpoint in the sagittal plane."""
        delta = cause.parameter_delta or {}
        lean_delta_rad = delta.get("trunk.rx", 0.0)
        if abs(lean_delta_rad) < 1e-6:
            return

        hip_mid = (kpts[HIP_L] + kpts[HIP_R]) / 2.0
        shoulder_mid = (kpts[5] + kpts[6]) / 2.0

        trunk_dx = shoulder_mid[0] - hip_mid[0]
        trunk_dy = shoulder_mid[1] - hip_mid[1]
        torso_length = math.sqrt(trunk_dx**2 + trunk_dy**2)
        if torso_length < 1e-6:
            return

        current_lean = math.atan2(trunk_dx, trunk_dy)
        new_lean = current_lean + lean_delta_rad

        new_shoulder_mid_x = hip_mid[0] + torso_length * math.sin(new_lean)
        new_shoulder_mid_y = hip_mid[1] + torso_length * math.cos(new_lean)

        offset_x = new_shoulder_mid_x - shoulder_mid[0]
        offset_y = new_shoulder_mid_y - shoulder_mid[1]

        for idx in UPPER_BODY_INDICES:
            kpts[idx][0] += offset_x
            kpts[idx][1] += offset_y

    def _lower_to_depth(
        self,
        kpts: np.ndarray,
        cause,
        thigh_length_l: float,
        shin_length_l: float,
        thigh_length_r: float,
        shin_length_r: float,
    ) -> None:
        """Lower hips to parallel (hip_y <= knee_y)."""
        delta = cause.parameter_delta or {}
        if delta.get("depth_target") != "parallel":
            return

        for _iteration in range(5):
            hip_mid_y = (kpts[HIP_L][1] + kpts[HIP_R][1]) / 2.0
            knee_mid_y = (kpts[KNEE_L][1] + kpts[KNEE_R][1]) / 2.0

            if hip_mid_y <= knee_mid_y:
                break

            drop = hip_mid_y - knee_mid_y + 0.01

            for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
                kpts[idx][1] -= drop

            kpts[KNEE_L] = solve_knee(
                kpts[HIP_L], kpts[ANKLE_L],
                thigh_length_l, shin_length_l, kpts[KNEE_L],
            )
            kpts[KNEE_R] = solve_knee(
                kpts[HIP_R], kpts[ANKLE_R],
                thigh_length_r, shin_length_r, kpts[KNEE_R],
            )

        min_ankle_y = min(kpts[ANKLE_L][1], kpts[ANKLE_R][1])
        hip_floor = min_ankle_y + 0.05
        for hip_idx in [HIP_L, HIP_R]:
            if kpts[hip_idx][1] < hip_floor:
                overshoot = hip_floor - kpts[hip_idx][1]
                for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
                    kpts[idx][1] += overshoot
                break

    @staticmethod
    def _compute_dorsiflexion(knee: np.ndarray, ankle: np.ndarray) -> float:
        """Shin angle from vertical in radians. 0 = perfectly vertical."""
        shin_vec = ankle - knee
        shin_vertical = -shin_vec[1]
        shin_horizontal = math.sqrt(shin_vec[0] ** 2 + shin_vec[2] ** 2)
        return math.atan2(shin_horizontal, max(shin_vertical, 1e-9))

    def _enforce_dorsi_cap(
        self,
        kpts: np.ndarray,
        max_dorsi_deg: float,
        thigh_l: float,
        shin_l: float,
        thigh_r: float,
        shin_r: float,
    ) -> None:
        """Raise hips if corrected dorsiflexion exceeds athlete's calibrated max."""
        max_dorsi_rad = math.radians(max_dorsi_deg)
        for _iteration in range(5):
            max_excess = 0.0
            for knee_idx, ankle_idx in [
                (KNEE_L, ANKLE_L),
                (KNEE_R, ANKLE_R),
            ]:
                dorsi_rad = self._compute_dorsiflexion(kpts[knee_idx], kpts[ankle_idx])
                excess = dorsi_rad - max_dorsi_rad
                if excess > max_excess:
                    max_excess = excess

            if max_excess < 0.001:
                break

            raise_amount = max_excess * 0.3
            for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
                kpts[idx][1] += raise_amount

            kpts[KNEE_L] = solve_knee(
                kpts[HIP_L], kpts[ANKLE_L], thigh_l, shin_l, kpts[KNEE_L],
            )
            kpts[KNEE_R] = solve_knee(
                kpts[HIP_R], kpts[ANKLE_R], thigh_r, shin_r, kpts[KNEE_R],
            )

    def _enforce_bone_lengths(
        self,
        kpts: np.ndarray,
        thigh_l: float,
        shin_l: float,
        thigh_r: float,
        shin_r: float,
    ) -> None:
        """Re-solve knees to maintain original bone lengths."""
        kpts[KNEE_L] = solve_knee(
            kpts[HIP_L], kpts[ANKLE_L], thigh_l, shin_l, kpts[KNEE_L],
        )
        kpts[KNEE_R] = solve_knee(
            kpts[HIP_R], kpts[ANKLE_R], thigh_r, shin_r, kpts[KNEE_R],
        )

    def _reground(self, kpts: np.ndarray) -> None:
        """Ensure ankles don't go below ground (Y=0 in viewer coords)."""
        min_ankle_y = min(kpts[ANKLE_L][1], kpts[ANKLE_R][1])
        if min_ankle_y < 0:
            for idx in range(HIP_L, FOOT_R + 1):
                kpts[idx][1] -= min_ankle_y


def build_morph_frames(
    observed_kpts: list[list[float]],
    corrected_kpts: list[list[float]],
    num_frames: int = 60,
) -> list[list[list[float]]]:
    """Generate morph frames using Gaussian-tapered interpolation."""
    observed = np.array(observed_kpts)
    corrected = np.array(corrected_kpts)

    sigma = num_frames / 5.0
    mid = num_frames / 2.0

    frames = []
    for frame_index in range(num_frames):
        weight = math.exp(-((frame_index - mid) ** 2) / (2.0 * sigma**2))
        interpolated = observed + weight * (corrected - observed)
        frames.append(interpolated.tolist())

    return frames

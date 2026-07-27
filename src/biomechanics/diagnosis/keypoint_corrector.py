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

SEGMENT_MASS_FRAC = {
    "head": 0.081,
    "trunk": 0.497,
    "upper_arm_l": 0.028, "upper_arm_r": 0.028,
    "forearm_l": 0.022, "forearm_r": 0.022,
    "thigh_l": 0.100, "thigh_r": 0.100,
    "shank_l": 0.047, "shank_r": 0.047,
    "foot_l": 0.014, "foot_r": 0.014,
}

SEGMENT_JOINTS: dict[str, tuple[int, int]] = {
    "upper_arm_l": (5, 7), "upper_arm_r": (6, 8),
    "forearm_l": (7, 9), "forearm_r": (8, 10),
    "thigh_l": (HIP_L, KNEE_L), "thigh_r": (HIP_R, KNEE_R),
    "shank_l": (KNEE_L, ANKLE_L), "shank_r": (KNEE_R, ANKLE_R),
}

BALANCE_FRAC = 0.35
HEEL_OFFSET_M = 0.06
BALANCE_TARGET_EPS_M = 0.002
BALANCE_LEAN_MAX_DEG = 30.0
DEFAULT_FOOT_LEN_M = 0.2937
_TOTAL_MASS_FRAC = sum(SEGMENT_MASS_FRAC.values())


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


def _mirror_vec(vec: np.ndarray, lat_unit: np.ndarray) -> np.ndarray:
    return vec - 2.0 * np.dot(vec, lat_unit) * lat_unit


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

    # 7. Project feet to ground plane
    out[FOOT_L][1] = 0.0
    out[FOOT_R][1] = 0.0

    return out


def build_segment_coms(kpts: np.ndarray, foot_len: float) -> dict[str, np.ndarray]:
    """Per-segment center-of-mass positions from 19-keypoint skeleton."""
    shoulder_mid = (kpts[5] + kpts[6]) / 2.0
    hip_mid = (kpts[HIP_L] + kpts[HIP_R]) / 2.0

    coms: dict[str, np.ndarray] = {
        "head": kpts[0].copy(),
        "trunk": (shoulder_mid + hip_mid) / 2.0,
    }

    for seg_name, (j_a, j_b) in SEGMENT_JOINTS.items():
        coms[seg_name] = (kpts[j_a] + kpts[j_b]) / 2.0

    along = BALANCE_FRAC * foot_len - HEEL_OFFSET_M
    for ankle_idx, knee_idx, name in [
        (ANKLE_L, KNEE_L, "foot_l"),
        (ANKLE_R, KNEE_R, "foot_r"),
    ]:
        ankle = kpts[ankle_idx]
        knee = kpts[knee_idx]
        dx = knee[0] - ankle[0]
        dz = knee[2] - ankle[2]
        leg_len_xz = math.sqrt(dx * dx + dz * dz) or 1.0
        coms[name] = np.array([
            ankle[0] + dx / leg_len_xz * along,
            ankle[1],
            ankle[2] + dz / leg_len_xz * along,
        ])

    return coms


def compute_com_ground(kpts: np.ndarray, foot_len: float) -> np.ndarray:
    """Whole-body COM projected onto the ground plane. Returns [x, z]."""
    coms = build_segment_coms(kpts, foot_len)
    cx, cz = 0.0, 0.0
    for seg_name, frac in SEGMENT_MASS_FRAC.items():
        seg_com = coms.get(seg_name)
        if seg_com is None:
            continue
        norm_frac = frac / _TOTAL_MASS_FRAC
        cx += seg_com[0] * norm_frac
        cz += seg_com[2] * norm_frac
    return np.array([cx, cz])


def compute_balance_target_ground(kpts: np.ndarray, foot_len: float) -> np.ndarray:
    """Mid-foot balance target on the ground plane. Returns [x, z]."""
    along = BALANCE_FRAC * foot_len - HEEL_OFFSET_M
    targets: list[np.ndarray] = []
    for ankle_idx, foot_idx, knee_idx in [
        (ANKLE_L, FOOT_L, KNEE_L),
        (ANKLE_R, FOOT_R, KNEE_R),
    ]:
        ankle = kpts[ankle_idx]
        foot = kpts[foot_idx]
        fx = foot[0] - ankle[0]
        fz = foot[2] - ankle[2]
        fl = math.sqrt(fx * fx + fz * fz)
        if fl < 1e-6:
            knee = kpts[knee_idx]
            fx = knee[0] - ankle[0]
            fz = knee[2] - ankle[2]
            fl = math.sqrt(fx * fx + fz * fz)
            if fl < 1e-6:
                continue
        fx /= fl
        fz /= fl
        targets.append(np.array([ankle[0] + fx * along, ankle[2] + fz * along]))

    if not targets:
        return np.array([0.0, 0.0])
    return sum(targets) / len(targets)


def apply_lean_to_upper_body(kpts: np.ndarray, lean_delta_rad: float) -> np.ndarray:
    """Apply lean with 2-segment spine: 60% lower trunk, 40% upper trunk."""
    out = kpts.copy()
    hip_mid_x = (kpts[HIP_L][0] + kpts[HIP_R][0]) / 2.0
    hip_mid_y = (kpts[HIP_L][1] + kpts[HIP_R][1]) / 2.0

    lower_lean = lean_delta_rad * 0.6
    upper_lean = lean_delta_rad * 0.4

    cos_lo = math.cos(lower_lean)
    sin_lo = math.sin(lower_lean)
    for idx in UPPER_BODY_INDICES:
        dx = kpts[idx][0] - hip_mid_x
        dy = kpts[idx][1] - hip_mid_y
        out[idx][0] = hip_mid_x + cos_lo * dx + sin_lo * dy
        out[idx][1] = hip_mid_y - sin_lo * dx + cos_lo * dy

    sh_mid_x = (out[5][0] + out[6][0]) / 2.0
    sh_mid_y = (out[5][1] + out[6][1]) / 2.0
    cos_up = math.cos(upper_lean)
    sin_up = math.sin(upper_lean)
    for idx in range(5):
        dx = out[idx][0] - sh_mid_x
        dy = out[idx][1] - sh_mid_y
        out[idx][0] = sh_mid_x + cos_up * dx + sin_up * dy
        out[idx][1] = sh_mid_y - sin_up * dx + cos_up * dy

    return out


def solve_balance_lean(kpts: np.ndarray, foot_len: float) -> float | None:
    """Newton-Raphson solver: find trunk lean that puts COM over mid-foot target.

    Matches the sandbox's solveBalanceLeanOffsetDeg — damped Newton with
    numerical sensitivity, projected onto the sagittal axis derived from
    the hip lateral vector.  Returns lean offset in radians, or None on failure.
    """
    hip_lateral = kpts[HIP_R] - kpts[HIP_L]
    hip_lat_xz = np.array([hip_lateral[0], hip_lateral[2]])
    hip_lat_len = np.linalg.norm(hip_lat_xz)
    if hip_lat_len < 1e-9:
        return None

    sagittal_dir = np.array([-hip_lat_xz[1] / hip_lat_len, hip_lat_xz[0] / hip_lat_len])

    lean = 0.0
    num_diff_eps = 1e-5
    hard_max = math.radians(BALANCE_LEAN_MAX_DEG + 10.0)

    for _ in range(16):
        posed = apply_lean_to_upper_body(kpts, lean)
        com = compute_com_ground(posed, foot_len)
        target = compute_balance_target_ground(posed, foot_len)

        gap = target - com
        gap_sagittal = float(np.dot(gap, sagittal_dir))

        if abs(gap_sagittal) <= BALANCE_TARGET_EPS_M:
            break

        posed_plus = apply_lean_to_upper_body(kpts, lean + num_diff_eps)
        com_plus = compute_com_ground(posed_plus, foot_len)
        sens_sagittal = float(np.dot(com_plus - com, sagittal_dir)) / num_diff_eps

        if abs(sens_sagittal) < 1e-9:
            return None

        step = gap_sagittal / sens_sagittal
        step = max(-0.3, min(0.3, step))
        lean += 0.8 * step
        lean = max(-hard_max, min(hard_max, lean))

    if not math.isfinite(lean):
        return None
    max_rad = math.radians(BALANCE_LEAN_MAX_DEG)
    lean = max(-max_rad, min(max_rad, lean))

    return lean


class KeypointCorrector:
    """Applies geometric corrections to 19 keypoints based on diagnosis."""

    def canonicalize(
        self,
        observed_kpts: list[list[float]],
        rom: dict | None = None,
    ) -> list[list[float]]:
        """Symmetrized canonical form of an observed pose.

        Bone lengths must be captured from THIS pose, not the raw observation:
        symmetry averages L/R bone vectors and therefore changes their lengths,
        so it has to run before the lengths are locked. Every correction step
        downstream of canonicalization preserves the canonical lengths exactly.
        """
        kpts = np.array(observed_kpts, dtype=float)
        max_dorsi_deg = rom.get("dorsiflexion_drop") if rom else None
        self._enforce_symmetry(kpts, max_dorsi_deg=max_dorsi_deg)
        return kpts.tolist()

    def correct(
        self,
        observed_kpts: list[list[float]],
        diagnosis: DiagnosisResult,
        anthro: dict | None = None,
        rom: dict | None = None,
        bone_lengths: tuple[float, float, float, float] | None = None,
    ) -> list[list[float]] | None:
        """Apply tier-1 corrections. Returns corrected kpts or None if no fixes needed.

        Pipeline order (length-safety invariant): the pose is canonicalized
        (symmetrized) FIRST, bone lengths are captured from the canonical pose,
        and no length-changing pass runs afterwards — every subsequent step
        either moves joints rigidly or re-solves knees via IK with the captured
        lengths. If `bone_lengths` is provided it must describe the canonical
        pose (see `canonicalize`).
        """
        tier1_causes = {
            cause.cause_id: cause
            for cause in diagnosis.immediate_causes
        }

        if not tier1_causes:
            return None

        max_dorsi_deg = rom.get("dorsiflexion_drop") if rom else None

        # 1. Canonicalize BEFORE capturing bone lengths. Idempotent, so
        # passing an already-canonical pose (demo_builder) is a no-op.
        kpts = np.array(observed_kpts, dtype=float)
        self._enforce_symmetry(kpts, max_dorsi_deg=max_dorsi_deg)

        # 2. Lock bone lengths — the invariant for everything below.
        if bone_lengths is not None:
            original_thigh_l, original_shin_l, original_thigh_r, original_shin_r = bone_lengths
        else:
            original_thigh_l = np.linalg.norm(kpts[KNEE_L] - kpts[HIP_L])
            original_shin_l = np.linalg.norm(kpts[ANKLE_L] - kpts[KNEE_L])
            original_thigh_r = np.linalg.norm(kpts[KNEE_R] - kpts[HIP_R])
            original_shin_r = np.linalg.norm(kpts[ANKLE_R] - kpts[KNEE_R])

        # 3. Cue corrections, all length-preserving from here on.
        has_stance = "narrow_stance" in tier1_causes
        has_toe_out = "narrow_foot_angle" in tier1_causes
        if has_stance or has_toe_out:
            pre_hip_mid = (kpts[HIP_L] + kpts[HIP_R]).copy() / 2.0
            self._apply_stance_toe_out_delta_fk(kpts, tier1_causes)
            stance_pelvis_shift = (kpts[HIP_L] + kpts[HIP_R]) / 2.0 - pre_hip_mid
        else:
            stance_pelvis_shift = None

        if "knee_track_cue" in tier1_causes:
            self._push_knees_out(kpts, tier1_causes["knee_track_cue"])

        self._enforce_bone_lengths(
            kpts, original_thigh_l, original_shin_l,
            original_thigh_r, original_shin_r,
        )

        if max_dorsi_deg is not None:
            self._enforce_dorsi_cap(
                kpts, max_dorsi_deg,
                original_thigh_l, original_shin_l,
                original_thigh_r, original_shin_r,
            )

        self._reground(kpts)

        # 4. Depth last among the leg corrections; nothing after this
        # touches hip height, so parallel depth survives to the output.
        if "depth_cue_unfamiliar" in tier1_causes:
            self._achieve_depth_within_dorsi_budget(
                kpts, tier1_causes["depth_cue_unfamiliar"],
                max_dorsi_deg,
                original_thigh_l, original_shin_l,
                original_thigh_r, original_shin_r,
            )

        foot_len = anthro.get("foot_length", DEFAULT_FOOT_LEN_M) if anthro else DEFAULT_FOOT_LEN_M

        # Torso follows the pelvis shift from the stance/toe-out FK before
        # any COM computation sees the pose.
        if stance_pelvis_shift is not None:
            for idx in UPPER_BODY_INDICES:
                kpts[idx] += stance_pelvis_shift

        if "weight_shift_cue" in tier1_causes:
            self._center_com_laterally(
                kpts, foot_len,
                original_thigh_l, original_shin_l,
                original_thigh_r, original_shin_r,
            )

        self._solve_and_apply_balance(kpts, foot_len)

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

    def _center_com_laterally(
        self,
        kpts: np.ndarray,
        foot_len: float,
        thigh_l: float,
        shin_l: float,
        thigh_r: float,
        shin_r: float,
    ) -> float:
        """Translate pelvis + upper body along the hip-lateral axis until the
        COM ground projection sits on the mid-foot balance target.

        Ankles and feet stay planted; knees are re-solved via IK each step.
        Iterates because leg-segment COMs only partially follow the pelvis.
        Returns the total applied lateral shift in meters (signed along the
        L->R hip axis).
        """
        total_shift = 0.0
        for _ in range(4):
            hip_lateral = kpts[HIP_R] - kpts[HIP_L]
            hip_lateral[1] = 0.0
            lat_len = np.linalg.norm(hip_lateral)
            if lat_len < 1e-9:
                break
            lat_unit = hip_lateral / lat_len
            lat_unit_xz = np.array([lat_unit[0], lat_unit[2]])

            com = compute_com_ground(kpts, foot_len)
            target = compute_balance_target_ground(kpts, foot_len)
            gap_lateral = float(np.dot(target - com, lat_unit_xz))
            if abs(gap_lateral) <= BALANCE_TARGET_EPS_M:
                break

            for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
                kpts[idx] += lat_unit * gap_lateral
            total_shift += gap_lateral

            kpts[KNEE_L] = solve_knee(
                kpts[HIP_L], kpts[ANKLE_L], thigh_l, shin_l, kpts[KNEE_L],
            )
            kpts[KNEE_R] = solve_knee(
                kpts[HIP_R], kpts[ANKLE_R], thigh_r, shin_r, kpts[KNEE_R],
            )
        return total_shift

    def _solve_and_apply_balance(self, kpts: np.ndarray, foot_len: float) -> None:
        """Apply sagittal balance with a 2-segment spine model.

        Distributes the total lean between a lower trunk rotation (hips to
        shoulders, 60%) and an upper trunk rotation (shoulders to head, 40%).
        This produces a natural C-curve rather than a rigid board tipping.
        """
        lean_rad = solve_balance_lean(kpts, foot_len)
        if lean_rad is None or abs(lean_rad) < 1e-6:
            return

        LOWER_FRAC = 0.6
        UPPER_FRAC = 1.0 - LOWER_FRAC
        lower_lean = lean_rad * LOWER_FRAC
        upper_lean = lean_rad * UPPER_FRAC

        hip_mid_x = (kpts[HIP_L][0] + kpts[HIP_R][0]) / 2.0
        hip_mid_y = (kpts[HIP_L][1] + kpts[HIP_R][1]) / 2.0

        # Lower trunk rotation: rotate all upper body indices about hip mid
        cos_lo = math.cos(lower_lean)
        sin_lo = math.sin(lower_lean)
        for idx in UPPER_BODY_INDICES:
            dx = kpts[idx][0] - hip_mid_x
            dy = kpts[idx][1] - hip_mid_y
            kpts[idx][0] = hip_mid_x + cos_lo * dx + sin_lo * dy
            kpts[idx][1] = hip_mid_y - sin_lo * dx + cos_lo * dy

        # Upper trunk rotation: rotate head/ears/eyes about shoulder mid
        # Shoulders are indices 5, 6; head group is 0-4
        sh_mid_x = (kpts[5][0] + kpts[6][0]) / 2.0
        sh_mid_y = (kpts[5][1] + kpts[6][1]) / 2.0
        cos_up = math.cos(upper_lean)
        sin_up = math.sin(upper_lean)
        for idx in range(5):
            dx = kpts[idx][0] - sh_mid_x
            dy = kpts[idx][1] - sh_mid_y
            kpts[idx][0] = sh_mid_x + cos_up * dx + sin_up * dy
            kpts[idx][1] = sh_mid_y - sin_up * dx + cos_up * dy

    def _lower_to_depth(
        self,
        kpts: np.ndarray,
        cause,
        thigh_length_l: float,
        shin_length_l: float,
        thigh_length_r: float,
        shin_length_r: float,
    ) -> None:
        """Lower hips to parallel (hip_y == knee_y).

        Knees are already planted by stance/toe-out. Drop hips + upper body
        so hip_mid_y == knee_mid_y, then re-solve knee angles via IK.
        """
        delta = cause.parameter_delta or {}
        if delta.get("depth_target") != "parallel":
            return

        hip_mid_y = (kpts[HIP_L][1] + kpts[HIP_R][1]) / 2.0
        knee_mid_y = (kpts[KNEE_L][1] + kpts[KNEE_R][1]) / 2.0

        if hip_mid_y <= knee_mid_y:
            return

        drop = hip_mid_y - knee_mid_y

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

    def _achieve_depth_within_dorsi_budget(
        self,
        kpts: np.ndarray,
        cause,
        max_dorsi_deg: float | None,
        thigh_l: float,
        shin_l: float,
        thigh_r: float,
        shin_r: float,
    ) -> None:
        """Lower to parallel, widening stance and toe-out if dorsi ROM is insufficient.

        When lowering to parallel would push shin dorsiflexion beyond the
        athlete's calibrated ROM, iteratively widens stance and increases
        toe-out (via delta-FK) until parallel is achievable within the
        dorsiflexion budget.
        """
        delta = cause.parameter_delta or {}
        if delta.get("depth_target") != "parallel":
            return

        hip_mid_y = (kpts[HIP_L][1] + kpts[HIP_R][1]) / 2.0
        knee_mid_y = (kpts[KNEE_L][1] + kpts[KNEE_R][1]) / 2.0
        if hip_mid_y <= knee_mid_y:
            return

        if max_dorsi_deg is None:
            self._lower_to_depth(kpts, cause, thigh_l, shin_l, thigh_r, shin_r)
            return

        max_dorsi_rad = math.radians(max_dorsi_deg)
        captured = kpts.copy()

        span_dx = captured[ANKLE_R][0] - captured[ANKLE_L][0]
        span_dz = captured[ANKLE_R][2] - captured[ANKLE_L][2]
        baseline_span = math.sqrt(span_dx**2 + span_dz**2)
        if baseline_span < 1e-6:
            self._lower_to_depth(kpts, cause, thigh_l, shin_l, thigh_r, shin_r)
            return

        stance_step = 0.015
        toe_out_step_rad = math.radians(1.5)
        max_stance_increase = 0.12
        max_toe_out_increase_rad = math.radians(15.0)
        dorsi_tol_rad = math.radians(0.5)
        depth_tol_m = 0.003

        stance_extra = 0.0
        toe_out_extra = 0.0
        best = None

        for _ in range(20):
            trial = captured.copy()

            if stance_extra > 1e-6 or toe_out_extra > 1e-6:
                target_span = baseline_span + 2.0 * stance_extra
                base = bottom_up_build(
                    captured, baseline_span, baseline_span, 0.0, 0.0, 0.0,
                )
                mod = bottom_up_build(
                    captured, target_span, baseline_span,
                    toe_out_extra, 0.0, 0.0,
                )
                if base is None or mod is None:
                    break
                for idx in range(HIP_L, FOOT_R + 1):
                    trial[idx] = captured[idx] + (mod[idx] - base[idx])
                old_hip_mid = (captured[HIP_L] + captured[HIP_R]) / 2.0
                new_hip_mid = (trial[HIP_L] + trial[HIP_R]) / 2.0
                for idx in UPPER_BODY_INDICES:
                    trial[idx] += new_hip_mid - old_hip_mid
                trial[KNEE_L] = solve_knee(
                    trial[HIP_L], trial[ANKLE_L], thigh_l, shin_l, trial[KNEE_L],
                )
                trial[KNEE_R] = solve_knee(
                    trial[HIP_R], trial[ANKLE_R], thigh_r, shin_r, trial[KNEE_R],
                )

            min_ank_y = min(trial[ANKLE_L][1], trial[ANKLE_R][1])
            if min_ank_y < 0:
                trial[:, 1] -= min_ank_y

            for _ in range(8):
                hy = (trial[HIP_L][1] + trial[HIP_R][1]) / 2.0
                ky = (trial[KNEE_L][1] + trial[KNEE_R][1]) / 2.0
                if hy <= ky + depth_tol_m:
                    break
                drop = hy - ky
                for idx in UPPER_BODY_INDICES + [HIP_L, HIP_R]:
                    trial[idx][1] -= drop
                trial[KNEE_L] = solve_knee(
                    trial[HIP_L], trial[ANKLE_L], thigh_l, shin_l, trial[KNEE_L],
                )
                trial[KNEE_R] = solve_knee(
                    trial[HIP_R], trial[ANKLE_R], thigh_r, shin_r, trial[KNEE_R],
                )

            worst_dorsi = 0.0
            for ki, ai in [(KNEE_L, ANKLE_L), (KNEE_R, ANKLE_R)]:
                shin_vec = trial[ai] - trial[ki]
                vert = -shin_vec[1]
                horiz = math.sqrt(shin_vec[0] ** 2 + shin_vec[2] ** 2)
                worst_dorsi = max(
                    worst_dorsi, math.atan2(horiz, max(vert, 1e-9)),
                )

            best = trial

            if worst_dorsi <= max_dorsi_rad + dorsi_tol_rad:
                break

            stance_extra = min(stance_extra + stance_step, max_stance_increase)
            toe_out_extra = min(
                toe_out_extra + toe_out_step_rad, max_toe_out_increase_rad,
            )
            if (stance_extra >= max_stance_increase
                    and toe_out_extra >= max_toe_out_increase_rad):
                break

        if best is not None:
            kpts[:] = best

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
        """Ensure ankles don't go below ground and feet sit on ground plane."""
        min_ankle_y = min(kpts[ANKLE_L][1], kpts[ANKLE_R][1])
        if min_ankle_y < 0:
            kpts[:, 1] -= min_ankle_y
        kpts[FOOT_L][1] = 0.0
        kpts[FOOT_R][1] = 0.0

    def _enforce_symmetry(
        self,
        kpts: np.ndarray,
        max_dorsi_deg: float | None = None,
    ) -> None:
        """Enforce bilateral symmetry via FK rebuild with averaged bone vectors."""
        hip_lateral = kpts[HIP_R] - kpts[HIP_L]
        hip_lateral[1] = 0.0
        lat_len = np.linalg.norm(hip_lateral)
        if lat_len < 1e-9:
            return
        lat_unit = hip_lateral / lat_len

        # Symmetrize ankles and feet: mirror lateral, average Y
        for l_idx, r_idx in [(ANKLE_L, ANKLE_R), (FOOT_L, FOOT_R)]:
            mid = (kpts[l_idx] + kpts[r_idx]) / 2.0
            half_vec = (kpts[r_idx] - kpts[l_idx]) / 2.0
            lateral_component = abs(np.dot(half_vec, lat_unit))
            lateral_half = lat_unit * lateral_component
            y_avg = mid[1]
            kpts[l_idx] = mid - lateral_half
            kpts[l_idx][1] = y_avg
            kpts[r_idx] = mid + lateral_half
            kpts[r_idx][1] = y_avg

        # Average bone vectors (mirror R to L orientation before averaging)
        shin_l = kpts[KNEE_L] - kpts[ANKLE_L]
        shin_r = kpts[KNEE_R] - kpts[ANKLE_R]
        shin_avg = (shin_l + _mirror_vec(shin_r, lat_unit)) / 2.0

        thigh_l = kpts[HIP_L] - kpts[KNEE_L]
        thigh_r = kpts[HIP_R] - kpts[KNEE_R]
        thigh_avg = (thigh_l + _mirror_vec(thigh_r, lat_unit)) / 2.0

        foot_l = kpts[FOOT_L] - kpts[ANKLE_L]
        foot_r = kpts[FOOT_R] - kpts[ANKLE_R]
        foot_avg = (foot_l + _mirror_vec(foot_r, lat_unit)) / 2.0

        # Cap dorsiflexion on the averaged shin before rebuild
        # shin_avg points upward (knee - ankle), so Y is positive when vertical
        if max_dorsi_deg is not None:
            max_dorsi_rad = math.radians(max_dorsi_deg)
            shin_vert = shin_avg[1]
            shin_horiz = math.sqrt(shin_avg[0] ** 2 + shin_avg[2] ** 2)
            dorsi_rad = math.atan2(shin_horiz, max(shin_vert, 1e-9))
            if dorsi_rad > max_dorsi_rad:
                excess = dorsi_rad - max_dorsi_rad
                tilt_axis = np.cross(shin_avg, np.array([0.0, 1.0, 0.0]))
                if np.linalg.norm(tilt_axis) > 1e-9:
                    shin_avg = rotate_about_axis(shin_avg, tilt_axis, excess)

        # Build synthetic captured skeleton with averaged vectors
        old_hip_mid = (kpts[HIP_L] + kpts[HIP_R]) / 2.0

        synthetic = kpts.copy()
        synthetic[ANKLE_L] = kpts[ANKLE_L].copy()
        synthetic[ANKLE_R] = kpts[ANKLE_R].copy()
        synthetic[FOOT_L] = kpts[ANKLE_L] + foot_avg
        synthetic[FOOT_R] = kpts[ANKLE_R] + _mirror_vec(foot_avg, lat_unit)
        synthetic[KNEE_L] = kpts[ANKLE_L] + shin_avg
        synthetic[KNEE_R] = kpts[ANKLE_R] + _mirror_vec(shin_avg, lat_unit)
        synthetic[HIP_L] = synthetic[KNEE_L] + thigh_avg
        synthetic[HIP_R] = synthetic[KNEE_R] + _mirror_vec(thigh_avg, lat_unit)

        # FK rebuild with identity parameters
        span_dx = kpts[ANKLE_R][0] - kpts[ANKLE_L][0]
        span_dz = kpts[ANKLE_R][2] - kpts[ANKLE_L][2]
        ankle_span = math.sqrt(span_dx ** 2 + span_dz ** 2)
        if ankle_span < 1e-9:
            ankle_span = 1e-9

        result = bottom_up_build(
            synthetic, ankle_span, ankle_span, 0.0, 0.0, 0.0,
        )
        if result is None:
            return

        # Apply rebuilt lower body and shift upper body with pelvis
        new_hip_mid = (result[HIP_L] + result[HIP_R]) / 2.0
        pelvis_shift = new_hip_mid - old_hip_mid

        for idx in range(HIP_L, FOOT_R + 1):
            kpts[idx] = result[idx]

        for idx in UPPER_BODY_INDICES:
            kpts[idx] += pelvis_shift

        # Reground and project feet to ground plane
        min_ankle_y = min(kpts[ANKLE_L][1], kpts[ANKLE_R][1])
        if min_ankle_y < 0:
            kpts[:, 1] -= min_ankle_y
        kpts[FOOT_L][1] = 0.0
        kpts[FOOT_R][1] = 0.0


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

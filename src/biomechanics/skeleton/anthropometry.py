"""Anthropometric scaling using de Leva (1996) segment mass fractions."""

from __future__ import annotations

from .definition import JointDef, SkeletonModel, JOINT_DEFS_20DOF

REFERENCE_HEIGHT_M = 1.75

SEGMENT_MASS_FRACTIONS: dict[str, float] = {
    "pelvis": 0.142,
    "trunk": 0.295,       # lumbar (0.139) + thorax (0.156) combined
    "head": 0.067,
    "L_thigh": 0.123,
    "R_thigh": 0.123,
    "L_shank": 0.048,
    "R_shank": 0.048,
    "L_foot": 0.012,
    "R_foot": 0.012,
    "L_upper_arm": 0.027,
    "R_upper_arm": 0.027,
    "L_forearm_hand": 0.022,
    "R_forearm_hand": 0.022,
    "L_hand": 0.006,
    "R_hand": 0.006,
    "neck": 0.020,
}

# Fraction of segment length from proximal end to COM (de Leva 1996, male)
SEGMENT_COM_PROXIMAL_FRACTION: dict[str, float] = {
    "pelvis": 0.5,
    "trunk": 0.45,
    "head": 0.50,
    "L_thigh": 0.41,
    "R_thigh": 0.41,
    "L_shank": 0.44,
    "R_shank": 0.44,
    "L_foot": 0.44,
    "R_foot": 0.44,
    "L_upper_arm": 0.44,
    "R_upper_arm": 0.44,
    "L_forearm_hand": 0.47,
    "R_forearm_hand": 0.47,
}

# Map segment names to (parent_joint, child_joint) for COM computation
SEGMENT_TO_JOINTS: dict[str, tuple[str, str]] = {
    "pelvis": ("pelvis", "trunk"),
    "trunk": ("trunk", "trunk"),    # COM offset handled specially
    "L_thigh": ("L_hip", "L_knee"),
    "R_thigh": ("R_hip", "R_knee"),
    "L_shank": ("L_knee", "L_ankle"),
    "R_shank": ("R_knee", "R_ankle"),
}


def scale_skeleton(
    height_m: float,
    weight_kg: float,
    joint_defs: tuple = JOINT_DEFS_20DOF,
) -> SkeletonModel:
    copied = tuple(
        JointDef(jd.name, jd.parent, jd.offset, jd.dof_axes, jd.limits)
        for jd in joint_defs
    )
    skeleton = SkeletonModel(copied)
    scale_factor = height_m / REFERENCE_HEIGHT_M
    skeleton.scale_offsets(scale_factor)

    _set_segment_masses(skeleton, weight_kg)
    skeleton._total_weight_kg = weight_kg
    skeleton._height_m = height_m
    skeleton._scale_factor = scale_factor
    return skeleton


def calibrate_skeleton(
    landmarks: "np.ndarray",
    weight_kg: float,
    vis_threshold: float = 0.5,
    joint_defs: tuple = JOINT_DEFS_20DOF,
) -> SkeletonModel:
    """Build a skeleton whose bone offsets match the observed landmarks.

    Parameters
    ----------
    landmarks : (T, n_joints, 4)  — multi-frame landmark array from skeleton3d_to_landmarks
    weight_kg : body mass for segment mass fractions
    vis_threshold : minimum visibility to trust a landmark pair
    """
    import numpy as np

    copied = tuple(
        JointDef(jd.name, jd.parent, jd.offset, jd.dof_axes, jd.limits)
        for jd in joint_defs
    )
    skeleton = SkeletonModel(copied)

    # Start with height-based uniform scaling as a fallback
    _REF_THIGH = 0.45
    _REF_SHANK = 0.43
    seg_lens = []
    for t in range(landmarks.shape[0]):
        lm = landmarks[t]
        for parent_idx, child_idx in [(2, 4), (3, 5), (4, 6), (5, 7)]:
            if lm[parent_idx, 3] >= vis_threshold and lm[child_idx, 3] >= vis_threshold:
                seg_lens.append(np.linalg.norm(lm[parent_idx, :3] - lm[child_idx, :3]))
    if seg_lens:
        median_seg = float(np.median(seg_lens))
        avg_ref = (_REF_THIGH + _REF_SHANK) / 2
        base_scale = median_seg / avg_ref
    else:
        base_scale = 1.0

    skeleton.scale_offsets(base_scale)

    # Now calibrate each segment individually from observed data.
    # Landmark indices: 0=pelvis, 1=trunk, 2=L_hip, 3=R_hip,
    #   4=L_knee, 5=R_knee, 6=L_ankle, 7=R_ankle, 8=head, 9=L_toe, 10=R_toe
    _SEGMENTS = [
        ("L_hip",   0, 2),   # pelvis → L_hip
        ("R_hip",   0, 3),   # pelvis → R_hip
        ("trunk",   0, 1),   # pelvis → trunk
        ("L_knee",  2, 4),   # L_hip → L_knee
        ("R_knee",  3, 5),   # R_hip → R_knee
        ("L_ankle", 4, 6),   # L_knee → L_ankle
        ("R_ankle", 5, 7),   # R_knee → R_ankle
    ]

    if landmarks.shape[1] > 8:
        _SEGMENTS.append(("head", 1, 8))     # trunk → head
    if landmarks.shape[1] > 9:
        _SEGMENTS.append(("L_toe", 6, 9))    # L_ankle → L_toe
    if landmarks.shape[1] > 10:
        _SEGMENTS.append(("R_toe", 7, 10))   # R_ankle → R_toe

    for joint_name, parent_lm_idx, child_lm_idx in _SEGMENTS:
        observed_lengths = []
        for t in range(landmarks.shape[0]):
            lm = landmarks[t]
            if (lm[parent_lm_idx, 3] >= vis_threshold
                    and lm[child_lm_idx, 3] >= vis_threshold):
                observed_lengths.append(
                    np.linalg.norm(lm[child_lm_idx, :3] - lm[parent_lm_idx, :3])
                )
        if not observed_lengths:
            continue

        observed_length = float(np.median(observed_lengths))
        current_offset = np.array(skeleton.offset(skeleton.joint_index(joint_name)))
        current_length = float(np.linalg.norm(current_offset))
        if current_length < 1e-6:
            continue

        ratio = observed_length / current_length
        new_offset = tuple(float(v * ratio) for v in current_offset)
        skeleton.set_offset(joint_name, new_offset)

    _set_segment_masses(skeleton, weight_kg)
    skeleton._total_weight_kg = weight_kg
    skeleton._height_m = base_scale * REFERENCE_HEIGHT_M
    skeleton._scale_factor = base_scale
    return skeleton


def _set_segment_masses(skeleton: SkeletonModel, weight_kg: float) -> None:
    joint_masses = {}
    segment_to_joint = {
        "pelvis": "pelvis",
        "trunk": "trunk",
        "L_thigh": "L_hip",
        "R_thigh": "R_hip",
        "L_shank": "L_knee",
        "R_shank": "R_knee",
        "L_foot": "L_ankle",
        "R_foot": "R_ankle",
    }

    for seg_name, joint_name in segment_to_joint.items():
        mass = SEGMENT_MASS_FRACTIONS[seg_name] * weight_kg
        joint_masses[joint_name] = joint_masses.get(joint_name, 0.0) + mass

    arm_head_mass = sum(
        SEGMENT_MASS_FRACTIONS[s] * weight_kg
        for s in ("head", "L_upper_arm", "R_upper_arm",
                   "L_forearm_hand", "R_forearm_hand")
    )
    joint_masses["trunk"] = joint_masses.get("trunk", 0.0) + arm_head_mass

    skeleton.set_joint_masses(joint_masses)

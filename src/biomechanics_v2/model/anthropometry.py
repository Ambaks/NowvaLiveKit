"""Generate MJCF XML for the squat skeleton model with anthropometric scaling."""

from __future__ import annotations

import xml.etree.ElementTree as ET

REFERENCE_HEIGHT_M = 1.75
REFERENCE_WEIGHT_KG = 75.0

# Body offsets at reference height (parent-relative, meters)
# Format: (parent_body, offset_x, offset_y, offset_z)
BODY_OFFSETS = {
    "pelvis": (None, 0.0, 0.0, 0.95),
    "trunk": ("pelvis", 0.0, 0.0, 0.28),
    "head": ("trunk", 0.0, 0.0, 0.40),
    "L_hip": ("pelvis", -0.10, 0.0, 0.0),
    "R_hip": ("pelvis", 0.10, 0.0, 0.0),
    "L_knee": ("L_hip", 0.0, 0.0, -0.45),
    "R_knee": ("R_hip", 0.0, 0.0, -0.45),
    "L_ankle": ("L_knee", 0.0, 0.0, -0.43),
    "R_ankle": ("R_knee", 0.0, 0.0, -0.43),
    "L_toe": ("L_ankle", 0.0, 0.20, 0.0),
    "R_toe": ("R_ankle", 0.0, 0.20, 0.0),
    "L_shoulder": ("trunk", -0.19, 0.0, 0.34),
    "R_shoulder": ("trunk", 0.19, 0.0, 0.34),
    "L_elbow": ("L_shoulder", 0.0, 0.0, -0.282),
    "R_elbow": ("R_shoulder", 0.0, 0.0, -0.282),
    "L_wrist": ("L_elbow", 0.0, 0.0, -0.254),
    "R_wrist": ("R_elbow", 0.0, 0.0, -0.254),
}

# Segment mass fractions (de Leva 1996)
SEGMENT_MASS_FRACTIONS = {
    "pelvis": 0.1065,
    "trunk": 0.2213,
    "head": 0.050,
    "L_thigh": 0.0923,
    "R_thigh": 0.0923,
    "L_shank": 0.036,
    "R_shank": 0.036,
    "L_foot": 0.009,
    "R_foot": 0.009,
    "L_upper_arm": 0.0255,
    "R_upper_arm": 0.0255,
    "L_forearm": 0.0138,
    "R_forearm": 0.0138,
    "L_hand": 0.0056,
    "R_hand": 0.0056,
}

# Which body gets which segment mass
BODY_TO_SEGMENT = {
    "pelvis": "pelvis",
    "trunk": "trunk",
    "head": "head",
    "L_hip": "L_thigh",
    "R_hip": "R_thigh",
    "L_knee": "L_shank",
    "R_knee": "R_shank",
    "L_ankle": "L_foot",
    "R_ankle": "R_foot",
    "L_shoulder": "L_upper_arm",
    "R_shoulder": "R_upper_arm",
    "L_elbow": "L_forearm",
    "R_elbow": "R_forearm",
    "L_wrist": "L_hand",
    "R_wrist": "R_hand",
}

# Joint definitions: (body_name, axis, range_deg_low, range_deg_high)
# Pelvis uses a freejoint (6 DOF), so its rotational limits are enforced
# via separate hinge joints on a sub-body. But MuJoCo freejoints don't have
# range limits — we handle pelvis differently.
HINGE_JOINTS = {
    "trunk": [
        ("trunk_rx", "-1 0 0", -30.0, 60.0),
        ("trunk_rz", "0 0 1", -25.0, 25.0),
    ],
    "L_hip": [
        ("L_hip_rx", "1 0 0", -15.0, 130.0),
        ("L_hip_ry", "0 1 0", -30.0, 45.0),
        ("L_hip_rz", "0 0 1", -30.0, 40.0),
    ],
    "R_hip": [
        ("R_hip_rx", "1 0 0", -15.0, 130.0),
        ("R_hip_ry", "0 1 0", -45.0, 30.0),
        ("R_hip_rz", "0 0 1", -40.0, 30.0),
    ],
    "L_knee": [
        ("L_knee_rx", "-1 0 0", 0.0, 150.0),
    ],
    "R_knee": [
        ("R_knee_rx", "-1 0 0", 0.0, 150.0),
    ],
    "L_ankle": [
        ("L_ankle_rx", "1 0 0", -30.0, 40.0),
        ("L_ankle_ry", "0 1 0", -20.0, 20.0),
    ],
    "R_ankle": [
        ("R_ankle_rx", "1 0 0", -30.0, 40.0),
        ("R_ankle_ry", "0 1 0", -20.0, 20.0),
    ],
    "L_shoulder": [
        ("L_shoulder_rx", "1 0 0", -45.0, 180.0),
        ("L_shoulder_rz", "0 0 1", -20.0, 180.0),
        ("L_shoulder_ry", "0 1 0", -90.0, 90.0),
    ],
    "R_shoulder": [
        ("R_shoulder_rx", "1 0 0", -45.0, 180.0),
        ("R_shoulder_rz", "0 0 -1", -180.0, 20.0),
        ("R_shoulder_ry", "0 1 0", -90.0, 90.0),
    ],
    "L_elbow": [
        ("L_elbow_rx", "-1 0 0", 0.0, 150.0),
    ],
    "R_elbow": [
        ("R_elbow_rx", "-1 0 0", 0.0, 150.0),
    ],
}

# Pelvis rotation limits (applied as joint range on the freejoint is not possible,
# so we use a ball joint alternative OR just document that the freejoint is unconstrained
# in translation and we rely on the IK/physics to keep it sane).
# Actually: MuJoCo freejoints have 7 DOF (3 trans + 4 quat). Our V1 model uses
# 6 DOF (3 trans + 3 euler XYZ). To match V1's 20-DOF layout, we use a different
# approach: pelvis is a body with 3 slide joints (tx, ty, tz) + 3 hinge joints (rx, ry, rz).
PELVIS_JOINTS = [
    ("pelvis_tx", "slide", "1 0 0", -float("inf"), float("inf")),
    ("pelvis_ty", "slide", "0 1 0", -float("inf"), float("inf")),
    ("pelvis_tz", "slide", "0 0 1", -float("inf"), float("inf")),
    ("pelvis_rx", "hinge", "-1 0 0", -45.0, 45.0),
    ("pelvis_ry", "hinge", "0 1 0", -25.0, 25.0),
    ("pelvis_rz", "hinge", "0 0 1", -15.0, 15.0),
]

# Mocap body targets (map to skeleton joints for IK)
MOCAP_TARGETS = [
    "pelvis", "trunk", "head",
    "L_hip", "R_hip",
    "L_knee", "R_knee",
    "L_ankle", "R_ankle",
    "L_toe", "R_toe",
    "L_shoulder", "R_shoulder",
    "L_elbow", "R_elbow",
    "L_wrist", "R_wrist",
]


def build_mjcf_xml(
    height_m: float = 1.75,
    weight_kg: float = 75.0,
    include_mocap_bodies: bool = True,
    include_floor: bool = True,
) -> str:
    """Generate MJCF XML string for the squat skeleton model."""
    scale_factor = height_m / REFERENCE_HEIGHT_M
    mass_scale = weight_kg / REFERENCE_WEIGHT_KG

    root = ET.Element("mujoco", model="squat_skeleton")

    # Compiler settings
    ET.SubElement(root, "compiler", angle="radian", coordinate="local")

    # Option: gravity, timestep
    ET.SubElement(root, "option", gravity="0 0 -9.81", timestep="0.002")

    # Default settings
    default = ET.SubElement(root, "default")
    joint_default = ET.SubElement(default, "joint", damping="2.0", armature="0.01")
    geom_default = ET.SubElement(default, "geom", type="capsule", contype="1",
                                  conaffinity="1", rgba="0.4 0.6 0.8 1")

    # Assets (floor texture)
    if include_floor:
        asset = ET.SubElement(root, "asset")
        ET.SubElement(asset, "texture", name="floor_tex", type="2d",
                      builtin="checker", width="512", height="512",
                      rgb1="0.9 0.9 0.9", rgb2="0.7 0.7 0.7")
        ET.SubElement(asset, "material", name="floor_mat", texture="floor_tex",
                      texrepeat="5 5")

    # Worldbody
    worldbody = ET.SubElement(root, "worldbody")

    if include_floor:
        ET.SubElement(worldbody, "geom", name="floor", type="plane",
                      size="5 5 0.1", pos="0 0 0", material="floor_mat",
                      contype="1", conaffinity="1")
        ET.SubElement(worldbody, "light", diffuse="0.8 0.8 0.8",
                      pos="0 2 4", dir="0 0 -1")

    # Build skeleton hierarchy
    scaled_offsets = {}
    for body_name, (parent, offset_x, offset_y, offset_z) in BODY_OFFSETS.items():
        scaled_offsets[body_name] = (
            offset_x * scale_factor,
            offset_y * scale_factor,
            offset_z * scale_factor,
        )

    # Pelvis body pos is "0 0 0" — its world position is controlled entirely
    # by the slide joints (tx, ty, tz), matching V1's convention where
    # q[0:3] directly specifies world position.
    pelvis_body = ET.SubElement(
        worldbody, "body", name="pelvis", pos="0 0 0"
    )

    # Pelvis joints (3 slide + 3 hinge = 6 DOF)
    for joint_name, joint_type, axis, low, high in PELVIS_JOINTS:
        attrs = {"name": joint_name, "type": joint_type, "axis": axis}
        if joint_type == "hinge":
            import math
            attrs["range"] = f"{math.radians(low)} {math.radians(high)}"
            attrs["limited"] = "true"
        else:
            attrs["limited"] = "false"
        ET.SubElement(pelvis_body, "joint", **attrs)

    # Pelvis inertial
    pelvis_mass = SEGMENT_MASS_FRACTIONS["pelvis"] * weight_kg
    _add_inertial(pelvis_body, pelvis_mass, radius=0.08 * scale_factor)

    # Pelvis geom (visual)
    ET.SubElement(pelvis_body, "geom", name="pelvis_geom", type="sphere",
                  size=f"{0.08 * scale_factor}", rgba="0.8 0.4 0.4 0.7", mass="0")
    ET.SubElement(pelvis_body, "site", name="site_pelvis", size="0.02")

    # Build child bodies recursively
    body_elements = {"pelvis": pelvis_body}

    build_order = ["trunk", "head", "L_hip", "R_hip", "L_knee", "R_knee",
                   "L_ankle", "R_ankle", "L_toe", "R_toe",
                   "L_shoulder", "R_shoulder", "L_elbow", "R_elbow",
                   "L_wrist", "R_wrist"]

    for body_name in build_order:
        parent_name = BODY_OFFSETS[body_name][0]
        parent_elem = body_elements[parent_name]
        offset = scaled_offsets[body_name]

        body_elem = ET.SubElement(
            parent_elem, "body", name=body_name,
            pos=f"{offset[0]} {offset[1]} {offset[2]}"
        )
        body_elements[body_name] = body_elem

        # Add joints
        if body_name in HINGE_JOINTS:
            import math
            for joint_name, axis, low_deg, high_deg in HINGE_JOINTS[body_name]:
                ET.SubElement(body_elem, "joint", name=joint_name,
                              type="hinge", axis=axis,
                              range=f"{math.radians(low_deg)} {math.radians(high_deg)}",
                              limited="true")

        # Add inertial/geom
        segment_name = BODY_TO_SEGMENT.get(body_name)
        if segment_name:
            mass = SEGMENT_MASS_FRACTIONS[segment_name] * weight_kg
        else:
            mass = 0.5 * mass_scale  # small mass for endpoint bodies

        _add_inertial(body_elem, mass, radius=0.03 * scale_factor)

        # Geom for visual bodies with length
        geom_info = _get_geom_info(body_name, scale_factor)
        if geom_info:
            ET.SubElement(body_elem, "geom", name=f"{body_name}_geom",
                          mass="0", **geom_info)

        # Site for IK targeting
        ET.SubElement(body_elem, "site", name=f"site_{body_name}", size="0.02")

    # Mocap bodies and equality constraints
    if include_mocap_bodies:
        for target_name in MOCAP_TARGETS:
            mocap_body = ET.SubElement(
                worldbody, "body", name=f"mocap_{target_name}", mocap="true",
                pos=f"{scaled_offsets[target_name][0]} {scaled_offsets[target_name][1]} {scaled_offsets[target_name][2]}"
            )
            ET.SubElement(mocap_body, "geom", type="sphere",
                          size="0.015", rgba="1 0 0 0.3", contype="0", conaffinity="0")
            ET.SubElement(mocap_body, "site", name=f"target_{target_name}", size="0.015")

        equality = ET.SubElement(root, "equality")
        for target_name in MOCAP_TARGETS:
            ET.SubElement(equality, "weld",
                          body1=target_name, body2=f"mocap_{target_name}",
                          solref="0.02 1", solimp="0.9 0.95 0.001",
                          active="true")

    # Actuators (position servos for all joints)
    actuator = ET.SubElement(root, "actuator")
    for joint_name, _, _, _, _ in PELVIS_JOINTS:
        if "slide" in joint_name:
            continue
        ET.SubElement(actuator, "position", name=f"act_{joint_name}",
                      joint=joint_name, kp="100")

    for body_name, joints in HINGE_JOINTS.items():
        for joint_name, axis, low_deg, high_deg in joints:
            ET.SubElement(actuator, "position", name=f"act_{joint_name}",
                          joint=joint_name, kp="100")

    ET.indent(root, space="  ")
    xml_string = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return xml_string


def scale_mjcf_from_proportions(
    base_xml: str,
    proportions,
    weight_kg: float,
) -> str:
    """Adjust segment lengths in MJCF XML to match calibrated bone lengths.

    Parameters
    ----------
    base_xml : MJCF XML string (from build_mjcf_xml)
    proportions : BodyProportions with femur_length_avg, tibia_length_avg,
                  torso_length_avg, hip_width
    weight_kg : athlete mass for re-scaling inertials
    """
    root = ET.fromstring(base_xml)

    # Find bodies and update their positions
    segment_updates = {
        "L_knee": (0.0, 0.0, -proportions.femur_length_avg),
        "R_knee": (0.0, 0.0, -proportions.femur_length_avg),
        "L_ankle": (0.0, 0.0, -proportions.tibia_length_avg),
        "R_ankle": (0.0, 0.0, -proportions.tibia_length_avg),
        "trunk": (0.0, 0.0, proportions.torso_length_avg),
        "L_hip": (-proportions.hip_width / 2, 0.0, 0.0),
        "R_hip": (proportions.hip_width / 2, 0.0, 0.0),
    }

    _update_body_positions_recursive(root, segment_updates)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _update_body_positions_recursive(element: ET.Element, updates: dict) -> None:
    """Walk the XML tree and update body positions."""
    for child in element:
        if child.tag == "body" and child.get("name") in updates:
            offset = updates[child.get("name")]
            child.set("pos", f"{offset[0]} {offset[1]} {offset[2]}")
        _update_body_positions_recursive(child, updates)


def _add_inertial(body_elem: ET.Element, mass: float, radius: float) -> None:
    """Add an inertial element with sphere-approximated inertia."""
    inertia_val = 0.4 * mass * radius * radius
    ET.SubElement(body_elem, "inertial", mass=str(round(mass, 4)),
                  pos="0 0 0",
                  diaginertia=f"{inertia_val:.6f} {inertia_val:.6f} {inertia_val:.6f}")


def _get_geom_info(body_name: str, scale_factor: float) -> dict | None:
    """Return geom attributes for visual representation of a body segment."""
    capsule_radius = 0.025 * scale_factor

    geom_defs = {
        "trunk": {"type": "capsule", "fromto": f"0 0 0 0 0 {0.28 * scale_factor}",
                  "size": f"{capsule_radius * 1.5}", "rgba": "0.4 0.6 0.8 0.7"},
        "head": {"type": "sphere", "size": f"{0.09 * scale_factor}",
                 "rgba": "0.9 0.8 0.7 0.7"},
        "L_hip": {"type": "capsule", "fromto": f"0 0 0 0 0 {-0.45 * scale_factor}",
                  "size": f"{capsule_radius * 1.2}", "rgba": "0.4 0.6 0.8 0.7"},
        "R_hip": {"type": "capsule", "fromto": f"0 0 0 0 0 {-0.45 * scale_factor}",
                  "size": f"{capsule_radius * 1.2}", "rgba": "0.4 0.6 0.8 0.7"},
        "L_knee": {"type": "capsule", "fromto": f"0 0 0 0 0 {-0.43 * scale_factor}",
                   "size": f"{capsule_radius}", "rgba": "0.4 0.6 0.8 0.7"},
        "R_knee": {"type": "capsule", "fromto": f"0 0 0 0 0 {-0.43 * scale_factor}",
                   "size": f"{capsule_radius}", "rgba": "0.4 0.6 0.8 0.7"},
        "L_ankle": {"type": "box",
                    "size": f"{0.04 * scale_factor} {0.10 * scale_factor} {0.02 * scale_factor}",
                    "pos": f"0 {0.10 * scale_factor} {-0.02 * scale_factor}",
                    "rgba": "0.6 0.6 0.4 0.7"},
        "R_ankle": {"type": "box",
                    "size": f"{0.04 * scale_factor} {0.10 * scale_factor} {0.02 * scale_factor}",
                    "pos": f"0 {0.10 * scale_factor} {-0.02 * scale_factor}",
                    "rgba": "0.6 0.6 0.4 0.7"},
        "L_shoulder": {"type": "capsule",
                       "fromto": f"0 0 0 0 0 {-0.282 * scale_factor}",
                       "size": f"{capsule_radius * 0.9}", "rgba": "0.4 0.6 0.8 0.7"},
        "R_shoulder": {"type": "capsule",
                       "fromto": f"0 0 0 0 0 {-0.282 * scale_factor}",
                       "size": f"{capsule_radius * 0.9}", "rgba": "0.4 0.6 0.8 0.7"},
        "L_elbow": {"type": "capsule",
                    "fromto": f"0 0 0 0 0 {-0.254 * scale_factor}",
                    "size": f"{capsule_radius * 0.8}", "rgba": "0.4 0.6 0.8 0.7"},
        "R_elbow": {"type": "capsule",
                    "fromto": f"0 0 0 0 0 {-0.254 * scale_factor}",
                    "size": f"{capsule_radius * 0.8}", "rgba": "0.4 0.6 0.8 0.7"},
        "L_wrist": {"type": "sphere",
                    "size": f"{0.02 * scale_factor}", "rgba": "0.6 0.6 0.4 0.7"},
        "R_wrist": {"type": "sphere",
                    "size": f"{0.02 * scale_factor}", "rgba": "0.6 0.6 0.4 0.7"},
    }
    return geom_defs.get(body_name)

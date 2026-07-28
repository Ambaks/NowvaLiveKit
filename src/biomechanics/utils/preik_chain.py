"""Pre-IK Skeleton Filter Chain

Defines the order of the 3D-keypoint filters that run between pose
estimation and the IK solver. The order lives here rather than inline in
the pipeline so it can be exercised end to end by a test: the defects
this chain has shipped were interactions between stages, invisible to
tests that drove each filter on its own.
"""

from __future__ import annotations

from typing import Protocol

from biomechanics.utils.bone_constraints import BoneLengthConstraints
from biomechanics.utils.confidence_blend import ConfidenceBlender
from biomechanics.utils.ground_clamp import GroundClamp
from biomechanics.utils.position_filter import KeypointPositionSmoother
from biomechanics.utils.types import Skeleton3D
from biomechanics.utils.velocity_clamp import VelocityClamp


class _Smoother(Protocol):
    def smooth(self, skeleton: Skeleton3D) -> Skeleton3D: ...


def apply_preik_filters(
    skeleton: Skeleton3D,
    *,
    confidence_blender: ConfidenceBlender,
    velocity_clamp: VelocityClamp,
    bone_constraints: BoneLengthConstraints,
    ground_clamp: GroundClamp,
    position_smoother: KeypointPositionSmoother | _Smoother,
) -> Skeleton3D:
    """Run the pre-IK filters in order and return the filtered skeleton.

    The caller must advance the standing-pose gate once per frame before
    calling this — the calibrators inside read the gate but never advance
    it. The second bone-length pass repairs the length drift the position
    smoother introduces by smoothing joint positions independently.
    """
    skeleton = confidence_blender.blend(skeleton)
    skeleton = velocity_clamp.clamp(skeleton)
    skeleton = bone_constraints.enforce(skeleton)
    skeleton = ground_clamp.clamp(skeleton)
    skeleton = position_smoother.smooth(skeleton)
    return bone_constraints.enforce(skeleton)

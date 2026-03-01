"""
Fault Detection Rules

Individual rule implementations for detecting specific form faults.
"""

from biomechanics.faults.rules.depth import DepthRule, DepthCategory
from biomechanics.faults.rules.symmetry import SymmetryRule
from biomechanics.faults.rules.heel_rise import HeelRiseRule
from biomechanics.faults.rules.forward_lean import ForwardLeanRule
from biomechanics.faults.rules.knee_valgus import KneeValgusRule

__all__ = [
    "DepthRule",
    "DepthCategory",
    "SymmetryRule",
    "HeelRiseRule",
    "ForwardLeanRule",
    "KneeValgusRule",
]

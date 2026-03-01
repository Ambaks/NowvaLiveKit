"""
Fault Detection Module

Provides fault detection rules, rep counting, and rule engine
for real-time form analysis during exercises.
"""

from biomechanics.faults.fault_types import (
    FaultType,
    FaultRule,
    DEFAULT_THRESHOLDS,
    FAULT_MESSAGES,
)
from biomechanics.faults.rep_counter import RepCounter, RepCounterConfig, RepState
from biomechanics.faults.rule_engine import RuleEngine

__all__ = [
    "FaultType",
    "FaultRule",
    "DEFAULT_THRESHOLDS",
    "FAULT_MESSAGES",
    "RepCounter",
    "RepCounterConfig",
    "RepState",
    "RuleEngine",
]

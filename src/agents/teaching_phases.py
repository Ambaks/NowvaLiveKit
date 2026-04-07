"""
Teaching phase definitions for the TeachingAgent state machine.

Defines the phases a beginner walks through when learning an exercise
(currently: barbell back squat) before being handed off to WorkoutAgent.
"""

from enum import Enum


class TeachingPhase(Enum):
    SETUP = "setup"
    DESCENDING = "descending"
    BOTTOM = "bottom"
    ASCENDING = "ascending"
    REP_COMPLETE = "rep_complete"
    HANDOFF = "handoff"

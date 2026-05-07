"""
Teaching phase definitions for the TeachingAgent state machine.

Defines the phases a beginner walks through when learning an exercise
(currently: barbell back squat) before being handed off to WorkoutAgent.
"""

from enum import Enum


class TeachingPhase(Enum):
    INTRO = "intro"                       # initial; agent has spoken nothing yet
    AWAITING_STANCE = "awaiting_stance"   # gave setup cues; watching stance ratio
    DESCENDING = "descending"             # in a rep, eccentric phase
    ASCENDING = "ascending"               # in a rep, concentric phase
    REP_COMPLETE = "rep_complete"         # finished rep, evaluating
    HANDOFF = "handoff"                   # about to swap to WorkoutAgent

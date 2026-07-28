"""
Tests for quick-exercise instruction building with prefilled parameters.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.agents.quickExerciseAgent import build_task_instructions


class TestBuildTaskInstructions:
    def test_nothing_prefilled_asks_for_everything(self):
        instructions = build_task_instructions("squat", None, None, None, None)
        assert "number of sets" in instructions
        assert "reps per set" in instructions
        assert "weight in lbs" in instructions
        assert "rest between sets" in instructions
        assert "ALREADY provided" not in instructions

    def test_partial_prefill_only_asks_for_missing(self):
        instructions = build_task_instructions("squat", 2, 3, None, 30)
        assert "number of sets = 2" in instructions
        assert "reps per set = 3" in instructions
        assert "rest between sets in seconds = 30" in instructions
        assert "Do NOT ask for these again" in instructions
        assert "Conversationally collect ONLY the remaining details" in instructions
        assert "weight in lbs" in instructions.split("remaining details:")[1]

    def test_all_prefilled_starts_immediately(self):
        instructions = build_task_instructions("squat", 2, 3, 0.0, 30)
        assert "Call the start_workout tool IMMEDIATELY" in instructions
        assert "Conversationally collect" not in instructions

    def test_bodyweight_zero_counts_as_provided(self):
        instructions = build_task_instructions("squat", None, None, 0.0, None)
        assert "weight in lbs (0 for bodyweight) = 0.0" in instructions
        assert "Do NOT ask for these again" in instructions

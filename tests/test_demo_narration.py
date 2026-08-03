"""Tests for demo narration script parsing and fallback."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.services.demo_narration import (
    build_fallback_script,
    parse_demo_script,
)

_VALID_PAYLOAD = {
    "intro": "Look at the screen!",
    "cue_lines": ["Widen that stance, watch your feet slide out.", "Knees out, see them track."],
    "outro": "Give me two more!",
}

_CUES = [
    {
        "cue_index": 0,
        "cause_id": "narrow_stance",
        "explanation": "stance too narrow",
        "magnitude_text": "about 4 centimeters wider on each side",
    },
    {
        "cue_index": 1,
        "cause_id": "knee_track_cue",
        "explanation": "knees caving",
        "magnitude_text": "knees pushed out about 6 degrees more",
    },
]


class TestParseDemoScript:

    def test_parse_valid_json(self) -> None:
        script = parse_demo_script(json.dumps(_VALID_PAYLOAD), expected_count=2)

        assert script is not None
        assert script.intro == "Look at the screen!"
        assert len(script.cue_lines) == 2

    def test_parse_strips_code_fences(self) -> None:
        fenced = f"```json\n{json.dumps(_VALID_PAYLOAD)}\n```"

        script = parse_demo_script(fenced, expected_count=2)

        assert script is not None
        assert script.outro == "Give me two more!"

    def test_parse_rejects_wrong_cue_count(self) -> None:
        assert parse_demo_script(json.dumps(_VALID_PAYLOAD), expected_count=3) is None

    def test_parse_rejects_non_string_lines(self) -> None:
        payload = dict(_VALID_PAYLOAD, cue_lines=["fine", 42])

        assert parse_demo_script(json.dumps(payload), expected_count=2) is None

    def test_parse_rejects_missing_intro(self) -> None:
        payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "intro"}

        assert parse_demo_script(json.dumps(payload), expected_count=2) is None

    def test_parse_rejects_invalid_json(self) -> None:
        assert parse_demo_script("not json at all", expected_count=2) is None


class TestBuildFallbackScript:

    def test_one_line_per_cue(self) -> None:
        script = build_fallback_script(_CUES)

        assert len(script.cue_lines) == len(_CUES)

    def test_lines_contain_magnitude_text(self) -> None:
        script = build_fallback_script(_CUES)

        assert "4 centimeters" in script.cue_lines[0]
        assert "6 degrees" in script.cue_lines[1]

    def test_intro_and_outro_present(self) -> None:
        script = build_fallback_script(_CUES)

        assert script.intro
        assert script.outro

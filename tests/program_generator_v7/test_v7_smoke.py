from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from program_generator_v7.main import generate_program_v7_sync

from fixtures import build_v7_input


def test_v7_generates_program_with_trace_and_kg_metadata():
    result = generate_program_v7_sync(build_v7_input("hypertrophy_general"), use_llm=False)

    assert result["version"] == "7.0"
    assert result["generator"] == "V7 Program Generator"
    assert len(result["weeks"]) == 4
    assert result["overview"]["kg_version"]
    assert result["artifact_summary"]["trace_entries"] > 0
    assert result["artifact_summary"]["kg_version"] == result["overview"]["kg_version"]
    assert result["stats"]["validation_score"] >= 0

    for week in result["weeks"]:
        assert week["workouts"]
        for workout in week["workouts"]:
            assert workout["exercises"]
            for exercise in workout["exercises"]:
                assert exercise["exercise_id"]
                assert exercise["exercise_name"]

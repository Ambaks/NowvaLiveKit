from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from program_generator_v5.main import generate_program_v5_sync
from program_generator_v7.main import generate_program_v7_sync

from fixtures import RAW_V7_PERSONAS, build_v5_input, build_v7_input


def generate_scorecard(persona_names: list[str] | None = None) -> list[dict]:
    persona_names = persona_names or list(RAW_V7_PERSONAS.keys())
    rows = []
    for persona_name in persona_names:
        v5_result = generate_program_v5_sync(build_v5_input(persona_name), use_llm=False)
        v7_result = generate_program_v7_sync(build_v7_input(persona_name), use_llm=False)
        rows.append({
            "persona": persona_name,
            "v5": _summarize_v5(v5_result),
            "v7": _summarize_v7(v7_result),
        })
    return rows


def render_markdown_scorecard(rows: list[dict]) -> str:
    lines = [
        "| Persona | Generator | Weeks | Unique Exercises | Validation | Time (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(_markdown_row(row["persona"], "V5", row["v5"]))
        lines.append(_markdown_row(row["persona"], "V7", row["v7"]))
    return "\n".join(lines)


def _summarize_v5(result: dict) -> dict:
    quality = result.get("quality", {}).get("validation_issues", {})
    return {
        "weeks": len(result.get("weeks", [])),
        "unique_exercises": result.get("stats", {}).get("unique_exercises", 0),
        "validation": {
            "critical": quality.get("critical", 0),
            "major": quality.get("major", 0),
            "warnings": quality.get("warnings", 0),
        },
        "generation_time_seconds": round(result.get("stats", {}).get("generation_time_seconds", 0.0), 4),
    }


def _summarize_v7(result: dict) -> dict:
    quality = result.get("quality", {}).get("validation_issues", {})
    return {
        "weeks": len(result.get("weeks", [])),
        "unique_exercises": result.get("stats", {}).get("unique_exercises", 0),
        "validation": {
            "critical": quality.get("critical_count", 0),
            "major": quality.get("major_count", 0),
            "warnings": quality.get("warning_count", 0),
        },
        "validation_score": result.get("stats", {}).get("validation_score", 0.0),
        "kg_version": result.get("overview", {}).get("kg_version"),
        "trace_entries": result.get("artifact_summary", {}).get("trace_entries", 0),
        "generation_time_seconds": round(result.get("stats", {}).get("generation_time_seconds", 0.0), 4),
    }


def _markdown_row(persona: str, generator: str, summary: dict) -> str:
    validation = summary["validation"]
    validation_text = f"{validation['critical']}/{validation['major']}/{validation['warnings']}"
    return (
        f"| {persona} | {generator} | {summary['weeks']} | "
        f"{summary['unique_exercises']} | {validation_text} | "
        f"{summary['generation_time_seconds']:.2f} |"
    )


if __name__ == "__main__":
    scorecard = generate_scorecard()
    print(render_markdown_scorecard(scorecard))
    print("\nJSON\n")
    print(json.dumps(scorecard, indent=2))

from __future__ import annotations

from program_generator_v5.layer6_serializer import serialize_to_v3

from .critic import should_run_critic
from .scoring import build_validation_score
from .validators import summarize_validation_issues


def serialize_v7_program(artifact) -> dict:
    validation_dicts = [issue.model_dump() for issue in artifact.validation_issues]
    critique = artifact.critic
    llm_review = {
        "overall_grade": critique.overall_grade if critique else "N/A",
        "strengths": _derive_strengths(artifact.metrics),
        "issues": [issue.model_dump() for issue in critique.issues] if critique else [],
        "coaching_summary": critique.summary if critique else "Structured critic skipped.",
    }
    output = serialize_to_v3(
        program=artifact.program,
        validation_issues=validation_dicts,
        llm_review=llm_review,
    )
    validation_summary = summarize_validation_issues(artifact.validation_issues)
    validation_score = build_validation_score(artifact.metrics, len(artifact.validation_issues))

    output["version"] = "7.0"
    output["generator"] = "V7 Program Generator"
    output["overview"]["generation_mode"] = artifact.directive.program_request.generation_mode
    output["overview"]["kg_version"] = artifact.kg_version
    output["overview"]["phase_sequence"] = artifact.block_plan.phase_sequence
    output["overview"]["planner_notes"] = artifact.block_plan.planner_notes
    output["stats"]["validation_score"] = validation_score
    output["stats"]["critic_recommended"] = should_run_critic(artifact)
    output["quality"]["validation_issues"] = validation_summary
    output["quality"]["v7_metrics"] = artifact.metrics
    output["quality"]["critic"] = critique.model_dump() if critique else None
    output["artifact_summary"] = {
        "kg_version": artifact.kg_version,
        "prompt_version": artifact.prompt_version,
        "trace_entries": len(artifact.assembly_trace),
        "repair_operations": len(artifact.repair_log),
    }
    output["_artifact_internal"] = {
        "directive": artifact.directive.model_dump(),
        "block_plan": artifact.block_plan.model_dump(),
        "assembly_trace": [entry.model_dump() for entry in artifact.assembly_trace],
        "validation": validation_dicts,
        "repair_log": [entry.model_dump() for entry in artifact.repair_log],
        "critic": critique.model_dump() if critique else None,
        "metrics": artifact.metrics,
        "kg_version": artifact.kg_version,
        "prompt_version": artifact.prompt_version,
    }
    return output


def _derive_strengths(metrics: dict) -> list[str]:
    strengths = []
    if metrics.get("weekly_volume_alignment", 0.0) >= 0.9:
        strengths.append("Weekly volume targets are tightly aligned.")
    if metrics.get("fatigue_balance_score", 0.0) >= 0.85:
        strengths.append("Fatigue is distributed coherently across the week.")
    if metrics.get("anchor_stability_score", 0.0) >= 0.75:
        strengths.append("Primary families stay stable enough for progression.")
    return strengths or ["Program assembled deterministically with V7 trace data."]

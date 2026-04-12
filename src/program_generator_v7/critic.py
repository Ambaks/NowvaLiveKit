from __future__ import annotations

import json

from .scoring import build_validation_score
from .schemas import CritiqueIssue, CritiqueRepairSuggestion, CritiqueV7, ProgramArtifactV7


def should_run_critic(artifact: ProgramArtifactV7) -> bool:
    metrics = artifact.metrics
    issue_count = len(artifact.validation_issues)
    validation_score = build_validation_score(metrics, issue_count)

    if artifact.directive.program_request.generation_mode == "audit":
        return True
    if artifact.directive.program_request.generation_mode == "cheap":
        return False
    return validation_score < 80 or issue_count > 4


async def run_structured_critic(
    artifact: ProgramArtifactV7,
    openai_client,
) -> CritiqueV7 | None:
    prompt = _build_critic_prompt(artifact)
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        payload = json.loads(response.choices[0].message.content)
    except Exception:
        return None

    issues = [
        CritiqueIssue(
            severity=item.get("severity", "warning"),
            message=item.get("message", ""),
            rationale=item.get("rationale", ""),
            scope=item.get("scope", "program"),
            week=item.get("week"),
            session=item.get("session"),
        )
        for item in payload.get("issues", [])
    ]
    suggestions = [
        CritiqueRepairSuggestion(
            op_type=item.get("op_type", "rebalance_week"),
            reason=item.get("reason", ""),
            target_scope=item.get("target_scope", "program"),
            target_id=item.get("target_id"),
            target_week=item.get("target_week"),
            target_session=item.get("target_session"),
            target_exercise_id=item.get("target_exercise_id"),
            replacement_family_id=item.get("replacement_family_id"),
            replacement_canonical_id=item.get("replacement_canonical_id"),
            confidence=float(item.get("confidence", 0.0)),
            do_not_apply_if=list(item.get("do_not_apply_if", [])),
        )
        for item in payload.get("repair_suggestions", [])
    ]
    return CritiqueV7(
        overall_grade=payload.get("overall_grade", "B"),
        issues=issues,
        repair_suggestions=suggestions,
        confidence=float(payload.get("confidence", 0.0)),
        summary=payload.get("summary", ""),
    )


def get_auto_applicable_suggestions(critique: CritiqueV7 | None) -> list[CritiqueRepairSuggestion]:
    if critique is None:
        return []
    allowed_ops = {
        "swap_within_family",
        "restore_anchor_family",
        "trim_sets",
        "rebalance_week",
        "swap_lower_fatigue_sibling",
    }
    return [
        suggestion
        for suggestion in critique.repair_suggestions
        if suggestion.confidence >= 0.8 and suggestion.op_type in allowed_ops
    ]


def _build_critic_prompt(artifact: ProgramArtifactV7) -> str:
    summary = {
        "directive": {
            "goal": artifact.directive.goal_stack.primary_goal,
            "effective_goal": artifact.directive.derived_context.effective_goal,
            "sport": artifact.directive.athlete.sport,
            "season": artifact.directive.athlete.training_season,
            "days_per_week": artifact.directive.program_request.days_per_week,
            "duration_weeks": artifact.directive.program_request.duration_weeks,
            "notes": artifact.directive.program_request.user_notes,
        },
        "block_plan": {
            "phase_sequence": artifact.block_plan.phase_sequence,
            "planner_notes": artifact.block_plan.planner_notes,
            "weeks": [
                {
                    "week_number": week.week_number,
                    "phase": week.phase_name,
                    "goal_phase": week.goal_phase,
                    "deload": week.deload,
                    "movement_quotas": week.movement_quotas,
                    "session_types": [session.session_type for session in week.sessions],
                }
                for week in artifact.block_plan.weeks
            ],
        },
        "metrics": artifact.metrics,
        "validation_issues": [issue.model_dump() for issue in artifact.validation_issues[:12]],
    }
    return (
        "You are a bounded critic for a deterministic strength-program generator. "
        "Do not generate a new program. Return only JSON with keys overall_grade, summary, "
        "confidence, issues, repair_suggestions. Each repair suggestion must reference one "
        "allowed deterministic op: swap_within_family, restore_anchor_family, trim_sets, "
        "rebalance_week, swap_lower_fatigue_sibling. Keep suggestions sparse and cheap.\n\n"
        f"{json.dumps(summary)}"
    )

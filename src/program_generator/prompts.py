"""
V5 Program Generator — LLM Prompt Templates
All prompts with format functions for structured output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import AthleteProfile, ProgramStrategy, BuiltWeek, BuiltProgram


# ─────────────────────────────────────────────────────────────────────────────
# 1. PROFILE EXTRACTION PROMPT (Layer 1)
# ─────────────────────────────────────────────────────────────────────────────


def format_profile_extraction_prompt(raw_text: str) -> str:
    """
    Format the prompt for extracting structured athlete profile from
    natural language input (voice agent transcript, free-text).

    Returns a prompt that asks the LLM to return structured JSON.
    """
    return f"""You are extracting a structured athlete profile from a conversation transcript or free-text input.

Extract the following fields from the user's input. If a field is not mentioned, set it to null.
Do NOT infer values that weren't stated or clearly implied.

Guidelines:
- If the user mentions a sport, identify the specific sport name.
- If the user mentions injuries, extract the body area and what movements to avoid.
- If the user mentions preferences like "I love deadlifts" or "I hate leg press", extract those.
- If the user mentions weak points like "my arms are small" or "I want bigger shoulders", extract the muscle groups.
- If the user mentions training history like "been lifting 3 years", extract training_age_years.
- If the user mentions goals like "get toned", "build muscle", "get stronger", map to: hypertrophy, strength, or power.

USER INPUT:
{raw_text}

Return a JSON object matching this schema (copy the exact structure):
{{
    "training_goal": "hypertrophy" | "strength" | "power" | null,
    "sport": string | null,
    "training_level": "beginner" | "intermediate" | "advanced" | null,
    "training_days_per_week": int | null,
    "session_duration_minutes": int | null,
    "injuries": [{{"area": string, "avoid": [string]}}],
    "exercises_to_avoid": [string],
    "exercises_to_include": [string],
    "weak_points": [string],
    "recovery_notes": string | null,
    "additional_context": string | null
}}

Return ONLY the JSON object, no other text.
"""


# ─────────────────────────────────────────────────────────────────────────────
# 2. STRATEGY RESOLUTION PROMPT (Layer 2)
# ─────────────────────────────────────────────────────────────────────────────


def format_strategy_resolution_prompt(
    conflict_description: str,
    rules_output: dict,
    profile: AthleteProfile,
) -> str:
    """
    Format the prompt for resolving strategy conflicts that the deterministic
    rules engine cannot handle.

    conflict_description: What the conflict is (e.g., "User wants 6 days/week but is a beginner")
    rules_output: What the rules engine selected
    profile: Full athlete profile
    """
    profile_summary = f"""
Athlete Profile:
- Goal: {profile.training_goal}
- Sport: {profile.sport or "None"}
- Level: {profile.training_level}
- Days per week: {profile.training_days_per_week}
- Session duration: {profile.session_duration_minutes} min
- Equipment tier: {profile.equipment_tier.value}
- Injuries: {profile.injuries if profile.injuries else "None"}
- Weak points: {", ".join(profile.weak_points) if profile.weak_points else "None"}
"""

    return f"""You are an expert strength & conditioning coach resolving a conflict in program design.

The deterministic rules engine selected:
- Split: {rules_output.get("split", "N/A")}
- Periodization: {rules_output.get("periodization", "N/A")}

But there's a conflict:
{conflict_description}

{profile_summary}

Your options for resolving:
1. Override the split to one of: {rules_output.get("alternative_splits", [])}
2. Override the periodization to one of: {rules_output.get("alternative_periodizations", [])}
3. Adjust constraints: {rules_output.get("possible_adjustments", "Reduce training frequency, modify volume targets, etc.")}

Choose the best resolution and explain your reasoning in 2-3 sentences.

Return JSON:
{{
    "resolution": "override_split" | "override_periodization" | "adjust_constraints",
    "value": string,
    "reasoning": string
}}

Return ONLY the JSON object, no other text.
"""


# ─────────────────────────────────────────────────────────────────────────────
# 3. WEEK REVIEW PROMPT (Layer 4)
# ─────────────────────────────────────────────────────────────────────────────


def format_week_review_prompt(
    week: BuiltWeek,
    profile: AthleteProfile,
    strategy: ProgramStrategy,
) -> str:
    """
    Format the prompt for per-week coherence review.
    This is called AFTER the deterministic engine has built the week's workouts.

    The LLM reviews qualitative aspects: exercise synergy, session flow,
    week-level coherence, and coaching intuition.
    """
    # Serialize the week's workouts into readable text
    formatted_week = _serialize_week(week)

    # Volume summary
    volume_summary = "\n".join(
        f"  {muscle}: {volume:.1f} sets"
        for muscle, volume in sorted(week.weekly_volume_actual.items())
        if volume > 0
    )

    sport_context = (
        f"Sport: {profile.sport} (sport-specific adjustments applied)"
        if profile.sport
        else "No sport-specific focus"
    )

    equipment_desc = {
        1: "Barbell + rack + bench + pull-up bar only",
        2: "Barbell + dumbbells",
        3: "Barbell + dumbbells + resistance bands",
    }.get(profile.equipment_tier.value, "Unknown equipment")

    total_weeks = len(strategy.week_profiles)

    return f"""You are a world-class strength & conditioning coach reviewing one week of a {profile.training_goal} training program.

The athlete: {profile.training_level} level, {equipment_desc}, training {profile.training_days_per_week}x/week.
{sport_context}

This is Week {week.week_number} ({week.phase_name}) of a {total_weeks}-week program.

Here is the week's training:

{formatted_week}
--- end of week ---

Weekly volume summary:
{volume_summary}

The volume targets and movement pattern balance have ALREADY been validated by a deterministic engine
and are guaranteed correct. Do NOT comment on total volume, MEV/MRV compliance, or movement pattern coverage.

Instead, evaluate these QUALITATIVE aspects:

1. **Exercise synergy**: Do the selected exercises work well together within each session?
   Look for: redundant exercises hitting the same muscle at the same angle, missed opportunities
   for complementary exercises, exercises that would fatigue each other poorly (e.g., heavy RDLs
   immediately after heavy deadlifts).

2. **Session flow**: Does the exercise ordering make sense for training quality?
   Look for: grip-intensive exercises stacked back-to-back, exercises requiring the same equipment
   creating logistical issues, poor superset pairings.

3. **Week-level coherence**: Do the sessions within the week complement each other?
   Look for: overemphasis on one movement angle across the week (e.g., all chest work is flat pressing,
   no incline), lack of exercise variety between sessions with the same muscle groups.

4. **Coaching intuition**: Anything a good coach would change that isn't covered above?

Return a JSON object:
{{
    "issues": [
        {{
            "session_day": int,
            "exercise_id": string|null,
            "issue": string,
            "suggestion": string,
            "confidence": "high" | "medium" | "low"
        }}
    ],
    "overall_quality": "excellent" | "good" | "needs_work",
    "coaching_notes": string
}}

If the week looks good, return empty issues array with "excellent" or "good" quality.
Only flag issues you're confident about. Max 3 issues per week.

Return ONLY the JSON object, no other text.
"""


def _serialize_week(week: BuiltWeek) -> str:
    """
    Convert a BuiltWeek into human-readable text for the LLM.
    """
    lines = []
    for workout in week.workouts:
        lines.append(f"\n=== Day {workout.day_number}: {workout.day_label} ===")
        lines.append(f"Estimated duration: {workout.estimated_duration_minutes} min")
        lines.append("")

        for ex in workout.exercises:
            # Format: "1. Barbell Bench Press — 3×8-10 @ RPE 7, rest 150s, tempo 2-1-1-0"
            sets_summary = f"{ex.total_sets}×{ex.sets[0].reps}" if ex.sets else f"{ex.total_sets} sets"
            rpe_str = f"@ RPE {ex.sets[0].rpe}" if ex.sets and ex.sets[0].rpe else ""
            rest_str = f"rest {ex.sets[0].rest_seconds}s" if ex.sets else ""
            tempo_str = f"tempo {ex.sets[0].tempo}" if ex.sets and ex.sets[0].tempo else ""

            superset_str = f"[Superset {ex.superset_group}] " if ex.superset_group else ""

            line = f"{ex.order_in_session}. {superset_str}{ex.exercise_name} — {sets_summary} {rpe_str}, {rest_str}, {tempo_str}"
            lines.append(line.strip())

            # Add notes from first set if present
            if ex.sets and ex.sets[0].notes:
                lines.append(f"   Note: {ex.sets[0].notes}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 4. FULL PROGRAM REVIEW PROMPT (Layer 5)
# ─────────────────────────────────────────────────────────────────────────────


def format_full_program_review_prompt(program: BuiltProgram) -> str:
    """
    Format the prompt for holistic, full-program review.
    This is the FINAL LLM call, done after all deterministic validation passes.

    The LLM looks for long-term patterns, overuse issues, and overall quality.
    """
    profile = program.profile
    formatted_program = _serialize_full_program(program)

    sport_context = (
        f"Sport: {profile.sport} (sport-specific adjustments applied)"
        if profile.sport
        else "No sport-specific focus"
    )

    equipment_desc = {
        1: "Barbell + rack + bench + pull-up bar only",
        2: "Barbell + dumbbells",
        3: "Barbell + dumbbells + resistance bands",
    }.get(profile.equipment_tier.value, "Unknown equipment")

    weak_points_context = (
        f"Weak points to address: {', '.join(profile.weak_points)}"
        if profile.weak_points
        else "No specific weak points stated"
    )

    return f"""You are a world-class S&C coach doing a final review of a complete {profile.training_goal} training program.

Athlete: {profile.training_level}, {equipment_desc}, {profile.training_days_per_week}x/week, {profile.program_duration_weeks} weeks.
{sport_context}
{weak_points_context}

The program has already passed all quantitative validation:
- ✅ Volume targets met for all muscle groups every week
- ✅ Movement pattern balance verified
- ✅ Push:pull ratios within range
- ✅ Periodization model correct for goal
- ✅ Exercise ordering correct
- ✅ No duplicate sessions

Your job is the FINAL coaching eye. Look for:

1. **Long-term exercise progression**: Does the exercise selection evolve sensibly across mesocycles?
   Are there logical progressions (e.g., goblet squat → back squat → front squat)?

2. **Overuse patterns across weeks**: Any joint or tendon getting hammered with the same movement
   pattern every session, every week? (e.g., always conventional grip bench, never neutral grip)

3. **Training experience quality**: Would this program be motivating and enjoyable to follow?
   Is there enough variety to prevent boredom without being chaotic?

4. **Weak point addressing**: Given the athlete's stated weak points ({", ".join(profile.weak_points) if profile.weak_points else "none"}),
   does the program adequately prioritize those areas with both volume AND exercise selection?

5. **Red flags**: Anything that would make you, as a coach, uncomfortable prescribing this?

Here is the complete program:

{formatted_program}

Return JSON:
{{
    "overall_grade": "A" | "B" | "C" | "D" | "F",
    "strengths": [string],
    "issues": [
        {{
            "category": string,
            "description": string,
            "affected_weeks": [int],
            "suggested_fix": string,
            "confidence": "high" | "medium" | "low"
        }}
    ],
    "coaching_summary": string
}}

Be honest but constructive. Only flag genuine issues. Max 5 issues.

Return ONLY the JSON object, no other text.
"""


def _serialize_full_program(program: BuiltProgram) -> str:
    """
    Convert a BuiltProgram into human-readable text for the LLM.
    Condenses to focus on exercise selection and progression.
    """
    lines = []
    lines.append(f"Program: {program.profile.program_duration_weeks} weeks, {program.total_workouts} workouts\n")

    for week in program.weeks:
        lines.append(f"\n{'='*60}")
        lines.append(f"WEEK {week.week_number} — {week.phase_name}")
        lines.append(f"{'='*60}")

        for workout in week.workouts:
            lines.append(f"\n{workout.day_label}:")
            for ex in workout.exercises:
                sets_str = f"{ex.total_sets}×{ex.sets[0].reps}" if ex.sets else f"{ex.total_sets} sets"
                rpe_str = f"@ RPE {ex.sets[0].rpe}" if ex.sets and ex.sets[0].rpe else ""
                lines.append(f"  {ex.exercise_name} — {sets_str} {rpe_str}")

    lines.append(f"\n{'='*60}")
    lines.append(f"Unique exercises used: {program.unique_exercises_used}")
    lines.append(f"Total sets: {program.total_sets}")
    lines.append(f"{'='*60}")

    return "\n".join(lines)

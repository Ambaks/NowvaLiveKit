"""
Step-scoped prompts for the website voice agent.

Each conversation step gets a focused prompt (~100-150 tokens) instead of
one monolithic ~2800-token blob. This reduces TTFT on Groq, eliminates
instruction drift on Llama 3.3, and keeps each LLM turn laser-focused
on a single question.

The active flow is 5 conversational steps (plus goodbye):
    NAME_CAPTURE -> PERSONAL_INFO -> GOAL -> FITNESS_LEVEL -> EXTRA_DETAILS -> GOODBYE

Legacy per-field steps (HEIGHT_WEIGHT, AGE_SEX, DURATION, etc.) are kept
in the enum so old @function_tool methods still resolve if the LLM invokes
them, but they are not part of STEP_ORDER.
"""

from enum import Enum
from typing import Dict, Any, Optional


class ConversationStep(Enum):
    # Active flow
    NAME_CAPTURE = "name_capture"
    PERSONAL_INFO = "personal_info"
    GOAL = "goal"
    FITNESS_LEVEL = "fitness_level"
    EXTRA_DETAILS = "extra_details"
    GOODBYE = "goodbye"
    # Legacy -- kept so old @function_tools still resolve, not in STEP_ORDER
    HEIGHT_WEIGHT = "height_weight"
    AGE_SEX = "age_sex"
    DURATION = "duration"
    FREQUENCY = "frequency"
    SESSION_DURATION = "session_duration"
    INJURIES = "injuries"
    SPORT = "sport"
    TRAINING_SEASON = "training_season"
    GAMES_PER_WEEK = "games_per_week"
    NOTES = "notes"
    EQUIPMENT = "equipment"


# Ordered list of all steps in the default conversation flow.
STEP_ORDER = [
    ConversationStep.NAME_CAPTURE,
    ConversationStep.PERSONAL_INFO,
    ConversationStep.GOAL,
    ConversationStep.FITNESS_LEVEL,
    ConversationStep.EXTRA_DETAILS,
    ConversationStep.GOODBYE,
]

# Mapping from missing program_creation keys to the step that captures them.
# Used by the finalize safety net to bounce the user back to the correct step
# if a required param somehow went missing.
_PARAM_TO_STEP = {
    "height_cm": ConversationStep.PERSONAL_INFO,
    "weight_kg": ConversationStep.PERSONAL_INFO,
    "age": ConversationStep.PERSONAL_INFO,
    "sex": ConversationStep.PERSONAL_INFO,
    "goal_category": ConversationStep.GOAL,
    "goal_raw": ConversationStep.GOAL,
    "duration_weeks": ConversationStep.EXTRA_DETAILS,
    "days_per_week": ConversationStep.EXTRA_DETAILS,
    "fitness_level": ConversationStep.FITNESS_LEVEL,
}

# ── Base context prepended to every step ─────────────────────────────────

_BASE_CONTEXT = """\
You are Nova, a friendly, energetic and expressive AI fitness coach helping the user create a personalized workout program.
Always respond in English. Keep responses brief and conversational.
You are actively having a conversation with the user. Act like a human being. NEVER call out function names out loud.
Make sure to use natural punctuation for pacing ("...", "!", ",", "--", "?"). No markdown, no special characters, no emoji.
Use filler words to sound more natural: "like...", "ummm...", "...uhhh...", "let me see..."
If the user goes off-topic, engage briefly, then redirect back to the current question. Do NOT advance until the current step is fully captured.

With this in context, create a response to the following scenario:"""



# ── Skip logic ───────────────────────────────────────────────────────────

def _should_skip(step: ConversationStep, state: Dict[str, Any]) -> bool:
    """Return True if this step should be skipped given current state."""
    existing = state.get("existing_profile", {})

    if step == ConversationStep.NAME_CAPTURE:
        return bool(state.get("name"))

    if step == ConversationStep.PERSONAL_INFO:
        # Skip only if ALL four values already known from a prior session.
        return bool(
            existing.get("height_cm")
            and existing.get("weight_kg")
            and existing.get("age")
            and existing.get("sex")
        )

    # GOAL, FITNESS_LEVEL, EXTRA_DETAILS, GOODBYE never skip.
    return False


def get_first_step(state: Dict[str, Any]) -> ConversationStep:
    """Return the first step that should not be skipped."""
    for step in STEP_ORDER:
        if step == ConversationStep.GOODBYE:
            break
        if not _should_skip(step, state):
            return step
    return ConversationStep.GOODBYE


def get_next_step(
    current_step: ConversationStep, state: Dict[str, Any]
) -> ConversationStep:
    """Return the next non-skipped step after current_step.

    Legacy steps not in STEP_ORDER gracefully fall through to GOODBYE so old
    tool invocations don't raise ValueError.
    """
    if current_step in STEP_ORDER:
        idx = STEP_ORDER.index(current_step)
        for step in STEP_ORDER[idx + 1:]:
            if not _should_skip(step, state):
                return step
    return ConversationStep.GOODBYE


def get_first_missing_step(missing_params: list[str]) -> Optional[ConversationStep]:
    """Given a list of missing program_creation keys, return the earliest step
    in the flow that would capture one of them."""
    for step in STEP_ORDER:
        for param, param_step in _PARAM_TO_STEP.items():
            if param in missing_params and param_step == step:
                return step
    return None


# ── Per-step prompt bodies ───────────────────────────────────────────────

def _name_line(state: Dict[str, Any]) -> str:
    name = state.get("name")
    if name:
        return f"You are talking to {name}.\n"
    return ""


def _step_body(step: ConversationStep, state: Dict[str, Any]) -> str:
    """Return the step-specific prompt body."""
    name = state.get("name", "the user")
    existing = state.get("existing_profile", {})
    program = state.get("program_creation", {})

    if step == ConversationStep.NAME_CAPTURE:
        return (
            "The user just joined. Ask for their first name if they haven't already said it.\n"
            "Spell their name letter by letter separated by hyphens to confirm, "
            "for example: S-A-R-A-H, Sarah.\n"
            "If they correct the spelling, ask them to spell it out for you letter by letter.\n"
            "Once confirmed, use capture_name(first_name)."
        )

    if step == ConversationStep.PERSONAL_INFO:
        # Figure out which of the four required fields we still need.
        field_labels = [
            ("age", "age"),
            ("sex", "biological sex"),
            ("height_cm", "height"),
            ("weight_kg", "weight"),
        ]
        known = [label for field, label in field_labels if existing.get(field)]
        needed = [label for field, label in field_labels if not existing.get(field)]

        known_note = f"You already know their {', '.join(known)}. " if known else ""
        needed_str = ", ".join(needed) if needed else "age, biological sex, height, and weight"

        return (
            f"{_name_line(state)}"
            f"{known_note}"
            f"Ask the user to tell you a little about themselves. "
            f"You need to collect: {needed_str}. "
            "Keep it warm and conversational -- for example: "
            "\"Awesome -- tell me a bit about yourself! I need your age, height, weight, "
            "and whether you're male or female. Feel free to add anything else you'd like me to know.\"\n"
            "\n"
            "Listen carefully and extract all the required values from their response. "
            "If they share anything extra beyond the required fields (training background, life context, "
            "personal goals, anything at all), capture that verbatim as the extra_info argument.\n"
            "\n"
            "When you have all the required values, call "
            "capture_personal_info(age, sex, height_value, weight_value, extra_info). "
            'Pass extra_info as "none" if they did not share anything beyond the required fields.\n'
            "\n"
            "IMPORTANT: If some required values are missing from their response, the tool will tell you "
            "which ones. Ask specifically and ONLY for the missing ones. Do NOT re-ask for values they "
            "already gave you. Do NOT advance until all required values are captured."
        )

    if step == ConversationStep.GOAL:
        return (
            f"{_name_line(state)}"
            "Ask about their main fitness goal -- building muscle, getting stronger, "
            "improving athleticism, or something else. Encourage detail: "
            "\"So, what are you looking to achieve? Give me as much detail as you want -- "
            "the more I know, the better program I can build for you. If you already have "
            "specifics in mind, like how long you want the program or how many days a week "
            "you can train, just tell me now.\"\n"
            "\n"
            "Listen for any of these OPTIONAL details in their response and pass them to the tool "
            "if mentioned (otherwise pass None):\n"
            "- duration_weeks: program length in weeks (e.g., 'six week program' -> 6)\n"
            "- days_per_week: training frequency (e.g., 'four days a week' -> 4)\n"
            "- session_duration: minutes per session (e.g., '45 minutes' -> 45)\n"
            "- injury_history: any injuries or limitations mentioned\n"
            "- specific_sport: sport name if they're training for one\n"
            "- training_season: off_season, pre_season, in_season, or post_season\n"
            "- games_per_week: games or competitions per week\n"
            "\n"
            "Call capture_goal_and_details(goal_description, ...) with the full goal description "
            "and any optional params the user mentioned. Pass None for anything they did NOT mention "
            "-- defaults will be applied later."
        )

    if step == ConversationStep.FITNESS_LEVEL:
        return (
            f"{_name_line(state)}"
            "Ask how they would describe their fitness level: "
            "beginner, intermediate, or advanced.\n"
            "Use capture_fitness_level(fitness_level)."
        )

    if step == ConversationStep.EXTRA_DETAILS:
        # Build a short summary of what's already set so Nova knows the state.
        already_set = []
        if program.get("duration_weeks"):
            already_set.append(f"duration {program['duration_weeks']} weeks")
        if program.get("days_per_week"):
            already_set.append(f"{program['days_per_week']} days per week")
        if program.get("session_duration"):
            already_set.append(f"{program['session_duration']} minute sessions")
        if program.get("injury_history") and program["injury_history"] not in ("none", ""):
            already_set.append(f"injuries: {program['injury_history']}")
        if program.get("specific_sport") and program["specific_sport"] not in ("none", ""):
            already_set.append(f"sport: {program['specific_sport']}")

        already_note = (
            f"Already captured from earlier in the conversation: {', '.join(already_set)}. "
            if already_set else ""
        )

        return (
            f"{_name_line(state)}"
            f"{already_note}"
            "Briefly ask if they want to customize anything else, or just go with the "
            "recommended defaults. Keep it short and open-ended -- for example: "
            "\"Anything else you want to tweak, or should I go with the defaults?\"\n"
            "\n"
            "DO NOT proactively list what's customizable unless they explicitly ask "
            "\"what can I change?\" or similar. If they ask, then mention: days per week, "
            "session length, injuries, specific sport, training season, games per week.\n"
            "\n"
            "If they say anything like \"defaults\", \"sounds good\", \"go for it\", \"whatever "
            "you recommend\", or similar affirmation, call apply_defaults(use_defaults=true).\n"
            "\n"
            "If they offer customizations, capture them directly in the tool call: "
            "apply_defaults(use_defaults=false, days_per_week=..., session_duration=..., "
            "injury_history=..., specific_sport=..., training_season=..., games_per_week=...). "
            "Pass None for any field they did not mention -- defaults fill the gaps.\n"
            "\n"
            "IMPORTANT: You MUST call apply_defaults to finish. Do not skip this step."
        )

    if step == ConversationStep.GOODBYE:
        return (
            f"{_name_line(state)}"
            f"You have all the information. Enthusiastically tell {name} you have everything you need.\n"
            "Thank them. Let them know they will receive their program via email within "
            "five minutes -- check inbox and spam folder.\n"
            "Do not ask any more questions. Do not use any tools. Just say goodbye."
        )

    # Legacy step bodies -- kept minimal since the new flow never routes here.
    # If an old @function_tool is invoked and advances into one of these, the
    # prompt just tells the LLM to move on.
    return (
        f"{_name_line(state)}"
        "Continue the conversation and capture any remaining program parameters."
    )


# ── Public API ───────────────────────────────────────────────────────────

def get_step_prompt(step: ConversationStep, state: Dict[str, Any]) -> str:
    """Build the full system prompt for a given conversation step."""
    body = _step_body(step, state)
    return f"{_BASE_CONTEXT}\n\n{body}"

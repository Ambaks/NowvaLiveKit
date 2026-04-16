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

TOOL CALLING RULES:
- As soon as you have the information for the current step, call the matching tool IMMEDIATELY in the same turn. Do NOT respond with text only.
- NEVER ask about equipment, equipment tier, or gym setup. Equipment is always handled automatically.
- When the user says "defaults", "sounds good", "go for it", or any agreement, call apply_defaults(use_defaults=true) RIGHT AWAY. Do not ask follow-up questions.
- If the user wants to CHANGE a previously captured value (e.g. "actually make it a strength program", "I'm 26 not 25", "change my weight to 200 pounds"), call correct_previous_answer(field=..., new_value=...) IMMEDIATELY, then continue with the current step.

With this in context, act upon the following scenario:"""



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
            "You need to collect the user's first name.\n"
            "\n"
            "CRITICAL RULES (follow in order every turn):\n"
            "1. SCAN the conversation history. If the user has ALREADY said their first name "
            "in a previous message, treat it as collected -- do NOT ask again.\n"
            "2. Once you have a name, spell it letter by letter separated by hyphens to confirm "
            "(e.g. S-A-R-A-H, Sarah). If they confirm or don't correct it, "
            "call capture_name(first_name=...) IMMEDIATELY.\n"
            "3. If they correct the spelling, ask them to spell it out letter by letter, then "
            "call capture_name with the corrected spelling.\n"
            "4. If no name has been mentioned yet, greet them warmly and ask for their first name.\n"
            "\n"
            "FIRST-TURN EXAMPLE (only if no name mentioned yet):\n"
            "\"Hey there! Nice to meet you! What's your first name?\"\n"
            "\n"
            "NEVER re-ask for a name the user already provided. "
            "Your #1 priority is calling capture_name as soon as the name is confirmed."
        )

    if step == ConversationStep.PERSONAL_INFO:
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
            f"{known_note}"
            f"You need to collect four values: {needed_str}.\n"
            "\n"
            "CRITICAL RULES (follow in order every turn):\n"
            "1. SCAN the conversation history. If the user has ALREADY stated any of the four values "
            "(age, sex, height, weight) in a previous message, treat those as collected. "
            "Do NOT ask for them again -- ever.\n"
            "2. If you now have all four values (from this turn, previous turns, or a mix), "
            "call capture_personal_info(...) IMMEDIATELY in this turn. Include any extra context "
            'they shared (training background, life situation, etc.) or "none".\n'
            "3. If some values are still missing, ask ONLY for the missing ones in a short, "
            "specific follow-up. Never repeat the full question.\n"
            "\n"
            "FIRST-TURN EXAMPLE (only if you haven't asked yet):\n"
            "\"Awesome -- tell me a bit about yourself! I need your age, height, weight, "
            "and whether you're male or female. Feel free to add anything else you'd like me to know.\"\n"
            "\n"
            "FOLLOW-UP EXAMPLE (if only weight is missing):\n"
            "\"Got it! And how much do you weigh?\"\n"
            "\n"
            "NEVER re-ask for values the user already provided. "
            "Your #1 priority is calling capture_personal_info as soon as all four values are available."
        )

    if step == ConversationStep.GOAL:
        return (
            "You need to collect the user's main fitness goal (required). "
            "You should also passively listen for optional details but NEVER ask for them.\n"
            "\n"
            "CRITICAL RULES (follow in order every turn):\n"
            "1. SCAN the conversation history. If the user has ALREADY described their goal "
            "in a previous message, treat it as collected -- do NOT ask again.\n"
            "2. If you have a goal description (from this turn or a previous one), "
            "call capture_goal_and_details(goal_description=...) IMMEDIATELY. "
            "Include any optional details they happened to mention; leave everything else unset.\n"
            "3. If no goal has been mentioned yet, ask them in a warm, open-ended way.\n"
            "\n"
            "OPTIONAL DETAILS (include if mentioned, never ask for them):\n"
            "- program length in weeks (e.g. 'six week program' -> 6)\n"
            "- training frequency in days per week (e.g. 'four days a week' -> 4)\n"
            "- session duration in minutes (e.g. '45 minutes' -> 45)\n"
            "- injuries or limitations\n"
            "- specific sport\n"
            "- training season: off_season, pre_season, in_season, or post_season\n"
            "- games or competitions per week\n"
            "\n"
            "FIRST-TURN EXAMPLE (only if no goal mentioned yet):\n"
            "\"So, what are you looking to achieve? Give me as much detail as you want -- "
            "the more I know, the better program I can build for you.\"\n"
            "\n"
            "NEVER re-ask for a goal the user already described. "
            "Your #1 priority is calling capture_goal_and_details as soon as you have a goal."
        )

    if step == ConversationStep.FITNESS_LEVEL:
        return (
            "You need to collect the user's fitness level: beginner, intermediate, or advanced.\n"
            "\n"
            "CRITICAL RULES (follow in order every turn):\n"
            "1. SCAN the conversation history. If the user has ALREADY indicated their fitness level "
            "(or something clearly equivalent like \"I'm new to this\" or \"I've been lifting for years\"), "
            "treat it as collected -- do NOT ask again.\n"
            "2. If you have their fitness level (from this turn or a previous one), "
            "call capture_fitness_level(fitness_level=...) IMMEDIATELY.\n"
            "3. If no fitness level has been mentioned yet, ask them in a short, direct way.\n"
            "\n"
            "FIRST-TURN EXAMPLE (only if not yet mentioned):\n"
            "\"How would you describe your fitness level -- beginner, intermediate, or advanced?\"\n"
            "\n"
            "NEVER re-ask for a fitness level the user already provided. "
            "Your #1 priority is calling capture_fitness_level as soon as you have an answer."
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
            f"{already_note}"
            "You need to find out if the user wants to customize anything or go with defaults.\n"
            "\n"
            "CRITICAL RULES (follow in order every turn):\n"
            "1. SCAN the conversation history. If the user has ALREADY responded to the "
            "\"defaults or customize?\" question (e.g. \"sounds good\", \"go with defaults\", "
            "or gave specific customizations), act on that answer -- do NOT ask again.\n"
            "2. If the user agreed to defaults (\"sounds good\", \"go for it\", \"nah\", "
            "\"I'm good\", \"whatever you recommend\", or any agreement):\n"
            "   -> Call apply_defaults(use_defaults=true) IMMEDIATELY. No follow-up questions.\n"
            "3. If the user gave specific customizations (e.g. \"four days a week\", \"I have a bad knee\"):\n"
            "   -> Call apply_defaults(use_defaults=false, ...) with their values IMMEDIATELY.\n"
            "4. If the user hasn't been asked yet, ask briefly and open-endedly.\n"
            "\n"
            "FIRST-TURN EXAMPLE (only if not yet asked):\n"
            "\"Anything else you want to tweak, or should I go with the defaults?\"\n"
            "\n"
            "If the user asks \"what can I change?\", mention: days per week, "
            "session length, injuries, specific sport, training season, games per week.\n"
            "NEVER mention equipment or gym setup -- that is handled automatically.\n"
            "\n"
            "NEVER re-ask a question the user already answered. "
            "Your #1 priority is calling apply_defaults as soon as the user responds."
        )

    if step == ConversationStep.GOODBYE:
        return (
            f"You have all the information. Enthusiastically tell the user you have everything you need.\n"
            "Thank them. Let them know they will receive their program via email within "
            "five minutes -- check inbox and spam folder.\n"
            "Do not ask any more questions. Do not use any tools. Just say goodbye."
        )

    # Legacy step bodies -- kept minimal since the new flow never routes here.
    # If an old @function_tool is invoked and advances into one of these, the
    # prompt just tells the LLM to move on.
    return (
        "Continue the conversation and capture any remaining program parameters."
    )


# ── Public API ───────────────────────────────────────────────────────────

def get_step_prompt(step: ConversationStep, state: Dict[str, Any]) -> str:
    """Build the full system prompt for a given conversation step."""
    body = _step_body(step, state)
    return f"{_BASE_CONTEXT}\n\n{body}"

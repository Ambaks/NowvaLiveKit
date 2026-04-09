"""
Step-scoped prompts for the website voice agent.

Each conversation step gets a focused prompt (~100-150 tokens) instead of
one monolithic ~2800-token blob. This reduces TTFT on Groq, eliminates
instruction drift on Llama 3.3, and keeps each LLM turn laser-focused
on a single question.
"""

from enum import Enum
from typing import Dict, Any, Optional


class ConversationStep(Enum):
    NAME_CAPTURE = "name_capture"
    HEIGHT_WEIGHT = "height_weight"
    AGE_SEX = "age_sex"
    GOAL = "goal"
    DURATION = "duration"
    FREQUENCY = "frequency"
    SESSION_DURATION = "session_duration"
    INJURIES = "injuries"
    SPORT = "sport"
    TRAINING_SEASON = "training_season"
    GAMES_PER_WEEK = "games_per_week"
    NOTES = "notes"
    EQUIPMENT = "equipment"
    FITNESS_LEVEL = "fitness_level"
    GOODBYE = "goodbye"


# Ordered list of all steps in the default conversation flow.
STEP_ORDER = [
    ConversationStep.NAME_CAPTURE,
    ConversationStep.HEIGHT_WEIGHT,
    ConversationStep.AGE_SEX,
    ConversationStep.GOAL,
    ConversationStep.DURATION,
    ConversationStep.FREQUENCY,
    ConversationStep.SESSION_DURATION,
    ConversationStep.INJURIES,
    ConversationStep.SPORT,
    ConversationStep.TRAINING_SEASON,
    ConversationStep.GAMES_PER_WEEK,
    ConversationStep.NOTES,
    ConversationStep.EQUIPMENT,
    ConversationStep.FITNESS_LEVEL,
    ConversationStep.GOODBYE,
]

# Mapping from missing program_creation keys to the step that captures them.
_PARAM_TO_STEP = {
    "height_cm": ConversationStep.HEIGHT_WEIGHT,
    "weight_kg": ConversationStep.HEIGHT_WEIGHT,
    "age": ConversationStep.AGE_SEX,
    "sex": ConversationStep.AGE_SEX,
    "goal_category": ConversationStep.GOAL,
    "goal_raw": ConversationStep.GOAL,
    "duration_weeks": ConversationStep.DURATION,
    "days_per_week": ConversationStep.FREQUENCY,
    "fitness_level": ConversationStep.FITNESS_LEVEL,
}

# ── Base context prepended to every step ─────────────────────────────────

_BASE_CONTEXT = """\
You are Nova, a friendly, energetic and expressive AI fitness coach helping the user create a personalized workout program.
Always respond in English. Keep responses brief.
You are actively having a conversation with the user. Act like a human being. NEVER call out function names out loud.
Make sure to use natural punctuation for pacing ("...", "!", ",", "--", "?"). No markdown, no special characters, no emoji.
Use filler words to sound more natural: "like...", "ummm...", "...uhhh...", "let me see..."
If the user goes off-topic, conversate briefly, then redirect to the current question.

With this in context, create a response to the following scenario:"""



# ── Skip logic ───────────────────────────────────────────────────────────

def _should_skip(step: ConversationStep, state: Dict[str, Any]) -> bool:
    """Return True if this step should be skipped given current state."""
    existing = state.get("existing_profile", {})
    program = state.get("program_creation", {})

    if step == ConversationStep.NAME_CAPTURE:
        return bool(state.get("name"))

    if step == ConversationStep.HEIGHT_WEIGHT:
        return bool(existing.get("height_cm") and existing.get("weight_kg"))

    if step == ConversationStep.AGE_SEX:
        return bool(existing.get("age") and existing.get("sex"))

    if step == ConversationStep.TRAINING_SEASON:
        sport = program.get("specific_sport", "").lower()
        return sport in ("none", "general", "general fitness", "") or not sport

    if step == ConversationStep.GAMES_PER_WEEK:
        season = program.get("training_season", "")
        return season != "in_season"

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
    """Return the next non-skipped step after current_step."""
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
        return f"Name already captured.\n"
    return ""


def _step_body(step: ConversationStep, state: Dict[str, Any]) -> str:
    """Return the step-specific prompt body."""
    name = state.get("name", "the user")
    program = state.get("program_creation", {})

    if step == ConversationStep.NAME_CAPTURE:
        return (
            "The user just joined. Ask for their first name if they haven't already said it.\n"
            "Spell their name letter by letter separated by hyphens to confirm, "
            "for example: S-A-R-A-H, Sarah.\n"
            "If they correct the spelling, ask them to spell it out for you letter by letter."
            "Once confirmed, use capture_name(first_name).\n"

        )

    if step == ConversationStep.HEIGHT_WEIGHT:
        return (
            f"{_name_line(state)}"
            "The user just told you their name, and you must now get their height and weight."
            "Ask for their height and weight. Accept any format -- "
            "Use capture_height_weight(height_value, weight_value) with their answer."
        )

    if step == ConversationStep.AGE_SEX:
        return (
            f"{_name_line(state)}"
            "Ask the user for their age and biological sex.\n"
            "Use capture_age_sex(age, sex) with their answer."
        )

    if step == ConversationStep.GOAL:
        return (
            f"{_name_line(state)}"
            "You need to ask the user what their main fitness goal is -- building muscle, getting stronger, "
            "improving athleticism, or something else.\n"
            "Use capture_goal(goal_description) with their answer."
        )

    if step == ConversationStep.DURATION:
        goal = program.get("goal_category", "their goal")
        rec = program.get("recommended_duration", 12)
        return (
            f"{_name_line(state)}"
            f"Ask the user how many weeks they want their program to be."
            f"Recommend {rec} weeks for their goal.\n"
            "Valid range is two to fifty-two weeks."
            "Use capture_program_duration(duration_weeks). "
        )

    if step == ConversationStep.FREQUENCY:
        return (
            f"{_name_line(state)}"
            "Ask how many days per week they can train. "
            "Valid range is one to seven.\n"
            "Use capture_training_frequency(days_per_week)."
        )

    if step == ConversationStep.SESSION_DURATION:
        return (
            f"{_name_line(state)}"
            "Ask how long they can spend per training session. "
            "This is optional -- if they say standard or normal, use sixty minutes.\n"
            "Range is thirty to one hundred eighty minutes."           
            "Use capture_session_duration(duration_minutes). "
        )

    if step == ConversationStep.INJURIES:
        return (
            f"{_name_line(state)}"
            "Ask if they have any injuries or physical limitations to work around. "
            "If none, that is fine.\n"
            "Use capture_injury_history(injury_description)."
        )

    if step == ConversationStep.SPORT:
        return (
            f"{_name_line(state)}"
            "Ask if they are training for a specific sport, or if this is general fitness.\n"
            'Use capture_specific_sport(sport_name). Use "none" if general fitness.'
        )

    if step == ConversationStep.TRAINING_SEASON:
        sport = program.get("specific_sport", "their sport")
        return (
            f"{_name_line(state)}"
            f"They play {sport}.\n"
            "Ask what part of the season they are in: "
            "off-season, pre-season, in-season, or post-season.\n"
            "Use capture_training_season(training_season)."
        )

    if step == ConversationStep.GAMES_PER_WEEK:
        return (
            f"{_name_line(state)}"
            "They are in-season.\n"
            "Ask how many games or competitions they have per week.\n"
            "Use capture_games_per_week(games_per_week). Range is zero to seven."
        )

    if step == ConversationStep.NOTES:
        return (
            f"{_name_line(state)}"
            "Ask if they have any additional preferences or notes -- "
            "exercise preferences, schedule constraints, or anything else.\n"
            'Use capture_user_notes(notes). Use "none" if nothing additional.'
        )

    if step == ConversationStep.EQUIPMENT:
        return (
            f"{_name_line(state)}"
            "Ask about their equipment access. Explain the tiers briefly:\n"
            "Tier one is a standard barbell and rack."
            "Tier two adds dumbbells. Tier three adds bands.\n"
            "Use capture_equipment_tier(equipment_tier) with one, two, or three."
        )

    if step == ConversationStep.FITNESS_LEVEL:
        return (
            f"{_name_line(state)}"
            "This is the last question. Ask how they would describe their fitness level: "
            "beginner, intermediate, or advanced.\n"
            "Use capture_fitness_level(fitness_level)."
        )

    if step == ConversationStep.GOODBYE:
        return (
            f"{_name_line(state)}"
            f"You have all the information. Enthusiastically tell {name} you have everything you need.\n"
            "Thank them. Let them know they will receive their program via email within "
            "five minutes -- check inbox and spam folder.\n"
            "Do not ask any more questions. Do not use any tools. Just say goodbye."
        )

    return ""


# ── Public API ───────────────────────────────────────────────────────────

def get_step_prompt(step: ConversationStep, state: Dict[str, Any]) -> str:
    """Build the full system prompt for a given conversation step."""
    body = _step_body(step, state)
    return f"{_BASE_CONTEXT}\n\n{body}"

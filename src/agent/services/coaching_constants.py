"""Shared coaching constants: the Nova persona and the cue key registry.

Cue keys are emitted by biomechanics.coaching.cue_cache. CUE_TEXT_MAP holds
the exact spoken strings that pre-generated TTS audio is cached against —
do not reword them without regenerating the audio. CUE_DISPLAY_LABELS holds
the short labels shown in set reports.
"""

from __future__ import annotations

# Persona prepended to all coaching LLM instructions.
COACHING_PERSONA = (
    "You are Nova, an energetic, world-class fitness coach on the Nowva smart squat rack. "
    "HIGH energy, motivating, supportive. SHORT responses only — follow the word limits given. "
    "Sound like a real coach in the gym — keep it human."
)

# Number words for rep cues
_NUMBER_WORDS = {
    1: "One!", 2: "Two!", 3: "Three!", 4: "Four!", 5: "Five!",
    6: "Six!", 7: "Seven!", 8: "Eight!", 9: "Nine!", 10: "Ten!",
    11: "Eleven!", 12: "Twelve!", 13: "Thirteen!", 14: "Fourteen!", 15: "Fifteen!",
    16: "Sixteen!", 17: "Seventeen!", 18: "Eighteen!", 19: "Nineteen!", 20: "Twenty!",
}

# Cue key → spoken text mapping (cached TTS audio exists for these exact strings)
CUE_TEXT_MAP: dict[str, str] = {
    # Squat corrections
    "knees_out": "Knees out!",
    "chest_up": "Chest up!",
    "deeper": "Get deeper!",
    "heels_down": "Heels down!",
    "even_it_out": "Even it out!",
    "slow_down": "Slow down!",
    "brace": "Brace your core!",
    # Deadlift corrections
    "hips_through": "Hips through!",
    "flat_back": "Flat back!",
    "lockout": "Lock it out!",
    # Positive reinforcement
    "good_rep": "Good rep!",
    "great_depth": "Great depth!",
    "strong": "Strong!",
    "clean": "Clean!",
    "perfect": "Perfect!",
    # Rep counts
    **{f"rep_{i}": _NUMBER_WORDS[i] for i in range(1, 21)},
}

# Cue key → human-readable label for set reports (rep_* labels are built inline)
CUE_DISPLAY_LABELS: dict[str, str] = {
    "knees_out": "Knees out!",
    "chest_up": "Chest up!",
    "deeper": "Go deeper!",
    "heels_down": "Heels down!",
    "even_it_out": "Even it out!",
    "slow_down": "Slow down!",
    "brace": "Brace core!",
    "hips_through": "Hips through!",
    "flat_back": "Flat back!",
    "lockout": "Lock it out!",
    "good_rep": "Good rep!",
    "great_depth": "Great depth!",
    "strong": "Strong!",
    "clean": "Clean!",
    "perfect": "Perfect!",
}

"""
Nova voice agent prompts module
"""

from .onboarding_prompt import ONBOARDING_PROMPT
from .main_menu_prompt import get_main_menu_prompt
from .workout_prompt import get_workout_prompt
from .program_creation_prompt import get_program_creation_prompt

__all__ = [
    "ONBOARDING_PROMPT",
    "get_main_menu_prompt",
    "get_workout_prompt",
    "get_program_creation_prompt",
]

"""
V5 Program Generator Package

Entry points:
- generate_program_v5() - Async main entry point
- generate_program_v5_sync() - Synchronous wrapper for testing
"""

from .main import generate_program_v5, generate_program_v5_sync
from .layer6_serializer import serialize_to_v3, serialize_to_markdown, serialize_summary
from .schemas import (
    AthleteProfile,
    BuiltProgram,
    ProgramStrategy,
    EquipmentTier,
)

__all__ = [
    "generate_program_v5",
    "generate_program_v5_sync",
    "serialize_to_v3",
    "serialize_to_markdown",
    "serialize_summary",
    "AthleteProfile",
    "BuiltProgram",
    "ProgramStrategy",
    "EquipmentTier",
]

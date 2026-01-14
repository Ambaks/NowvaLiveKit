"""
Phase mapping and interpolation service for program generation.

Handles intelligent phase planning for any program duration up to 12 weeks:
- Exact template matches (4, 8, 12 weeks)
- Proportional interpolation for non-standard durations (3-12 weeks)
- Edge cases: 1-2 weeks (goal-aware simplified)
- Smart deload placement with override rules

For programs longer than 12 weeks, use the 12-week template and let the LLM
naturally extend/repeat patterns during generation.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict

from ..config.phase_templates import (
    PhaseBlock,
    PhaseTemplate,
    get_template,
    get_closest_template,
)


@dataclass
class MappedPhase:
    """A phase mapped to a specific week in the program."""
    week_number: int
    phase_name: str
    sets_x_reps: str
    intensity_range: str
    rest_period: str
    volume_adjustment: str
    exercise_selection: str
    notes: Optional[str] = None


class PhaseMapper:
    """
    Maps phase templates to program durations with intelligent interpolation.

    Handles:
    - 1-2 weeks: Goal-aware simple guidance (no real periodization)
    - 3-12 weeks: Proportional interpolation from closest template
    - Smart deload placement with conflict resolution

    For programs >12 weeks, caller should use the 12-week template.
    """

    def __init__(self, goal: str, duration_weeks: int, params: Optional[Dict] = None):
        """
        Initialize phase mapper.

        Args:
            goal: Training goal (hypertrophy, strength, power, athletic_performance)
            duration_weeks: Target program duration (1-12 weeks recommended)
            params: Optional program parameters for context
        """
        self.goal = goal.lower()
        self.duration_weeks = min(duration_weeks, 12)  # Cap at 12 weeks
        self.params = params or {}
        self.phase_schedule: List[MappedPhase] = []

        # Build the phase schedule
        self._build_phase_schedule()

    def _build_phase_schedule(self):
        """Build complete phase schedule based on duration."""
        if self.duration_weeks <= 2:
            self._handle_very_short_program()
        else:
            self._handle_standard_program()

    def _handle_very_short_program(self):
        """
        Handle 1-2 week programs with goal-aware simple guidance.

        No real periodization possible, but guidance should match goal.
        """
        if self.duration_weeks == 1:
            self._create_single_week_program()
        else:  # 2 weeks
            self._create_two_week_program()

    def _create_single_week_program(self):
        """Create goal-specific single week program."""
        if self.goal == "hypertrophy":
            self.phase_schedule.append(MappedPhase(
                week_number=1,
                phase_name="Hypertrophy Block",
                sets_x_reps="4x10-12",
                intensity_range="70-75%",
                rest_period="60-90s",
                volume_adjustment="Moderate volume",
                exercise_selection="Variety emphasis, metabolic stress",
                notes="Single week hypertrophy - focus on volume and metabolic stress"
            ))

        elif self.goal == "strength":
            self.phase_schedule.append(MappedPhase(
                week_number=1,
                phase_name="Strength Block",
                sets_x_reps="5x5",
                intensity_range="80-85%",
                rest_period="3-4min",
                volume_adjustment="Moderate volume",
                exercise_selection="Competition lifts focus",
                notes="Single week strength - maintain high intensity"
            ))

        elif self.goal == "power":
            self.phase_schedule.append(MappedPhase(
                week_number=1,
                phase_name="Power Block",
                sets_x_reps="5x3 explosive",
                intensity_range="75-85%",
                rest_period="3-4min",
                volume_adjustment="Moderate volume",
                exercise_selection="Olympic lifts, explosive movements, plyometrics",
                notes="Single week power - explosive intent, quality over quantity"
            ))

        else:  # athletic_performance
            self.phase_schedule.append(MappedPhase(
                week_number=1,
                phase_name="Athletic Performance Block",
                sets_x_reps="4x5 + explosive work",
                intensity_range="75-85%",
                rest_period="2-4min",
                volume_adjustment="Moderate volume",
                exercise_selection="Concurrent: strength + power in same sessions",
                notes="Single week athletic performance - train multiple qualities"
            ))

    def _create_two_week_program(self):
        """Create goal-specific two week program."""
        if self.goal == "hypertrophy":
            self.phase_schedule.extend([
                MappedPhase(
                    week_number=1,
                    phase_name="Hypertrophy Accumulation",
                    sets_x_reps="4x10-12",
                    intensity_range="70-75%",
                    rest_period="60-90s",
                    volume_adjustment="Normal",
                    exercise_selection="High variety, isolation work",
                    notes="Build volume and metabolic stress"
                ),
                MappedPhase(
                    week_number=2,
                    phase_name="Hypertrophy Intensification",
                    sets_x_reps="4x8-10",
                    intensity_range="75-80%",
                    rest_period="90s",
                    volume_adjustment="Moderate",
                    exercise_selection="Compound emphasis",
                    notes="Increase mechanical tension"
                ),
            ])

        elif self.goal == "strength":
            self.phase_schedule.extend([
                MappedPhase(
                    week_number=1,
                    phase_name="Strength Accumulation",
                    sets_x_reps="5x5",
                    intensity_range="80-85%",
                    rest_period="3-4min",
                    volume_adjustment="Normal",
                    exercise_selection="Competition lifts + variations",
                    notes="Build strength base"
                ),
                MappedPhase(
                    week_number=2,
                    phase_name="Strength Intensification",
                    sets_x_reps="5x3",
                    intensity_range="85-90%",
                    rest_period="4min",
                    volume_adjustment="Moderate",
                    exercise_selection="Competition lifts focus",
                    notes="Peak intensity"
                ),
            ])

        elif self.goal == "power":
            self.phase_schedule.extend([
                MappedPhase(
                    week_number=1,
                    phase_name="Power Development",
                    sets_x_reps="5x3 explosive",
                    intensity_range="75-85%",
                    rest_period="3-4min",
                    volume_adjustment="Normal",
                    exercise_selection="Olympic lifts, jumps, throws",
                    notes="Develop explosive power"
                ),
                MappedPhase(
                    week_number=2,
                    phase_name="Power Expression",
                    sets_x_reps="4x2 explosive",
                    intensity_range="85-90%",
                    rest_period="4-5min",
                    volume_adjustment="Moderate",
                    exercise_selection="Sport-specific power movements",
                    notes="Express peak power"
                ),
            ])

        else:  # athletic_performance
            self.phase_schedule.extend([
                MappedPhase(
                    week_number=1,
                    phase_name="Concurrent Development",
                    sets_x_reps="4x5 + 4x3 explosive",
                    intensity_range="75-85%",
                    rest_period="2-4min",
                    volume_adjustment="Normal",
                    exercise_selection="Strength + power concurrent training",
                    notes="Train multiple qualities simultaneously"
                ),
                MappedPhase(
                    week_number=2,
                    phase_name="Athletic Expression",
                    sets_x_reps="3x3 + sport-specific",
                    intensity_range="80-90%",
                    rest_period="3-4min",
                    volume_adjustment="Moderate",
                    exercise_selection="Sport-specific power + strength",
                    notes="Express athletic qualities"
                ),
            ])

    def _handle_standard_program(self):
        """Handle 3-12 week programs with interpolation from closest template."""
        # Check for exact template match
        exact_template = get_template(self.goal, self.duration_weeks)
        if exact_template:
            self._apply_template_with_deload_override(exact_template)
        else:
            # Interpolate from closest template
            self._interpolate_from_template()

    def _apply_template_with_deload_override(self, template: PhaseTemplate):
        """Apply template directly but with smart deload override rules."""
        temp_schedule = []

        # First pass: create schedule from template
        for phase in template.phases:
            for week in range(phase.week_start, phase.week_end + 1):
                temp_schedule.append(MappedPhase(
                    week_number=week,
                    phase_name=phase.name,
                    sets_x_reps=phase.sets_x_reps,
                    intensity_range=phase.intensity_range,
                    rest_period=phase.rest_period,
                    volume_adjustment=phase.volume_adjustment,
                    exercise_selection=phase.exercise_selection,
                    notes=phase.notes
                ))

        # Second pass: apply deload override rules
        self.phase_schedule = self._apply_deload_override(temp_schedule)

    def _interpolate_from_template(self):
        """Interpolate phases from closest template to target duration."""
        # Get closest template for interpolation
        base_template = get_closest_template(self.goal, self.duration_weeks)

        # Calculate scaling factor
        scale_factor = self.duration_weeks / base_template.duration_weeks

        # Map each phase proportionally
        temp_schedule = []
        current_week = 1

        for phase in base_template.phases:
            phase_duration = phase.week_end - phase.week_start + 1
            scaled_duration = max(1, round(phase_duration * scale_factor))

            # Ensure we don't exceed target duration
            if current_week + scaled_duration - 1 > self.duration_weeks:
                scaled_duration = self.duration_weeks - current_week + 1

            # Add scaled phase to schedule
            for week_offset in range(scaled_duration):
                week_num = current_week + week_offset
                if week_num <= self.duration_weeks:
                    temp_schedule.append(MappedPhase(
                        week_number=week_num,
                        phase_name=phase.name,
                        sets_x_reps=phase.sets_x_reps,
                        intensity_range=phase.intensity_range,
                        rest_period=phase.rest_period,
                        volume_adjustment=phase.volume_adjustment,
                        exercise_selection=phase.exercise_selection,
                        notes=phase.notes
                    ))

            current_week += scaled_duration

            # Stop if we've reached target duration
            if current_week > self.duration_weeks:
                break

        # Apply deload override rules
        self.phase_schedule = self._apply_deload_override(temp_schedule)

    def _apply_deload_override(self, schedule: List[MappedPhase]) -> List[MappedPhase]:
        """
        Apply smart deload override rules.

        Rules:
        - Never deload in final 2 weeks (taper territory)
        - Never deload in week 1
        - If conflicts occur, skip or shift the deload
        - Maintain roughly 3:1 or 4:1 work-to-deload ratio
        """
        final_two_weeks = {self.duration_weeks - 1, self.duration_weeks}

        result = []
        for mapped_phase in schedule:
            # Check if this is a deload that violates rules
            is_deload = "deload" in mapped_phase.phase_name.lower()

            if is_deload:
                # Rule 1: Never deload in week 1
                if mapped_phase.week_number == 1:
                    # Convert to normal training week
                    mapped_phase.phase_name = "Accumulation"
                    mapped_phase.volume_adjustment = "Normal"
                    mapped_phase.notes = "Converted from deload (week 1 rule)"

                # Rule 2: Never deload in final 2 weeks
                elif mapped_phase.week_number in final_two_weeks:
                    # Check if it should be a taper instead
                    if mapped_phase.week_number == self.duration_weeks:
                        mapped_phase.phase_name = "Taper"
                        mapped_phase.notes = "Converted to taper (final week rule)"
                    else:
                        mapped_phase.phase_name = "Peak Prep"
                        mapped_phase.volume_adjustment = "Moderate reduction (20-30%)"
                        mapped_phase.notes = "Modified deload (near end of program)"

            result.append(mapped_phase)

        return result

    def get_phase_for_week(self, week_num: int) -> Optional[MappedPhase]:
        """
        Get phase information for a specific week.

        Args:
            week_num: Week number (1-indexed)

        Returns:
            MappedPhase for the week, or None if week not found
        """
        for phase in self.phase_schedule:
            if phase.week_number == week_num:
                return phase
        return None

    def get_phases_for_batch(self, start_week: int, end_week: int) -> List[MappedPhase]:
        """
        Get phases for a batch of weeks (for batch generation).

        Args:
            start_week: Start week (1-indexed, inclusive)
            end_week: End week (1-indexed, inclusive)

        Returns:
            List of MappedPhases for the week range
        """
        return [
            phase for phase in self.phase_schedule
            if start_week <= phase.week_number <= end_week
        ]

    def get_deload_schedule_summary(self) -> str:
        """
        Get human-readable deload schedule summary.

        Returns:
            String describing when deloads occur
        """
        deload_weeks = [
            phase.week_number for phase in self.phase_schedule
            if "deload" in phase.phase_name.lower()
        ]

        if not deload_weeks:
            return "No deload weeks scheduled"

        return f"Deload weeks: {', '.join(map(str, deload_weeks))}"

    def get_phase_progression_summary(self) -> str:
        """
        Get high-level phase progression summary.

        Returns:
            String describing overall phase progression
        """
        if self.duration_weeks <= 2:
            return "Very short program - simplified periodization"

        # Group consecutive weeks with same phase
        phase_groups = []
        current_phase_name = None
        current_start = None
        current_end = None

        for phase in self.phase_schedule:
            if phase.phase_name != current_phase_name:
                # Save previous group
                if current_phase_name:
                    if current_start == current_end:
                        phase_groups.append(f"Week {current_start}: {current_phase_name}")
                    else:
                        phase_groups.append(f"Weeks {current_start}-{current_end}: {current_phase_name}")

                # Start new group
                current_phase_name = phase.phase_name
                current_start = phase.week_number
                current_end = phase.week_number
            else:
                current_end = phase.week_number

        # Don't forget last group
        if current_phase_name:
            if current_start == current_end:
                phase_groups.append(f"Week {current_start}: {current_phase_name}")
            else:
                phase_groups.append(f"Weeks {current_start}-{current_end}: {current_phase_name}")

        return " → ".join(phase_groups)

    def get_phase_count(self) -> int:
        """Get total number of distinct phases in the program."""
        return len(set(phase.phase_name for phase in self.phase_schedule))


def plan_program_phases(goal: str, duration_weeks: int, params: Optional[Dict] = None) -> PhaseMapper:
    """
    Convenience function to create a PhaseMapper.

    Args:
        goal: Training goal
        duration_weeks: Program duration
        params: Optional program parameters

    Returns:
        Configured PhaseMapper instance
    """
    return PhaseMapper(goal, duration_weeks, params)

"""
HTML Generator Service
Converts program data to styled HTML for PDF generation using Jinja2 templates.
"""
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Dict, List, Any, Optional
from datetime import datetime

# Get the templates directory path
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'templates')

# Initialize Jinja2 environment
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)


# Color schemes by program type
COLOR_SCHEMES = {
    'power': {
        'primary': '#EF4444',
        'primary_light': '#FCA5A5',
        'primary_dark': '#B91C1C',
        'gradient_start': '#DC2626',
        'gradient_end': '#F59E0B',
        'accent': '#FBBF24',
    },
    'hypertrophy': {
        'primary': '#8B5CF6',
        'primary_light': '#C4B5FD',
        'primary_dark': '#6D28D9',
        'gradient_start': '#7C3AED',
        'gradient_end': '#EC4899',
        'accent': '#A78BFA',
    },
    'strength': {
        'primary': '#3B82F6',
        'primary_light': '#93C5FD',
        'primary_dark': '#1E40AF',
        'gradient_start': '#2563EB',
        'gradient_end': '#0EA5E9',
        'accent': '#60A5FA',
    },
    'endurance': {
        'primary': '#10B981',
        'primary_light': '#6EE7B7',
        'primary_dark': '#047857',
        'gradient_start': '#059669',
        'gradient_end': '#14B8A6',
        'accent': '#34D399',
    },
    'sport': {
        'primary': '#F59E0B',
        'primary_light': '#FCD34D',
        'primary_dark': '#D97706',
        'gradient_start': '#F59E0B',
        'gradient_end': '#EF4444',
        'accent': '#FBBF24',
    }
}


def detect_program_type(goal: str) -> str:
    """
    Detect program type from goal field for color theming.

    Args:
        goal: Program goal string

    Returns:
        Program type: 'power', 'hypertrophy', 'strength', 'endurance', or 'sport'
    """
    goal_lower = goal.lower()

    if any(word in goal_lower for word in ['power', 'explosive', 'vertical', 'speed', 'olympic', 'plyometric']):
        return 'power'
    elif any(word in goal_lower for word in ['hypertrophy', 'muscle', 'size', 'aesthetic', 'bodybuilding', 'growth']):
        return 'hypertrophy'
    elif any(word in goal_lower for word in ['strength', 'powerlifting', '1rm', 'max', 'strong']):
        return 'strength'
    elif any(word in goal_lower for word in ['endurance', 'marathon', 'cardio', 'stamina', 'conditioning']):
        return 'endurance'
    else:
        return 'sport'  # Default for sport-specific


def get_intensity_color(intensity_percent: Optional[float]) -> str:
    """
    Get color for intensity heat-map.

    Args:
        intensity_percent: Intensity percentage (0-100)

    Returns:
        Hex color code
    """
    if not intensity_percent:
        return '#E5E5E5'  # Gray for no intensity

    if intensity_percent >= 90:
        return '#EF4444'  # Red for 90%+
    elif intensity_percent >= 85:
        return '#F59E0B'  # Orange for 85-89%
    elif intensity_percent >= 70:
        return '#FBBF24'  # Yellow for 70-84%
    else:
        return '#34D399'  # Green for <70%


def get_category_badge_color(category: str) -> str:
    """
    Get color for exercise category badge.

    Args:
        category: Exercise category (Strength, Hypertrophy, Power)

    Returns:
        Hex color code
    """
    category_lower = category.lower()

    if 'power' in category_lower:
        return '#EF4444'  # Red
    elif 'hypertrophy' in category_lower:
        return '#8B5CF6'  # Purple
    elif 'strength' in category_lower:
        return '#3B82F6'  # Blue
    else:
        return '#6B7280'  # Gray (default)


def aggregate_program_stats(program_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate statistics about the program.

    Args:
        program_data: Full program data dictionary

    Returns:
        Dictionary of statistics
    """
    total_workouts = 0
    total_exercises = 0
    total_sets = 0
    exercise_frequency = {}
    muscle_groups = {}

    for week in program_data.get('weeks', []):
        for workout in week.get('workouts', []):
            total_workouts += 1
            for exercise in workout.get('exercises', []):
                total_exercises += 1

                # Count exercise frequency
                ex_name = exercise.get('exercise_name', '')
                exercise_frequency[ex_name] = exercise_frequency.get(ex_name, 0) + 1

                # Count muscle groups
                muscle_group = exercise.get('muscle_group', '')
                muscle_groups[muscle_group] = muscle_groups.get(muscle_group, 0) + 1

                # Count sets
                total_sets += len(exercise.get('sets', []))

    return {
        'total_workouts': total_workouts,
        'total_exercises': total_exercises,
        'total_sets': total_sets,
        'exercise_frequency': exercise_frequency,
        'muscle_groups': muscle_groups,
        'unique_exercises': len(exercise_frequency),
    }


def generate_html(
    program_data: Dict[str, Any],
    user_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate HTML for a complete program.

    Args:
        program_data: Full program data including weeks, workouts, exercises
        user_data: Optional user information (name, email, age, etc.)

    Returns:
        Complete HTML string ready for PDF conversion
    """
    # Detect program type and get color scheme
    program_type = detect_program_type(program_data.get('goal', ''))
    colors = COLOR_SCHEMES.get(program_type, COLOR_SCHEMES['sport'])

    # Aggregate statistics
    stats = aggregate_program_stats(program_data)

    # Prepare template context
    context = {
        'program': program_data,
        'user': user_data or {},
        'program_type': program_type,
        'colors': colors,
        'stats': stats,
        'generated_date': datetime.now().strftime('%B %d, %Y'),
        'get_intensity_color': get_intensity_color,
        'get_category_badge_color': get_category_badge_color,
    }

    # Load and render the main template
    template = jinja_env.get_template('program_main.html')
    html_content = template.render(**context)

    return html_content


def generate_program_html_file(
    program_data: Dict[str, Any],
    user_data: Optional[Dict[str, Any]],
    output_path: str
) -> str:
    """
    Generate HTML file for a program.

    Args:
        program_data: Full program data
        user_data: User information
        output_path: Path to save HTML file

    Returns:
        Path to generated HTML file
    """
    html_content = generate_html(program_data, user_data)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return output_path

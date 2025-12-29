"""
Natural language date parsing for voice agent
Supports relative dates: "tomorrow", "next Monday", "this week", "3 days from now"
"""
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List
import re


class DateParseError(Exception):
    """Raised when date parsing fails"""
    pass


def parse_natural_date(text: str, reference_date: Optional[date] = None) -> date:
    """
    Parse natural language date expression to date object.

    Args:
        text: Natural language date ("tomorrow", "next monday", "in 3 days")
        reference_date: Reference date (defaults to today)

    Returns:
        Parsed date object

    Raises:
        DateParseError: If date cannot be parsed

    Examples:
        >>> parse_natural_date("tomorrow")
        date(2025, 12, 30)  # If today is Dec 29
        >>> parse_natural_date("next monday")
        date(2025, 1, 5)
        >>> parse_natural_date("in 3 days")
        date(2026, 1, 1)
    """
    if reference_date is None:
        reference_date = date.today()

    text_lower = text.lower().strip()

    # EXACT MATCHES
    if text_lower in ['today', 'now']:
        return reference_date
    if text_lower == 'tomorrow':
        return reference_date + timedelta(days=1)
    if text_lower == 'yesterday':
        return reference_date - timedelta(days=1)

    # WEEKDAY NAMES
    weekday_map = {
        'monday': 0, 'mon': 0,
        'tuesday': 1, 'tue': 1, 'tues': 1,
        'wednesday': 2, 'wed': 2,
        'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
        'friday': 4, 'fri': 4,
        'saturday': 5, 'sat': 5,
        'sunday': 6, 'sun': 6
    }

    # Pattern: "next [weekday]", "this [weekday]"
    for day_name, day_index in weekday_map.items():
        if f"next {day_name}" in text_lower:
            return get_next_weekday(reference_date, day_index, skip_today=True)
        if f"this {day_name}" in text_lower:
            return get_next_weekday(reference_date, day_index, skip_today=False)
        if text_lower == day_name:
            # Just "monday" means next occurrence
            return get_next_weekday(reference_date, day_index, skip_today=False)

    # RELATIVE OFFSETS: "in 3 days", "3 days from now", "in a week"
    offset_match = re.search(r'(?:in|after)\s+(\d+)\s+(day|days|week|weeks)', text_lower)
    if offset_match:
        count = int(offset_match.group(1))
        unit = offset_match.group(2)
        if 'day' in unit:
            return reference_date + timedelta(days=count)
        if 'week' in unit:
            return reference_date + timedelta(weeks=count)

    # Pattern: "X days from now"
    from_now_match = re.search(r'(\d+)\s+days?\s+from\s+now', text_lower)
    if from_now_match:
        days = int(from_now_match.group(1))
        return reference_date + timedelta(days=days)

    # Fallback: try ISO date format (YYYY-MM-DD)
    iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    raise DateParseError(f"Could not parse date from: '{text}'")


def get_next_weekday(reference_date: date, target_weekday: int, skip_today: bool = False) -> date:
    """
    Get the next occurrence of a specific weekday.

    Args:
        reference_date: Starting date
        target_weekday: Target weekday (0=Monday, 6=Sunday)
        skip_today: If True, skip today even if it matches

    Returns:
        Next occurrence of the target weekday
    """
    current_weekday = reference_date.weekday()

    if current_weekday == target_weekday and not skip_today:
        return reference_date

    days_ahead = (target_weekday - current_weekday) % 7
    if days_ahead == 0:
        days_ahead = 7  # Next week

    return reference_date + timedelta(days=days_ahead)


def parse_week_range(text: str, reference_date: Optional[date] = None) -> Tuple[date, date]:
    """
    Parse week range from natural language.

    Args:
        text: "this week", "next week", "the week after"
        reference_date: Reference date (defaults to today)

    Returns:
        (start_date, end_date) of the week (Monday to Sunday)

    Raises:
        DateParseError: If week cannot be parsed
    """
    if reference_date is None:
        reference_date = date.today()

    text_lower = text.lower().strip()

    # Get start of week (Monday)
    def week_start(d: date) -> date:
        return d - timedelta(days=d.weekday())

    def week_end(d: date) -> date:
        return week_start(d) + timedelta(days=6)

    if text_lower in ['this week', 'current week']:
        start = week_start(reference_date)
        return (start, week_end(reference_date))

    if text_lower in ['next week']:
        next_week_date = reference_date + timedelta(weeks=1)
        start = week_start(next_week_date)
        return (start, week_end(next_week_date))

    if text_lower in ['the week after', 'week after next']:
        two_weeks_date = reference_date + timedelta(weeks=2)
        start = week_start(two_weeks_date)
        return (start, week_end(two_weeks_date))

    raise DateParseError(f"Could not parse week range from: '{text}'")


def get_date_description(target_date: date, reference_date: Optional[date] = None) -> str:
    """
    Convert date to natural language description.

    Args:
        target_date: Date to describe
        reference_date: Reference date (defaults to today)

    Returns:
        Natural language description ("tomorrow", "next Monday", "December 30")

    Example:
        >>> get_date_description(date(2025, 12, 30), date(2025, 12, 29))
        "tomorrow"
    """
    if reference_date is None:
        reference_date = date.today()

    delta = (target_date - reference_date).days

    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if 0 < delta <= 7:
        weekday_name = target_date.strftime("%A")
        if target_date.weekday() > reference_date.weekday():
            return f"this {weekday_name}"
        else:
            return f"next {weekday_name}"

    # Fallback: "December 30" or "December 30, 2026" if different year
    if target_date.year == reference_date.year:
        return target_date.strftime("%B %d")
    else:
        return target_date.strftime("%B %d, %Y")

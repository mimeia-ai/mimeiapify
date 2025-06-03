import textwrap
import re
from datetime import datetime, timezone
import logging
import pytz
from typing import Union, Optional

logger = logging.getLogger("HelperFunctions")

def parse_datetime_to_target_tz(dt_input: Optional[Union[str, datetime]], target_tz_str: str) -> Optional[datetime]:
    """
    Parses various datetime inputs (ISO string, naive datetime assumed UTC, aware datetime)
    and returns a timezone-aware datetime object localized to the target timezone.
    Returns None if input is None or parsing fails.
    """
    if dt_input is None:
        return None

    target_tz = pytz.timezone(target_tz_str)

    if isinstance(dt_input, str):
        try:
            # Handle potential 'Z' or offset formats
            dt_input = dt_input.replace('Z', '+00:00')
            # Attempt to parse ISO format
            dt_aware = datetime.fromisoformat(dt_input)
            # If parsed successfully but no tzinfo, assume UTC
            if dt_aware.tzinfo is None:
                dt_aware = pytz.utc.localize(dt_aware)
        except ValueError:
            logger.error(f"Could not parse datetime string: {dt_input}")
            # Optionally, try other formats or return None/raise error
            return None # Or raise specific error
    elif isinstance(dt_input, datetime):
        if dt_input.tzinfo is None:
            # Assume naive datetime is UTC
            dt_aware = pytz.utc.localize(dt_input)
        else:
            # Already timezone-aware
            dt_aware = dt_input
    else:
        logger.error(f"Unsupported input type for datetime parsing: {type(dt_input)}")
        return None # Or raise specific error

    # Convert to target timezone
    return dt_aware.astimezone(target_tz)

# Optional: Explicit serializer if needed, though Pydantic handles aware datetimes well.
def datetime_to_iso_string(dt_aware: Optional[datetime]) -> Optional[str]:
    """Converts a timezone-aware datetime object to an ISO 8601 string."""
    if dt_aware is None:
        return None
    if dt_aware.tzinfo is None:
            logger.warning(f"Provided datetime object lacks timezone info: {dt_aware}. Cannot reliably convert to ISO string with offset.")
            # Decide handling: raise error, assume UTC, or return naive ISO string?
            # Returning naive ISO string for now:
            return dt_aware.isoformat()
    return dt_aware.isoformat()


def format_date_friendly(iso_date_str: str, target_tz_str: str = "UTC") -> str:
    """
    Converts ISO date string to a friendly Spanish format in the target timezone.
    Example: '2025-01-16T15:04:09.000Z' -> '16 de enero del 2025' (adjusts day based on timezone)
    """
    try:
        logger.debug(f"Formatting date: {iso_date_str} for timezone {target_tz_str}")
        
        dt_aware = parse_datetime_to_target_tz(iso_date_str, target_tz_str)
        if not dt_aware:
                return iso_date_str # Return original if parsing failed

        # Convert to Spanish month name
        months = {
            1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
            5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
            9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
        }

        # Format the date using the localized datetime object
        return f"{dt_aware.day} de {months[dt_aware.month]} del {dt_aware.year}"
    except Exception as e:
        logger.error(f"Error formatting date {iso_date_str}: {str(e)}")
        return iso_date_str  # Return original string if conversion fails

def robust_clean_text(text: str, collapse_spaces: bool = True, collapse_newlines: bool = True) -> str:
    """
    Cleans up the provided text by:
    - Removing common leading whitespace (dedent).
    - Stripping leading and trailing spaces from each line.
    - Optionally collapsing multiple consecutive spaces (or any whitespace) within lines.
    - Optionally collapsing multiple consecutive blank lines into one.
    - Removing Markdown headings (# symbols)
    - Converting double asterisks (**) to single asterisks (*)
    
    Args:
        text (str): The input text to be cleaned.
        collapse_spaces (bool): If True, collapse multiple spaces within lines to a single space.
        collapse_newlines (bool): If True, collapse multiple blank lines into a single blank line.
        
    Returns:
        str: The cleaned text.
    """
    # Step 1: Remove common leading whitespace.
    dedented_text = textwrap.dedent(text)
    
    # Step 1.5: Remove Markdown headings and convert double asterisks to single
    lines = dedented_text.splitlines()
    processed_lines = []
    for line in lines:
        # Remove Markdown headings (###)
        line = re.sub(r'^#{1,6}\s+', '', line)
        # Convert double asterisks to single
        line = line.replace('**', '*')
        processed_lines.append(line)
    
    dedented_text = '\n'.join(processed_lines)
    
    # Step 2: Process each line: trim leading/trailing spaces and optionally collapse internal spaces.
    lines = dedented_text.splitlines()
    cleaned_lines = []
    for line in lines:
        # Strip extra spaces at the beginning and end of the line.
        stripped_line = line.strip()
        if collapse_spaces:
            # Replace any sequence of whitespace characters with a single space.
            stripped_line = re.sub(r'\s+', ' ', stripped_line)
        cleaned_lines.append(stripped_line)
    
    # Step 3: Optionally collapse multiple consecutive blank lines.
    if collapse_newlines:
        final_lines = []
        previous_blank = False
        for line in cleaned_lines:
            if line == "":
                if not previous_blank:
                    final_lines.append(line)
                previous_blank = True
            else:
                final_lines.append(line)
                previous_blank = False
    else:
        final_lines = cleaned_lines
    
    # Join the lines back together, ensuring no extra newlines at the start or end.
    return "\n".join(final_lines).strip()
    
        
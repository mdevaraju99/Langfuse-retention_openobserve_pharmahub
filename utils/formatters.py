"""
Data formatting utilities
"""
from datetime import datetime
from typing import Optional


def format_date(date_str: str, format_in: str = "%Y-%m-%d", format_out: str = "%B %d, %Y") -> str:
    """Format date string"""
    try:
        date_obj = datetime.strptime(date_str, format_in)
        return date_obj.strftime(format_out)
    except:
        return date_str


def format_number(num: int) -> str:
    """Format large numbers with K, M suffixes"""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text with ellipsis"""
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(' ', 1)[0] + "..."


def validate_url(url: str) -> bool:
    """Basic URL validation"""
    return url.startswith(("http://", "https://"))

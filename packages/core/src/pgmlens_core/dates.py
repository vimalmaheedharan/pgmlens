"""Small date helpers shared by every package so wording stays consistent."""

from __future__ import annotations

from datetime import date, datetime


def short_date(value: date | datetime) -> str:
    """Format as 'Nov 8' (no zero padding, platform independent)."""
    return f"{value:%b} {value.day}"

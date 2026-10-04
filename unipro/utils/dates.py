from __future__ import annotations

from datetime import date, datetime

import jdatetime


def parse_user_date(value: str) -> date:
    raw = value.strip().replace("-", "/")
    parts = raw.split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("invalid date format")

    year, month, day = map(int, parts)
    if year < 1700:
        return jdatetime.date(year, month, day).togregorian()
    return date(year, month, day)


def format_jalali(value: date) -> str:
    j = jdatetime.date.fromgregorian(date=value)
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def format_clock(value: datetime) -> str:
    return value.strftime("%H:%M")

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import jdatetime
from dateutil import parser as date_parser


TEHRAN_TZ = ZoneInfo("Asia/Tehran")
TRANSIENT_STATUS = {429, 502, 503, 504}


def normalize_text(value: Any) -> str:
    return (
        " ".join(str(value or "").split())
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("‌", "")
        .casefold()
    )


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TEHRAN_TZ)
    return parsed.astimezone(TEHRAN_TZ)


def jalali_dash(value: date) -> str:
    j = jdatetime.date.fromgregorian(date=value)
    return f"{j.year:04d}-{j.month:02d}-{j.day:02d}"


def departure_from_clock(day: date, clock: Any) -> datetime | None:
    raw = str(clock or "").strip()
    try:
        hour, minute = map(int, raw.split(":", 1))
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return datetime.combine(day, time(hour, minute), tzinfo=TEHRAN_TZ)


class PublicWebApiMixin:
    """Small read-only HTTP client for public provider web contracts.

    It does not solve CAPTCHAs, rotate identities, or retry access-denied
    responses. A 401/403 is surfaced to the provider as an error.
    """

    request_timeout_seconds: float = 8.0

    async def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        merged_headers = {
            "Accept": "application/json",
            "Accept-Language": "fa-IR,fa;q=0.9",
            "User-Agent": "Mozilla/5.0 UniProTravelWatch/0.1",
        }
        if headers:
            merged_headers.update(headers)

        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers=merged_headers) as session:
                    async with session.request(
                        method,
                        url,
                        params=params,
                        json=payload,
                    ) as response:
                        text = await response.text()
                        if response.status in TRANSIENT_STATUS and attempt == 0:
                            retry_after = response.headers.get("Retry-After")
                            delay = 0.4
                            if retry_after and retry_after.isdigit():
                                delay = min(2.0, max(0.2, float(retry_after)))
                            await asyncio.sleep(delay)
                            continue
                        if response.status >= 400:
                            raise RuntimeError(
                                f"HTTP {response.status} from provider: {text[:160]}"
                            )
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError as exc:
                            raise RuntimeError("provider returned non-JSON response") from exc
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as exc:
                last_error = exc
                if attempt == 0 and not (
                    isinstance(exc, RuntimeError)
                    and ("HTTP 401" in str(exc) or "HTTP 403" in str(exc))
                ):
                    await asyncio.sleep(0.25)
                    continue
                raise
        raise RuntimeError(str(last_error or "provider request failed"))

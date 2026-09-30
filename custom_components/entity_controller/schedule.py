"""Schedule parsing and window evaluation for Entity Controller."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class ScheduleSource(StrEnum):
    """Supported schedule anchors."""

    FIXED = "fixed"
    SUNRISE = "sunrise"
    SUNSET = "sunset"


@dataclass(frozen=True, slots=True)
class SchedulePoint:
    """A structured schedule anchor with an optional offset."""

    source: ScheduleSource
    fixed_time: time | None = None
    offset: timedelta = timedelta(0)

    @classmethod
    def fixed(cls, value: time, *, offset: timedelta = timedelta(0)) -> "SchedulePoint":
        return cls(ScheduleSource.FIXED, value, offset)

    @classmethod
    def sunrise(cls, *, offset: timedelta = timedelta(0)) -> "SchedulePoint":
        return cls(ScheduleSource.SUNRISE, None, offset)

    @classmethod
    def sunset(cls, *, offset: timedelta = timedelta(0)) -> "SchedulePoint":
        return cls(ScheduleSource.SUNSET, None, offset)


_LEGACY_SUN_PATTERN = re.compile(
    r"^(sunrise|sunset)(?:\s*([+-])\s*(\d{1,2}:\d{2}:\d{2}))?$",
    re.IGNORECASE,
)


def _parse_hms_duration(value: str) -> timedelta:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_legacy_schedule_point(value: str) -> SchedulePoint:
    """Convert a supported v9 schedule string to the structured v10 model."""

    normalized = value.strip().lower()
    if match := _LEGACY_SUN_PATTERN.fullmatch(normalized):
        source_text, sign, offset_text = match.groups()
        offset = timedelta(0)
        if offset_text:
            offset = _parse_hms_duration(offset_text)
            if sign == "-":
                offset = -offset
        source = ScheduleSource(source_text)
        return SchedulePoint(source=source, offset=offset)

    try:
        fixed = time.fromisoformat(normalized)
    except ValueError as err:
        raise ValueError(f"Unsupported legacy schedule point: {value!r}") from err
    return SchedulePoint.fixed(fixed)


def resolve_schedule_point(
    point: SchedulePoint,
    now: datetime,
    *,
    sunrise: datetime | None = None,
    sunset: datetime | None = None,
) -> datetime:
    """Resolve a schedule point on the local date represented by ``now``."""

    if now.tzinfo is None:
        raise ValueError("Schedule evaluation requires an aware datetime")

    if point.source is ScheduleSource.FIXED:
        if point.fixed_time is None:
            raise ValueError("Fixed schedule point is missing fixed_time")
        base = datetime.combine(now.date(), point.fixed_time, tzinfo=now.tzinfo)
    elif point.source is ScheduleSource.SUNRISE:
        if sunrise is None:
            raise ValueError("Sunrise datetime is required")
        base = sunrise.astimezone(now.tzinfo)
    else:
        if sunset is None:
            raise ValueError("Sunset datetime is required")
        base = sunset.astimezone(now.tzinfo)

    return base + point.offset


def is_window_active(
    start: SchedulePoint,
    end: SchedulePoint,
    now: datetime,
    *,
    sunrise: datetime | None = None,
    sunset: datetime | None = None,
) -> bool:
    """Return whether ``now`` lies inside a possibly cross-midnight window."""

    start_at = resolve_schedule_point(start, now, sunrise=sunrise, sunset=sunset)
    end_at = resolve_schedule_point(end, now, sunrise=sunrise, sunset=sunset)

    if end_at <= start_at:
        if now < end_at:
            start_at -= timedelta(days=1)
        else:
            end_at += timedelta(days=1)

    return start_at <= now < end_at


def schedule_at_home_assistant(
    hass: HomeAssistant,
    when: datetime,
    callback: Callable[[], Awaitable[None]],
) -> Callable[[], None]:
    """Schedule an async no-argument callback with Home Assistant."""

    from homeassistant.helpers.event import async_track_point_in_time

    async def _run(_: datetime) -> None:
        await callback()

    return async_track_point_in_time(hass, _run, when)

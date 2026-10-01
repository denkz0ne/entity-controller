from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from custom_components.entity_controller.schedule import (
    SchedulePoint,
    ScheduleSource,
    is_window_active,
    parse_legacy_schedule_point,
    schedule_point_from_data,
    window_is_active_from_data,
)


def test_fixed_window_crossing_midnight() -> None:
    tz = timezone(timedelta(hours=2))
    start = SchedulePoint.fixed(time(22, 0))
    end = SchedulePoint.fixed(time(6, 0))

    assert is_window_active(start, end, datetime(2026, 9, 30, 23, 0, tzinfo=tz))
    assert is_window_active(start, end, datetime(2026, 10, 1, 5, 59, tzinfo=tz))
    assert not is_window_active(start, end, datetime(2026, 10, 1, 12, 0, tzinfo=tz))


def test_legacy_sunset_offset_converts_to_schedule_point() -> None:
    point = parse_legacy_schedule_point("sunset - 00:30:00")

    assert point.source is ScheduleSource.SUNSET
    assert point.fixed_time is None
    assert point.offset == -timedelta(minutes=30)


def test_legacy_fixed_time_converts_to_schedule_point() -> None:
    point = parse_legacy_schedule_point("07:15:30")

    assert point.source is ScheduleSource.FIXED
    assert point.fixed_time == time(7, 15, 30)
    assert point.offset == timedelta(0)


def test_structured_fixed_window_is_active_across_midnight() -> None:
    window = {
        "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
        "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
    }
    now = datetime(2026, 10, 1, 1, 0, tzinfo=ZoneInfo("Europe/Bratislava"))

    assert window_is_active_from_data(window, now)
    assert schedule_point_from_data(window["start"]).fixed_time == time(20, 0)

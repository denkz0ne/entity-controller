"""Runtime actions for Entity Controller v10."""

from __future__ import annotations

from dataclasses import replace

from .controller import ControllerRuntime
from .model import ControllerState, ReconcileReason, TransitionCause
from .schedule import ScheduleSource, parse_legacy_schedule_point


async def async_activate(runtime: ControllerRuntime) -> None:
    """Activate a controller through service/button semantics."""

    runtime.enabled = True
    await runtime.async_transition(
        runtime._active_target,
        TransitionCause.SERVICE,
    )


async def async_clear_block(runtime: ControllerRuntime) -> None:
    """Clear blocked state where applicable."""

    if runtime.state is ControllerState.BLOCKED:
        if runtime.interlock_active:
            await runtime.async_reconcile(ReconcileReason.CLEAR_BLOCK)
            return
        await runtime.async_transition(ControllerState.IDLE, TransitionCause.SERVICE)


async def async_enable_block(runtime: ControllerRuntime) -> None:
    """Force blocked state while a timer is active."""

    if runtime.state is ControllerState.ACTIVE_TIMER:
        await runtime.async_transition(ControllerState.BLOCKED, TransitionCause.SERVICE)


async def async_enable_stay_mode(runtime: ControllerRuntime) -> None:
    """Enable runtime stay mode."""

    await runtime.async_set_stay_mode(True)


async def async_disable_stay_mode(runtime: ControllerRuntime) -> None:
    """Disable runtime stay mode."""

    await runtime.async_set_stay_mode(False)


async def async_set_night_mode(
    runtime: ControllerRuntime,
    *,
    start_time: str | None = None,
    end_time: str | None = None,
) -> None:
    """Update an existing night profile without restarting the controller."""

    if runtime.config.night_mode is None:
        return
    night_mode = dict(runtime.config.night_mode)
    if start_time is None and end_time is None:
        start_time = end_time = "00:00:00"

    for boundary, value in (("start", start_time), ("end", end_time)):
        if value is None:
            continue
        if value == "constraint":
            constraint = runtime.config.constraint_window
            if constraint is not None:
                night_mode[boundary] = dict(constraint[boundary])
            continue
        if value == "now":
            value = runtime._clock().timetz().replace(tzinfo=None).isoformat()
        point = parse_legacy_schedule_point(value)
        night_mode[boundary] = {
            "source": point.source.value,
            "time": (
                point.fixed_time.isoformat()
                if point.source is ScheduleSource.FIXED
                and point.fixed_time is not None
                else "00:00:00"
            ),
            "offset_seconds": point.offset.total_seconds(),
        }

    await runtime.async_apply_config(replace(runtime.config, night_mode=night_mode))

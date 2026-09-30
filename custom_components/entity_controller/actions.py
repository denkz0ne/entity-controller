"""Runtime actions for Entity Controller v10."""

from __future__ import annotations

from .controller import ControllerRuntime
from .model import ControllerState, TransitionCause


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
        await runtime.async_transition(ControllerState.IDLE, TransitionCause.SERVICE)


async def async_enable_block(runtime: ControllerRuntime) -> None:
    """Force blocked state while a timer is active."""

    if runtime.state is ControllerState.ACTIVE_TIMER:
        await runtime.async_transition(ControllerState.BLOCKED, TransitionCause.SERVICE)


async def async_enable_stay_mode(runtime: ControllerRuntime) -> None:
    """Enable runtime stay mode."""

    runtime.stay_mode = True


async def async_disable_stay_mode(runtime: ControllerRuntime) -> None:
    """Disable runtime stay mode."""

    runtime.stay_mode = False


async def async_set_night_mode(
    runtime: ControllerRuntime,
    *,
    start_time: str | None = None,
    end_time: str | None = None,
) -> None:
    """Compatibility placeholder until v10 constraint profiles are implemented."""


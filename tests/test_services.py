from __future__ import annotations

import pytest

from custom_components.entity_controller.actions import (
    async_activate,
    async_clear_block,
    async_disable_stay_mode,
    async_enable_block,
    async_enable_stay_mode,
    async_set_night_mode,
)
from custom_components.entity_controller.controller import ControllerRuntime
from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    TransitionCause,
)
from custom_components.entity_controller.services import async_dispatch_service


def make_runtime() -> ControllerRuntime:
    return ControllerRuntime(ControllerConfig(subentry_id="controller-a", name="Hall"))


@pytest.mark.asyncio
async def test_activate_action_uses_service_transition() -> None:
    runtime = make_runtime()

    await async_activate(runtime)

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.last_transition_cause is TransitionCause.SERVICE


@pytest.mark.asyncio
async def test_clear_block_action_returns_blocked_controller_to_idle() -> None:
    runtime = make_runtime()
    runtime.state = ControllerState.BLOCKED
    runtime.blocked_by = "light.hall"

    await async_clear_block(runtime)

    assert runtime.state is ControllerState.IDLE
    assert runtime.blocked_by is None


@pytest.mark.asyncio
async def test_enable_block_action_blocks_active_timer() -> None:
    runtime = make_runtime()
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    await async_enable_block(runtime)

    assert runtime.state is ControllerState.BLOCKED
    assert runtime.last_transition_cause is TransitionCause.SERVICE


@pytest.mark.asyncio
async def test_stay_mode_actions_toggle_runtime_flag() -> None:
    runtime = make_runtime()

    await async_enable_stay_mode(runtime)
    assert runtime.stay_mode is True

    await async_disable_stay_mode(runtime)
    assert runtime.stay_mode is False


@pytest.mark.asyncio
async def test_set_night_mode_is_compatibility_noop_until_constraints_exist() -> None:
    runtime = make_runtime()

    result = await async_set_night_mode(
        runtime, start_time="now", end_time="constraint"
    )

    assert result is None
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
async def test_registered_action_dispatches_to_selected_controller() -> None:
    selected = make_runtime()
    other = ControllerRuntime(
        ControllerConfig(subentry_id="controller-b", name="Kitchen")
    )
    manager = object.__new__(EntityControllerManager)
    manager.controllers = {
        "controller-a": selected,
        "controller-b": other,
    }

    await async_dispatch_service(
        {"entry-id": manager},
        "activate",
        {"controller_id": "controller-a"},
    )

    assert selected.state is ControllerState.ACTIVE_TIMER
    assert other.state is ControllerState.IDLE

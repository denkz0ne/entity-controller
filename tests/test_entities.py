from __future__ import annotations

import pytest

from custom_components.entity_controller.binary_sensor import (
    EntityControllerBlockedBinarySensor,
)
from custom_components.entity_controller.button import EntityControllerActivateButton
from custom_components.entity_controller.controller import ControllerRuntime
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    TransitionCause,
)
from custom_components.entity_controller.sensor import EntityControllerStateSensor
from custom_components.entity_controller.switch import (
    EntityControllerEnabledSwitch,
    EntityControllerStayModeSwitch,
)


def make_runtime() -> ControllerRuntime:
    return ControllerRuntime(
        ControllerConfig(
            subentry_id="controller-a",
            name="Hall Motion",
            trigger_entities=("binary_sensor.motion",),
        )
    )


def test_native_entities_have_stable_unique_ids_and_subentry_device_info() -> None:
    runtime = make_runtime()

    entities = [
        EntityControllerStateSensor(runtime, "entry-1"),
        EntityControllerEnabledSwitch(runtime, "entry-1"),
        EntityControllerStayModeSwitch(runtime, "entry-1"),
        EntityControllerBlockedBinarySensor(runtime, "entry-1"),
        EntityControllerActivateButton(runtime, "entry-1"),
    ]

    assert [entity.unique_id for entity in entities] == [
        "entry-1_controller-a_state",
        "entry-1_controller-a_enabled",
        "entry-1_controller-a_stay_mode",
        "entry-1_controller-a_blocked",
        "entry-1_controller-a_activate",
    ]
    for entity in entities:
        assert entity.device_info["identifiers"] == {("entity_controller", "controller-a")}
        assert entity.device_info["name"] == "Hall Motion"
        assert entity.device_info["config_entry_id"] == "entry-1"
        assert entity.device_info["config_subentry_id"] == "controller-a"


def test_state_sensor_exposes_exact_fsm_state_and_runtime_attributes() -> None:
    runtime = make_runtime()
    sensor = EntityControllerStateSensor(runtime, "entry-1")
    runtime.state = ControllerState.ACTIVE_TIMER
    runtime.last_triggered_by = "binary_sensor.motion"
    runtime.effective_delay_seconds = 42

    assert sensor.native_value == "active_timer"
    assert sensor.extra_state_attributes["last_triggered_by"] == "binary_sensor.motion"
    assert sensor.extra_state_attributes["effective_delay"] == 42


@pytest.mark.asyncio
async def test_enabled_switch_off_disables_decisions_without_turning_loads_off() -> None:
    runtime = make_runtime()
    switch = EntityControllerEnabledSwitch(runtime, "entry-1")

    await switch.async_turn_off()

    assert switch.is_on is False
    assert runtime.enabled is False
    assert runtime.state is ControllerState.DISABLED


@pytest.mark.asyncio
async def test_stay_mode_switch_persists_runtime_flag() -> None:
    runtime = make_runtime()
    switch = EntityControllerStayModeSwitch(runtime, "entry-1")

    await switch.async_turn_on()
    assert runtime.stay_mode is True

    await switch.async_turn_off()
    assert runtime.stay_mode is False


def test_blocked_binary_sensor_exposes_reason_and_source() -> None:
    runtime = make_runtime()
    runtime.state = ControllerState.BLOCKED
    runtime.blocked_by = "light.hall"
    runtime.last_transition_cause = TransitionCause.MANUAL_CONTROL
    sensor = EntityControllerBlockedBinarySensor(runtime, "entry-1")

    assert sensor.is_on is True
    assert sensor.extra_state_attributes["reason"] == "manual_control"
    assert sensor.extra_state_attributes["blocked_by"] == "light.hall"


@pytest.mark.asyncio
async def test_activate_button_transitions_controller_active() -> None:
    runtime = make_runtime()
    button = EntityControllerActivateButton(runtime, "entry-1")

    await button.async_press()

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.last_transition_cause is TransitionCause.SERVICE


def test_disabled_by_default_diagnostics_are_not_primary_entities() -> None:
    runtime = make_runtime()
    assert EntityControllerStateSensor(runtime, "entry-1").entity_registry_enabled_default
    assert not EntityControllerStateSensor(
        runtime,
        "entry-1",
        diagnostic_key="last_trigger",
    ).entity_registry_enabled_default

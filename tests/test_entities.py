from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity

from custom_components.entity_controller.binary_sensor import (
    EntityControllerBlockedBinarySensor,
)
from custom_components.entity_controller.button import EntityControllerActivateButton
from custom_components.entity_controller.controller import (
    ControllerRuntime,
    ReconcileSnapshot,
)
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    ReconcileReason,
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
            icon="mdi:motion-sensor",
            trigger_entities=("binary_sensor.motion",),
        )
    )


def test_native_entities_have_stable_unique_ids_names_icons_and_device_info() -> None:
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
    assert [entity.suggested_object_id for entity in entities] == [
        "ec_hall_motion_state",
        "ec_hall_motion_enabled",
        "ec_hall_motion_stay_mode",
        "ec_hall_motion_blocked",
        "ec_hall_motion_activate",
    ]
    assert [entity.translation_key for entity in entities] == [
        "state",
        "enabled",
        "stay_mode",
        "blocked",
        "activate",
    ]
    assert [entity.icon for entity in entities] == [
        "mdi:state-machine",
        "mdi:toggle-switch",
        "mdi:pin",
        "mdi:shield-lock",
        "mdi:play-circle",
    ]
    for entity in entities:
        assert entity.device_info["identifiers"] == {
            ("entity_controller", "controller-a")
        }
        assert entity.device_info["name"] == "Hall Motion"
        assert entity.has_entity_name
        assert "config_entry_id" not in entity.device_info
        assert "config_subentry_id" not in entity.device_info

    assert isinstance(entities[0], SensorEntity)
    assert isinstance(entities[1], SwitchEntity)
    assert isinstance(entities[2], SwitchEntity)
    assert isinstance(entities[3], BinarySensorEntity)
    assert isinstance(entities[4], ButtonEntity)


def test_renaming_controller_keeps_unique_id_and_only_changes_new_id_suggestion() -> None:
    runtime = make_runtime()
    entity = EntityControllerStateSensor(runtime, "entry-1")

    renamed_runtime = ControllerRuntime(
        replace(runtime.config, name="Kitchen Lights")
    )
    renamed_entity = EntityControllerStateSensor(renamed_runtime, "entry-1")

    assert renamed_entity.unique_id == entity.unique_id
    assert entity.suggested_object_id == "ec_hall_motion_state"
    assert renamed_entity.suggested_object_id == "ec_kitchen_lights_state"


def test_entity_translations_cover_native_function_names_and_fsm_states() -> None:
    for path, state_name in (
        (Path("custom_components/entity_controller/translations/en.json"), "EC State"),
        (Path("custom_components/entity_controller/translations/sk.json"), "EC Stav"),
    ):
        entity = json.loads(path.read_text(encoding="utf-8"))["entity"]
        assert entity["sensor"]["state"]["name"] == state_name
        assert entity["sensor"]["state"]["state"]["active_timer"]
        assert entity["switch"]["enabled"]["name"]
        assert entity["switch"]["stay_mode"]["name"]
        assert entity["binary_sensor"]["blocked"]["name"]
        assert entity["button"]["activate"]["name"]


def test_state_sensor_exposes_exact_fsm_state_and_runtime_attributes() -> None:
    runtime = make_runtime()
    sensor = EntityControllerStateSensor(runtime, "entry-1")
    runtime.state = ControllerState.ACTIVE_TIMER
    runtime.last_triggered_by = "binary_sensor.motion"
    runtime.effective_delay_seconds = 42

    assert sensor.native_value == "active_timer"
    assert sensor.extra_state_attributes["last_triggered_by"] == "binary_sensor.motion"
    assert sensor.extra_state_attributes["effective_delay"] == 42
    runtime.night_active = True
    runtime.block_expires_at = "soon"
    assert sensor.extra_state_attributes["profile"] == "night"
    assert sensor.extra_state_attributes["block_expires_at"] == "soon"


@pytest.mark.asyncio
async def test_state_sensor_exposes_transition_provenance_and_reconcile_sources() -> None:
    runtime = make_runtime()
    source = "binary_sensor.motion"
    await runtime.async_transition(
        ControllerState.ACTIVE_TIMER,
        TransitionCause.SENSOR_TRIGGER,
        source_entity_id=source,
    )
    sensor = EntityControllerStateSensor(runtime, "entry-1")

    assert runtime.last_transition_source == source
    assert sensor.extra_state_attributes["last_transition_source"] == source
    assert sensor.extra_state_attributes["last_transition_cause"] == "sensor_trigger"
    assert sensor.extra_state_attributes["last_transition_at"] is not None

    await runtime.async_reconcile(
        ReconcileReason.RESTORE,
        ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=True,
            interlock_active=False,
            sensor_active=False,
            state_entities_on=False,
            active_overrides=("input_boolean.guest_mode",),
        ),
    )

    attributes = sensor.extra_state_attributes
    assert attributes["last_reconcile_reason"] == "restore"
    assert attributes["active_overrides"] == ["input_boolean.guest_mode"]
    assert attributes["active_interlocks"] == []
    assert attributes["override_active"] is True
    assert attributes["last_transition_source"] == source

    await runtime.async_transition(ControllerState.IDLE, TransitionCause.SERVICE)
    assert runtime.last_transition_source is None


@pytest.mark.asyncio
async def test_blocked_sensor_explains_interlock_reconcile_without_fake_transition() -> None:
    runtime = make_runtime()
    await runtime.async_reconcile(
        ReconcileReason.RESTORE,
        ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=False,
            interlock_active=True,
            sensor_active=False,
            state_entities_on=False,
            active_interlocks=("input_boolean.maintenance",),
        ),
    )

    blocked = EntityControllerBlockedBinarySensor(runtime, "entry-1")
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.last_transition_at is None
    assert blocked.extra_state_attributes == {
        "block_reason": "interlock",
        "reason": "interlock",
        "blocked_by": "input_boolean.maintenance",
        "blocked_at": runtime.blocked_at,
        "block_expires_at": runtime.block_expires_at,
        "active_interlocks": ["input_boolean.maintenance"],
    }


@pytest.mark.asyncio
async def test_enabled_switch_off_disables_decisions_without_turning_loads_off() -> (
    None
):
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
    runtime.block_reason = "manual_control"
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
    assert EntityControllerStateSensor(
        runtime, "entry-1"
    ).entity_registry_enabled_default
    assert not EntityControllerStateSensor(
        runtime,
        "entry-1",
        diagnostic_key="last_trigger",
    ).entity_registry_enabled_default

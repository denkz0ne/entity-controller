from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant import config_entries

from custom_components.entity_controller.config_flow import (
    ControllerOptionsFlow,
    ControllerSubentryFlowHandler,
    EntityControllerConfigFlow,
    controller_form_values,
    normalize_controller_user_input,
)
from custom_components.entity_controller.const import DOMAIN


def _prepare_config_flow(
    flow: EntityControllerConfigFlow,
) -> EntityControllerConfigFlow:
    flow.flow_id = "root-flow"
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    return flow


def _prepare_subentry_flow(
    flow: ControllerSubentryFlowHandler,
) -> ControllerSubentryFlowHandler:
    flow.flow_id = "controller-flow"
    flow.handler = ("entry-id", "controller")
    flow.context = {"source": "user"}
    return flow


def _schema_keys(schema: object) -> set[str]:
    return {getattr(key, "schema", key) for key in getattr(schema, "schema", {})}


def _all_schema_keys(schema: object) -> set[str]:
    keys = _schema_keys(schema)
    for value in getattr(schema, "schema", {}).values():
        nested = getattr(value, "schema", None)
        if nested is not None:
            keys.update(_schema_keys(nested))
    return keys


@pytest.mark.asyncio
async def test_root_flow_creates_single_entity_controller_entry() -> None:
    flow = _prepare_config_flow(EntityControllerConfigFlow())

    result = await flow.async_step_user({"name": "Entity Controller"})

    assert result["type"] == "create_entry"
    assert result["flow_id"] == "root-flow"
    assert result["handler"] == DOMAIN
    assert result["title"] == "Entity Controller"
    assert result["data"] == {"name": "Entity Controller"}
    assert result["version"] == 10


@pytest.mark.asyncio
async def test_root_creation_starts_controller_subentry_flow() -> None:
    class SubentryFlows:
        async def async_init(self, handler, *, context):
            assert handler == ("entry-id", "controller")
            assert context["source"] == "user"
            return {"flow_id": "subentry-flow"}

    flow = _prepare_config_flow(EntityControllerConfigFlow())
    flow.hass = type(
        "Hass",
        (),
        {
            "config_entries": type(
                "ConfigEntries", (), {"subentries": SubentryFlows()}
            )()
        },
    )()

    result = await flow.async_on_create_entry(
        {"result": type("Entry", (), {"entry_id": "entry-id"})()}
    )

    assert result["next_flow"][1] == "subentry-flow"


@pytest.mark.asyncio
async def test_root_flow_form_has_visible_fields() -> None:
    flow = _prepare_config_flow(EntityControllerConfigFlow())

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["flow_id"] == "root-flow"
    assert result["handler"] == DOMAIN
    assert "name" in _schema_keys(result["data_schema"])


def test_root_flow_advertises_controller_subentry_type() -> None:
    supported = EntityControllerConfigFlow.async_get_supported_subentry_types(object())

    assert supported == {"controller": ControllerSubentryFlowHandler}


@pytest.mark.asyncio
async def test_integration_settings_opens_add_controller_form() -> None:
    flow = ControllerOptionsFlow()
    flow.flow_id = "options-flow"
    flow.handler = "entry-id"
    flow.context = {"source": "init"}

    result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["handler"] == "entry-id"
    assert "trigger_entities" in _all_schema_keys(result["data_schema"])


@pytest.mark.asyncio
async def test_integration_settings_adds_controller_subentry(monkeypatch) -> None:
    added: list[object] = []

    class Subentry:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    entry = type("Entry", (), {"domain": DOMAIN, "options": {}})()

    class ConfigEntries:
        def async_get_known_entry(self, entry_id):
            assert entry_id == "entry-id"
            return entry

        def async_add_subentry(self, parent, subentry):
            assert parent is entry
            added.append(subentry)

    monkeypatch.setattr(config_entries, "ConfigSubentry", Subentry, raising=False)
    flow = ControllerOptionsFlow()
    flow.flow_id = "options-flow"
    flow.handler = "entry-id"
    flow.context = {"source": "init"}
    flow.hass = type("Hass", (), {"config_entries": ConfigEntries()})()

    result = await flow.async_step_init(
        {
            "name": "Hall",
            "trigger_entities": ["binary_sensor.hall"],
            "control_entities": ["light.hall"],
        }
    )

    assert result["type"] == "create_entry"
    assert added[0].subentry_type == "controller"
    assert added[0].data["control_entities"] == ("light.hall",)


def test_manifest_enables_config_flow() -> None:
    manifest = json.loads(
        Path("custom_components/entity_controller/manifest.json").read_text()
    )

    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "hub"


def test_basic_controller_input_is_normalized_without_advanced_fields() -> None:
    data = normalize_controller_user_input(
        {
            "name": "Hall Motion",
            "trigger_entities": ["binary_sensor.hall_motion"],
            "control_entities": ["light.hall"],
        }
    )

    assert data == {
        "name": "Hall Motion",
        "icon": None,
        "trigger_entities": ("binary_sensor.hall_motion",),
        "control_entities": ("light.hall",),
        "state_entities": (),
        "override_entities": (),
        "interlock_entities": (),
        "sensor_type": "event",
        "sensor_resets_timer": False,
        "delay_seconds": 180.0,
        "blocking_enabled": True,
        "block_timeout_seconds": None,
        "enabled_default": True,
        "stay_mode_default": False,
        "backoff_enabled": False,
        "backoff_factor": 1.1,
        "backoff_max_seconds": 300.0,
        "constraint_window": None,
        "night_mode": None,
        "service_data_on": {},
        "service_data_off": {},
        "transition_behaviors": {
            "on_enter_idle": "off",
            "on_exit_idle": "ignore",
            "on_enter_active": "on",
            "on_exit_active": "ignore",
            "on_enter_overridden": "ignore",
            "on_exit_overridden": "ignore",
            "on_enter_constrained": "ignore",
            "on_exit_constrained": "ignore",
            "on_enter_blocked": "ignore",
            "on_exit_blocked": "ignore",
        },
        "trigger_on_states": ("on",),
        "trigger_off_states": ("off",),
        "state_on_states": ("on",),
        "state_off_states": ("off",),
        "override_on_states": ("on",),
        "override_off_states": ("off",),
        "state_attributes_ignore": (),
    }


def test_advanced_controller_sections_are_normalized() -> None:
    data = normalize_controller_user_input(
        {
            "identity": {"name": "Hall", "icon": "mdi:motion-sensor"},
            "triggers": {
                "trigger_entities": ["binary_sensor.hall"],
                "sensor_type": "duration",
                "sensor_resets_timer": True,
            },
            "targets": {"control_entities": ["light.hall"]},
            "timer": {
                "delay_seconds": 60,
                "backoff_enabled": True,
                "backoff_factor": 1.5,
                "backoff_max_seconds": 600,
            },
            "blocking": {
                "blocking_enabled": True,
                "block_timeout_seconds": 900,
            },
            "constraints": {
                "constraint_enabled": True,
                "constraint_start_source": "fixed",
                "constraint_start_time": "06:30:00",
                "constraint_start_offset_seconds": 0,
                "constraint_end_source": "sunset",
                "constraint_end_time": "23:00:00",
                "constraint_end_offset_seconds": -900,
            },
            "night": {
                "night_mode_enabled": True,
                "night_start_source": "sunset",
                "night_start_time": "20:00:00",
                "night_start_offset_seconds": -1800,
                "night_end_source": "sunrise",
                "night_end_time": "06:00:00",
                "night_end_offset_seconds": 900,
                "night_delay_seconds": 30,
                "night_service_data_on": {"brightness_pct": 15},
                "night_service_data_off": {},
            },
            "actions": {
                "service_data_on": {"brightness_pct": 80},
                "service_data_off": {"transition": 2},
                "on_enter_active": "on",
                "on_enter_idle": "off",
            },
            "advanced": {
                "trigger_on_states": "on, detected",
                "trigger_off_states": "off, clear",
                "state_attributes_ignore": "brightness, color_mode",
            },
        }
    )

    assert data["icon"] == "mdi:motion-sensor"
    assert data["sensor_resets_timer"] is True
    assert data["block_timeout_seconds"] == 900.0
    assert data["backoff_factor"] == 1.5
    assert data["constraint_window"]["end"] == {
        "source": "sunset",
        "time": "23:00:00",
        "offset_seconds": -900.0,
    }
    assert data["night_mode"]["delay_seconds"] == 30.0
    assert data["night_mode"]["service_data_on"] == {"brightness_pct": 15}
    assert data["service_data_on"] == {"brightness_pct": 80}
    assert data["transition_behaviors"]["on_enter_active"] == "on"
    assert data["trigger_on_states"] == ("on", "detected")
    assert data["state_attributes_ignore"] == ("brightness", "color_mode")


def test_stored_controller_data_is_expanded_back_into_form_sections() -> None:
    values = controller_form_values(
        {
            "name": "Hall",
            "trigger_entities": ("binary_sensor.hall",),
            "control_entities": ("light.hall",),
            "constraint_window": {
                "start": {"source": "sunset", "time": "20:00:00", "offset_seconds": -600},
                "end": {"source": "fixed", "time": "23:00:00", "offset_seconds": 0},
            },
            "night_mode": {
                "start": {"source": "fixed", "time": "21:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
                "delay_seconds": 45,
            },
            "trigger_on_states": ("on", "playing"),
        }
    )

    assert values["identity"]["name"] == "Hall"
    assert values["constraints"]["constraint_enabled"] is True
    assert values["constraints"]["constraint_start_source"] == "sunset"
    assert values["night"]["night_delay_seconds"] == 45
    assert values["advanced"]["trigger_on_states"] == "on, playing"


@pytest.mark.asyncio
async def test_controller_subentry_form_is_valid_flow_result() -> None:
    flow = _prepare_subentry_flow(ControllerSubentryFlowHandler())

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["flow_id"] == "controller-flow"
    assert result["handler"] == ("entry-id", "controller")
    assert result["step_id"] == "user"
    keys = _all_schema_keys(result["data_schema"])
    for required in (
        "name",
        "trigger_entities",
        "control_entities",
        "sensor_resets_timer",
        "block_timeout_seconds",
        "backoff_enabled",
        "constraint_enabled",
        "night_mode_enabled",
        "night_delay_seconds",
        "service_data_on",
        "on_enter_active",
        "state_attributes_ignore",
    ):
        assert required in keys

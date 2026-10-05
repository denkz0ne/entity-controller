from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigEntryState

from custom_components.entity_controller.config_flow import (
    CONTROLLER_RECONFIGURE_SCHEMA,
    CONTROLLER_SCHEMA,
    ControllerOptionsFlow,
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


def _schema_keys(schema: object) -> set[str]:
    return {getattr(key, "schema", key) for key in getattr(schema, "schema", {})}


def _all_schema_keys(schema: object) -> set[str]:
    keys = _schema_keys(schema)
    for value in getattr(schema, "schema", {}).values():
        nested = getattr(value, "schema", None)
        if nested is not None:
            keys.update(_schema_keys(nested))
    return keys


def _section_schema(schema: object, name: str) -> object:
    for key, value in getattr(schema, "schema", {}).items():
        if getattr(key, "schema", key) == name:
            return getattr(value, "schema", value)
    raise AssertionError(f"Missing section {name}")


class _ImportFlowManager:
    def async_progress_by_handler(self, *args, **kwargs):
        return []

    def async_abort(self, flow_id):
        raise AssertionError(f"Unexpected flow abort: {flow_id}")


class _ImportConfigEntries:
    def __init__(self, entries=()):
        self.entries = list(entries)
        self.flow = _ImportFlowManager()

    def async_entries(self, domain, include_ignore=False):
        return self.entries

    def async_entry_for_domain_unique_id(self, domain, unique_id):
        return next((entry for entry in self.entries if entry.unique_id == unique_id), None)


def _prepare_import_flow(existing=()):
    flow = EntityControllerConfigFlow()
    flow.flow_id = "import-flow"
    flow.handler = DOMAIN
    flow.context = {"source": "import"}
    flow.hass = SimpleNamespace(
        loop=asyncio.get_running_loop(),
        config_entries=_ImportConfigEntries(existing),
    )
    return flow


@pytest.mark.asyncio
async def test_import_flow_creates_entry_with_stable_legacy_identity() -> None:
    flow = _prepare_import_flow()

    result = await flow.async_step_import(
        {
            "controller_id": "old_bedroom",
            "name": "Old Bedroom",
            "trigger_entities": ("binary_sensor.bedroom_motion",),
            "control_entities": ("light.bedroom",),
            "delay_seconds": 90.0,
        }
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Old Bedroom"
    assert result["data"] == {
        "name": "Old Bedroom",
        "trigger_entities": ("binary_sensor.bedroom_motion",),
        "control_entities": ("light.bedroom",),
        "delay_seconds": 90.0,
        "_ec_controller_id": "old_bedroom",
        "_ec_entity_unique_id_prefix": "old_bedroom",
    }
    assert result["context"]["unique_id"] == "legacy-yaml:old_bedroom"
    assert result["version"] == 11


@pytest.mark.asyncio
async def test_import_flow_aborts_duplicate_without_changing_existing_entry() -> None:
    existing = SimpleNamespace(
        unique_id="legacy-yaml:old_bedroom",
        data={"name": "User edited name"},
        source="import",
        state=ConfigEntryState.NOT_LOADED,
    )
    flow = _prepare_import_flow([existing])

    with pytest.raises(data_entry_flow.AbortFlow):
        await flow.async_step_import(
            {"controller_id": "old_bedroom", "name": "Old Bedroom"}
        )

    assert existing.data == {"name": "User edited name"}


@pytest.mark.asyncio
async def test_user_flow_creates_a_controller_device_entry() -> None:
    flow = _prepare_config_flow(EntityControllerConfigFlow())

    result = await flow.async_step_user(
        {
            "name": "WC",
            "trigger_entities": ["binary_sensor.wc_motion"],
            "control_entities": ["light.wc"],
        }
    )

    assert result["type"] == "create_entry"
    assert result["flow_id"] == "root-flow"
    assert result["handler"] == DOMAIN
    assert result["title"] == "WC"
    assert result["data"]["name"] == "WC"
    assert result["data"]["trigger_entities"] == ("binary_sensor.wc_motion",)
    assert result["data"]["_ec_controller_id"]
    assert result["data"]["_ec_entity_unique_id_prefix"] == result["data"][
        "_ec_controller_id"
    ]
    assert result["version"] == 11


@pytest.mark.asyncio
async def test_add_flow_form_has_controller_fields() -> None:
    flow = _prepare_config_flow(EntityControllerConfigFlow())

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["flow_id"] == "root-flow"
    assert result["handler"] == DOMAIN
    assert _schema_keys(result["data_schema"]) == _schema_keys(CONTROLLER_SCHEMA)


def test_controller_form_keeps_common_setup_in_one_expanded_section() -> None:
    assert _schema_keys(CONTROLLER_SCHEMA) == {
        "basic",
        "timer",
        "monitoring",
        "rules",
        "constraints",
        "night",
        "initial_state",
        "actions",
        "advanced",
    }
    assert _schema_keys(_section_schema(CONTROLLER_SCHEMA, "basic")) == {
        "name",
        "icon",
        "trigger_entities",
        "control_entities",
        "delay_seconds",
    }


def test_reconfigure_form_omits_creation_only_defaults() -> None:
    assert "initial_state" not in _schema_keys(CONTROLLER_RECONFIGURE_SCHEMA)


@pytest.mark.asyncio
async def test_device_settings_opens_edit_controller_form() -> None:
    entry = type(
        "Entry",
        (),
        {
            "entry_id": "entry-id",
            "data": {"name": "Hall", "trigger_entities": ("binary_sensor.hall",)},
        },
    )()

    class ConfigEntries:
        def async_get_known_entry(self, entry_id):
            assert entry_id == "entry-id"
            return entry

    flow = ControllerOptionsFlow()
    flow.flow_id = "options-flow"
    flow.handler = "entry-id"
    flow.context = {"source": "options"}
    flow.hass = type("Hass", (), {"config_entries": ConfigEntries()})()
    suggested_values = []
    flow.add_suggested_values_to_schema = lambda schema, values: (
        suggested_values.append(values) or schema
    )

    result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["handler"] == "entry-id"
    assert _schema_keys(result["data_schema"]) == _schema_keys(
        CONTROLLER_RECONFIGURE_SCHEMA
    )
    assert suggested_values == [
        {
            "basic": {"name": "Hall", "trigger_entities": ("binary_sensor.hall",)},
            "timer": {},
            "monitoring": {},
            "rules": {},
            "constraints": {"constraint_enabled": False},
            "night": {"night_mode_enabled": False},
            "initial_state": {},
            "actions": {},
            "advanced": {},
        }
    ]


@pytest.mark.asyncio
async def test_device_settings_updates_only_that_controller() -> None:
    entry = type(
        "Entry",
        (),
        {
            "domain": DOMAIN,
            "entry_id": "entry-id",
            "options": {},
            "title": "Hall",
            "data": {
                "_ec_controller_id": "stable-controller-id",
                "_ec_entity_unique_id_prefix": "stable-controller-id",
                "name": "Hall",
                "trigger_entities": ("binary_sensor.old",),
                "control_entities": ("light.hall",),
                "enabled": False,
                "stay_mode": True,
            },
        },
    )()

    class ConfigEntries:
        def async_get_known_entry(self, entry_id):
            assert entry_id == "entry-id"
            return entry

        def async_update_entry(self, target, *, data, title):
            assert target is entry
            entry.data = data
            entry.title = title

    flow = ControllerOptionsFlow()
    flow.flow_id = "options-flow"
    flow.handler = "entry-id"
    flow.context = {"source": "init"}
    flow.hass = type("Hass", (), {"config_entries": ConfigEntries()})()

    result = await flow.async_step_init(
        {
            "name": "Hall",
            "trigger_entities": ["binary_sensor.new"],
            "control_entities": ["light.hall"],
        }
    )

    assert result["type"] == "create_entry"
    assert entry.title == "Hall"
    assert entry.data["trigger_entities"] == ("binary_sensor.new",)
    assert entry.data["_ec_controller_id"] == "stable-controller-id"
    assert entry.data["enabled"] is False
    assert entry.data["stay_mode"] is True


def test_manifest_enables_config_flow() -> None:
    manifest = json.loads(
        Path("custom_components/entity_controller/manifest.json").read_text()
    )

    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest.get("single_config_entry", False) is False
    assert manifest["integration_type"] == "device"


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


def test_duration_selector_values_are_stored_as_seconds() -> None:
    data = normalize_controller_user_input(
        {
            "basic": {
                "name": "Hall",
                "trigger_entities": ["binary_sensor.hall"],
                "control_entities": ["light.hall"],
                "delay_seconds": {"minutes": 2, "seconds": 30},
            },
            "monitoring": {"block_timeout_seconds": {"minutes": 15}},
        }
    )

    assert data["delay_seconds"] == 150.0
    assert data["block_timeout_seconds"] == 900.0


def test_stored_controller_data_is_expanded_back_into_form_sections() -> None:
    values = controller_form_values(
        {
            "name": "Hall",
            "trigger_entities": ["binary_sensor.hall"],
            "control_entities": ["light.hall"],
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

    assert values["basic"]["name"] == "Hall"
    assert values["constraints"]["constraint_enabled"] is True
    assert values["constraints"]["constraint_start_source"] == "sunset"
    assert values["night"]["night_delay_seconds"] == {
        "hours": 0,
        "minutes": 0,
        "seconds": 45,
    }
    assert values["advanced"]["trigger_on_states"] == "on, playing"


def test_stored_disabled_block_timeout_is_a_duration_mapping() -> None:
    values = controller_form_values(
        {
            "name": "Hall",
            "trigger_entities": ("binary_sensor.hall",),
            "control_entities": ("light.hall",),
            "block_timeout_seconds": None,
        }
    )

    CONTROLLER_SCHEMA(values)
    assert values["monitoring"]["block_timeout_seconds"] == {
        "hours": 0,
        "minutes": 0,
        "seconds": 0,
    }


@pytest.mark.asyncio
async def test_add_controller_form_contains_complete_configuration() -> None:
    flow = _prepare_config_flow(EntityControllerConfigFlow())

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["flow_id"] == "root-flow"
    assert result["handler"] == DOMAIN
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

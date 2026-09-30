from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant import config_entries

from custom_components.entity_controller.config_flow import (
    ControllerOptionsFlow,
    ControllerSubentryFlowHandler,
    EntityControllerConfigFlow,
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
async def test_helper_settings_opens_add_controller_form() -> None:
    flow = ControllerOptionsFlow()
    flow.flow_id = "options-flow"
    flow.handler = "entry-id"
    flow.context = {"source": "init"}

    result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["handler"] == "entry-id"
    assert "trigger_entities" in _schema_keys(result["data_schema"])


@pytest.mark.asyncio
async def test_helper_settings_adds_controller_subentry(monkeypatch) -> None:
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
        "trigger_entities": ("binary_sensor.hall_motion",),
        "control_entities": ("light.hall",),
        "state_entities": (),
        "override_entities": (),
        "interlock_entities": (),
        "sensor_type": "event",
        "delay_seconds": 180.0,
        "blocking_enabled": True,
        "stay_mode_default": False,
    }


@pytest.mark.asyncio
async def test_controller_subentry_form_is_valid_flow_result() -> None:
    flow = _prepare_subentry_flow(ControllerSubentryFlowHandler())

    result = await flow.async_step_user()

    assert result["type"] == "form"
    assert result["flow_id"] == "controller-flow"
    assert result["handler"] == ("entry-id", "controller")
    assert result["step_id"] == "user"
    assert "name" in _schema_keys(result["data_schema"])
    assert "trigger_entities" in _schema_keys(result["data_schema"])
    assert "control_entities" in _schema_keys(result["data_schema"])

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.entity_controller.config_flow import (
    ControllerSubentryFlowHandler,
    EntityControllerConfigFlow,
    normalize_controller_user_input,
)
from custom_components.entity_controller.const import DOMAIN


def _prepare_config_flow(flow: EntityControllerConfigFlow) -> EntityControllerConfigFlow:
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
    return {
        getattr(key, "schema", key)
        for key in getattr(schema, "schema", {})
    }


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

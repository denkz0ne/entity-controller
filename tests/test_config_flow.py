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


@pytest.mark.asyncio
async def test_root_flow_creates_single_entity_controller_entry() -> None:
    flow = EntityControllerConfigFlow()

    result = await flow.async_step_user({})

    assert result["type"] == "create_entry"
    assert result["title"] == "Entity Controller"
    assert result["data"] == {}


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

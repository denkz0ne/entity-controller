from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.entity_controller.config_flow import ControllerSubentryFlowHandler


@pytest.mark.asyncio
async def test_controller_subentry_flow_adds_basic_motion_controller() -> None:
    flow = ControllerSubentryFlowHandler()

    result = await flow.async_step_user(
        {
            "name": "Hall Motion",
            "trigger_entities": ["binary_sensor.hall_motion"],
            "control_entities": ["light.hall"],
            "delay_seconds": 90,
        }
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Hall Motion"
    assert result["subentry_type"] == "controller"
    assert result["data"]["trigger_entities"] == ("binary_sensor.hall_motion",)
    assert result["data"]["control_entities"] == ("light.hall",)
    assert result["data"]["delay_seconds"] == 90.0


@pytest.mark.asyncio
async def test_controller_subentry_reconfigure_updates_without_root_reload() -> None:
    flow = ControllerSubentryFlowHandler()

    result = await flow.async_step_reconfigure(
        {
            "name": "Hall Motion",
            "trigger_entities": ["binary_sensor.new_motion"],
            "control_entities": ["light.hall"],
        }
    )

    assert result["type"] == "update_subentry"
    assert result["reload"] is False
    assert result["data"]["trigger_entities"] == ("binary_sensor.new_motion",)


@pytest.mark.asyncio
async def test_external_helper_selection_is_preserved_as_reference() -> None:
    flow = ControllerSubentryFlowHandler()

    result = await flow.async_step_user(
        {
            "name": "Room",
            "trigger_entities": ["binary_sensor.room_motion"],
            "control_entities": ["light.room"],
            "override_entities": ["input_boolean.navsteva_block"],
            "interlock_entities": ["input_boolean.izba_block"],
        }
    )

    assert result["data"]["override_entities"] == ("input_boolean.navsteva_block",)
    assert result["data"]["interlock_entities"] == ("input_boolean.izba_block",)


def test_en_and_sk_translations_define_config_subentry_flow() -> None:
    for path in (
        Path("custom_components/entity_controller/strings.json"),
        Path("custom_components/entity_controller/translations/en.json"),
        Path("custom_components/entity_controller/translations/sk.json"),
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "config_subentries" in data
        assert "controller" in data["config_subentries"]
        assert data["config_subentries"]["controller"]["title"]

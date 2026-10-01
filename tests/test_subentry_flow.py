from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.entity_controller.config_flow import (
    ControllerSubentryFlowHandler,
)


def _prepare_subentry_flow(
    flow: ControllerSubentryFlowHandler,
    source: str = "user",
) -> ControllerSubentryFlowHandler:
    flow.flow_id = "controller-flow"
    flow.handler = ("entry-id", "controller")
    flow.context = {"source": source}
    return flow


class ReconfigureFlow(ControllerSubentryFlowHandler):
    def _get_entry(self) -> object:
        return "entry"

    def _get_reconfigure_subentry(self) -> object:
        return "subentry"

    def async_update_and_abort(self, entry: object, subentry: object, **kwargs: object):
        return {
            "type": "abort",
            "reason": "reconfigure_successful",
            "entry": entry,
            "subentry": subentry,
            **kwargs,
        }


@pytest.mark.asyncio
async def test_controller_subentry_flow_adds_basic_motion_controller() -> None:
    flow = _prepare_subentry_flow(ControllerSubentryFlowHandler())

    result = await flow.async_step_user(
        {
            "name": "Hall Motion",
            "trigger_entities": ["binary_sensor.hall_motion"],
            "control_entities": ["light.hall"],
            "delay_seconds": 90,
        }
    )

    assert result["type"] == "create_entry"
    assert result["flow_id"] == "controller-flow"
    assert result["handler"] == ("entry-id", "controller")
    assert result["context"] == {"source": "user"}
    assert result["title"] == "Hall Motion"
    assert result["data"]["trigger_entities"] == ("binary_sensor.hall_motion",)
    assert result["data"]["control_entities"] == ("light.hall",)
    assert result["data"]["delay_seconds"] == 90.0


@pytest.mark.asyncio
async def test_controller_subentry_reconfigure_updates_without_root_reload() -> None:
    flow = _prepare_subentry_flow(ReconfigureFlow(), source="reconfigure")
    flow.context["subentry_id"] = "controller-a"

    result = await flow.async_step_reconfigure(
        {
            "name": "Hall Motion",
            "trigger_entities": ["binary_sensor.new_motion"],
            "control_entities": ["light.hall"],
        }
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert result["title"] == "Hall Motion"
    assert result["data"]["trigger_entities"] == ("binary_sensor.new_motion",)


@pytest.mark.asyncio
async def test_external_helper_selection_is_preserved_as_reference() -> None:
    flow = _prepare_subentry_flow(ControllerSubentryFlowHandler())

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
        steps = (
            (data["config_subentries"]["controller"]["step"]["user"], True),
            (
                data["config_subentries"]["controller"]["step"]["reconfigure"],
                False,
            ),
            (data["options"]["step"]["init"], True),
        )
        for step, has_initial_state in steps:
            sections = (
                "basic",
                "timer",
                "monitoring",
                "rules",
                "constraints",
                "night",
                "actions",
                "advanced",
            ) + (("initial_state",) if has_initial_state else ())
            for section in sections:
                assert step["sections"][section]["name"]
            for field in (
                "sensor_resets_timer",
                "block_timeout_seconds",
                "constraint_start_source",
                "night_delay_seconds",
                "on_enter_active",
                "state_attributes_ignore",
            ):
                assert any(
                    section.get("data", {}).get(field)
                    for section in step["sections"].values()
                )
        if path.name == "sk.json":
            assert "Udalosť spustí časovač" in steps[0][0]["sections"]["timer"][
                "data_description"
            ]["sensor_type"]

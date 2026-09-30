from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from custom_components.entity_controller.controller import ControllerRuntime
from custom_components.entity_controller.diagnostics import async_get_config_entry_diagnostics
from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import ControllerConfig, ControllerState


@dataclass(frozen=True)
class FakeEntry:
    entry_id: str
    data: dict[str, Any]
    runtime_data: EntityControllerManager


class FakeHass:
    pass


@pytest.mark.asyncio
async def test_diagnostics_are_stable_and_redact_sensitive_data() -> None:
    manager = EntityControllerManager(FakeHass(), object())
    first = ControllerRuntime(
        ControllerConfig(
            subentry_id="b-controller",
            name="Kitchen",
            trigger_entities=("binary_sensor.kitchen_motion",),
        )
    )
    first.state = ControllerState.ACTIVE_TIMER
    first.enabled = False
    first.stay_mode = True
    second = ControllerRuntime(
        ControllerConfig(subentry_id="a-controller", name="Hall")
    )
    manager.controllers = {
        "b-controller": first,
        "a-controller": second,
    }
    manager.controller_errors["b-controller"] = "state registry unavailable"
    entry = FakeEntry(
        "entry-id",
        {
            "api_token": "secret-token",
            "plain": "visible",
            "nested": {"password": "secret-password"},
        },
        manager,
    )

    diagnostics = await async_get_config_entry_diagnostics(FakeHass(), entry)

    assert diagnostics["entry"]["data"] == {
        "api_token": "**REDACTED**",
        "plain": "visible",
        "nested": {"password": "**REDACTED**"},
    }
    assert [controller["subentry_id"] for controller in diagnostics["controllers"]] == [
        "a-controller",
        "b-controller",
    ]
    assert diagnostics["controllers"][1]["state"] == "active_timer"
    assert diagnostics["controllers"][1]["enabled"] is False
    assert diagnostics["controllers"][1]["stay_mode"] is True
    assert diagnostics["controller_errors"] == {
        "b-controller": "state registry unavailable"
    }

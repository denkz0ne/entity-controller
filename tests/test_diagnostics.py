from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from custom_components.entity_controller.controller import (
    ControllerRuntime,
    ReconcileSnapshot,
)
from custom_components.entity_controller.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    ReconcileReason,
    TransitionCause,
)


@dataclass(frozen=True)
class FakeEntry:
    entry_id: str
    data: dict[str, Any]
    runtime_data: EntityControllerManager


class FakeHass:
    pass


@pytest.mark.asyncio
async def test_diagnostics_include_runtime_context_and_redact_sensitive_data() -> None:
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
    await first.async_transition(
        ControllerState.BLOCKED,
        TransitionCause.MANUAL_CONTROL,
        source_entity_id="light.kitchen",
    )
    await first.async_reconcile(
        ReconcileReason.RESTORE,
        ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=False,
            interlock_active=True,
            sensor_active=True,
            state_entities_on=True,
            active_interlocks=("input_boolean.maintenance",),
            active_triggers=("binary_sensor.kitchen_motion",),
        ),
    )
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
    assert diagnostics["controllers"][1]["state"] == "blocked"
    assert diagnostics["controllers"][1]["enabled"] is True
    assert diagnostics["controllers"][1]["stay_mode"] is True
    runtime_diagnostics = diagnostics["controllers"][1]
    assert runtime_diagnostics["last_transition_source"] == "light.kitchen"
    assert runtime_diagnostics["active_interlocks"] == [
        "input_boolean.maintenance"
    ]
    assert runtime_diagnostics["active_triggers"] == [
        "binary_sensor.kitchen_motion"
    ]
    assert runtime_diagnostics["block_reason"] == "interlock"
    assert runtime_diagnostics["last_action_at"] is None
    assert runtime_diagnostics["snapshot_generation"] == 0
    assert runtime_diagnostics["selected_exit_strategy"] == "off"
    assert runtime_diagnostics["restore_skipped_manual"] is False
    assert runtime_diagnostics["config"]["trigger_entities"] == [
        "binary_sensor.kitchen_motion"
    ]
    assert diagnostics["controller_errors"] == {
        "b-controller": "state registry unavailable"
    }

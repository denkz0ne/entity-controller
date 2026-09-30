from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import ControllerState


@dataclass(frozen=True)
class FakeSubentry:
    subentry_id: str
    data: dict[str, Any]


class FakeState:
    def __init__(self, state: str) -> None:
        self.state = state
        self.context = None


class FakeStates:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = values or {}

    def get(self, entity_id: str) -> FakeState | None:
        if entity_id not in self._values:
            return None
        return FakeState(self._values[entity_id])


class FakeHass:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.states = FakeStates(values)
        self.listeners: dict[str, list[Any]] = {}

    def track_state(self, entity_id: str, callback: Any) -> Any:
        self.listeners.setdefault(entity_id, []).append(callback)

        def _remove() -> None:
            self.listeners[entity_id].remove(callback)

        return _remove

    async def fire_state_change(
        self,
        entity_id: str,
        new_state: str,
        *,
        old_state: str = "off",
        context: Any = None,
    ) -> None:
        self.states._values[entity_id] = new_state
        callbacks = list(self.listeners.get(entity_id, ()))
        event = {
            "entity_id": entity_id,
            "old_state": FakeState(old_state),
            "new_state": FakeState(new_state),
            "context": context,
        }
        for callback in callbacks:
            await callback(event)

    def listener_count(self) -> int:
        return sum(len(callbacks) for callbacks in self.listeners.values())


class FakeEntry:
    entry_id = "entry-id"


def subentry(subentry_id: str = "controller-a", **data: Any) -> FakeSubentry:
    return FakeSubentry(
        subentry_id,
        {
            "name": "Controller A",
            "delay_seconds": 30,
            **data,
        },
    )


@pytest.mark.asyncio
async def test_add_controller_reconciles_control_entity_on_without_forcing_off() -> None:
    hass = FakeHass({"light.hall": "on"})
    manager = EntityControllerManager(hass, FakeEntry())

    runtime = await manager.async_add_controller(
        subentry(control_entities=("light.hall",), state_entities=("light.hall",))
    )

    assert runtime.state is ControllerState.BLOCKED
    assert runtime.last_reconcile_reason.value == "startup"


@pytest.mark.asyncio
async def test_manager_routes_multiple_trigger_entities_to_one_controller() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(trigger_entities=("binary_sensor.one", "binary_sensor.two"))
    )

    await hass.fire_state_change("binary_sensor.one", "on")
    await hass.fire_state_change("binary_sensor.two", "on")

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.last_triggered_by == "binary_sensor.two"
    assert runtime.trigger_generation == 2


@pytest.mark.asyncio
async def test_external_override_helper_updates_controller_immediately() -> None:
    hass = FakeHass({"input_boolean.guest": "off"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(override_entities=("input_boolean.guest",))
    )

    await hass.fire_state_change("input_boolean.guest", "on")

    assert runtime.state is ControllerState.OVERRIDDEN
    assert runtime.overridden_by == "input_boolean.guest"


@pytest.mark.asyncio
async def test_remove_controller_cleans_up_all_registered_callbacks() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.one", "binary_sensor.two"),
            override_entities=("input_boolean.override",),
            interlock_entities=("input_boolean.block",),
        )
    )

    assert hass.listener_count() == 4

    await manager.async_remove_controller("controller-a")

    assert "controller-a" not in manager.controllers
    assert hass.listener_count() == 0

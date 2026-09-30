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


class BrokenStates:
    def get(self, entity_id: str) -> Any:
        if entity_id == "binary_sensor.broken":
            raise RuntimeError("state registry unavailable for this entity")
        return None


class FakeHass:
    def __init__(self) -> None:
        self.states = BrokenStates()
        self.listeners: dict[str, list[Any]] = {}

    def track_state(self, entity_id: str, callback: Any) -> Any:
        self.listeners.setdefault(entity_id, []).append(callback)

        def _remove() -> None:
            self.listeners[entity_id].remove(callback)

        return _remove


class FakeEntry:
    entry_id = "entry-id"


@pytest.mark.asyncio
async def test_unavailable_trigger_isolated_to_its_controller() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())

    broken = await manager.async_add_controller(
        FakeSubentry(
            "broken",
            {
                "name": "Broken",
                "trigger_entities": ("binary_sensor.broken",),
            },
        )
    )
    healthy = await manager.async_add_controller(
        FakeSubentry(
            "healthy",
            {
                "name": "Healthy",
                "trigger_entities": ("binary_sensor.healthy",),
            },
        )
    )

    assert broken.state is ControllerState.DISABLED
    assert healthy.state is ControllerState.IDLE
    assert manager.controller_errors["broken"]
    assert "healthy" not in manager.controller_errors

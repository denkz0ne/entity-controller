from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

import pytest

from custom_components.entity_controller.controller import ControllerRuntime
from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    TransitionBehavior,
)


class FakeScheduledCall:
    def __init__(self, when: datetime, callback: Callable[[], Awaitable[None]]) -> None:
        self.when = when
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[FakeScheduledCall] = []

    def __call__(
        self, when: datetime, callback: Callable[[], Awaitable[None]]
    ) -> Callable[[], None]:
        call = FakeScheduledCall(when, callback)
        self.calls.append(call)
        return call.cancel


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

    def listener_count(self, entity_id: str) -> int:
        return len(self.listeners.get(entity_id, ()))


class FakeEntry:
    entry_id = "entry-id"


def subentry(**data: Any) -> FakeSubentry:
    return FakeSubentry("controller-a", {"name": "Controller A", **data})


@pytest.mark.asyncio
async def test_shortening_active_delay_reschedules_from_original_trigger_time() -> None:
    now = [datetime(2026, 9, 30, 12, 0, tzinfo=UTC)]
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=120),
        clock=lambda: now[0],
        schedule_at=scheduler,
    )
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    now[0] += timedelta(seconds=30)
    await runtime.async_apply_config(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=60)
    )

    assert scheduler.calls[0].cancelled is True
    assert runtime.expires_at == datetime(2026, 9, 30, 12, 1, tzinfo=UTC)
    assert scheduler.calls[-1].when == runtime.expires_at


@pytest.mark.asyncio
async def test_new_expiry_already_elapsed_evaluates_once_without_stale_callback() -> None:
    now = [datetime(2026, 9, 30, 12, 0, tzinfo=UTC)]
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=120),
        clock=lambda: now[0],
        schedule_at=scheduler,
    )
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    stale = scheduler.calls[0]

    now[0] += timedelta(seconds=90)
    await runtime.async_apply_config(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=30)
    )

    assert runtime.state is ControllerState.IDLE
    assert stale.cancelled is True
    await stale.callback()
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
async def test_manager_reconfigure_adds_and_removes_trigger_listeners() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(trigger_entities=("binary_sensor.one",))
    )

    updated = await manager.async_update_controller(
        subentry(trigger_entities=("binary_sensor.two",))
    )

    assert updated is runtime
    assert hass.listener_count("binary_sensor.one") == 0
    assert hass.listener_count("binary_sensor.two") == 1


@pytest.mark.asyncio
async def test_helper_newly_selected_while_on_reconciles_to_overridden() -> None:
    hass = FakeHass({"input_boolean.guest": "on"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(subentry())

    updated = await manager.async_update_controller(
        subentry(override_entities=("input_boolean.guest",))
    )

    assert updated is runtime
    assert runtime.state is ControllerState.OVERRIDDEN


@pytest.mark.asyncio
async def test_reconfigure_does_not_execute_idle_off_behavior() -> None:
    calls: list[TransitionBehavior] = []
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=120),
        behavior_executor=lambda behavior: calls.append(behavior),
    )

    await runtime.async_apply_config(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=60)
    )

    assert runtime.state is ControllerState.IDLE
    assert calls == []

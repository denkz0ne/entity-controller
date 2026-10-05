from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

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
        self.service_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.services = self

    def track_state(self, entity_id: str, callback: Any) -> Any:
        self.listeners.setdefault(entity_id, []).append(callback)

        def _remove() -> None:
            self.listeners[entity_id].remove(callback)

        return _remove

    def listener_count(self, entity_id: str) -> int:
        return len(self.listeners.get(entity_id, ()))

    async def fire_state_change(
        self,
        entity_id: str,
        new_state: str,
    ) -> None:
        old_state = self.states.get(entity_id)
        self.states._values[entity_id] = new_state
        event = {
            "entity_id": entity_id,
            "old_state": old_state,
            "new_state": FakeState(new_state),
            "context": None,
        }
        for callback in list(self.listeners.get(entity_id, ())):
            await callback(event)

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        blocking: bool,
        context: Any,
    ) -> None:
        self.service_calls.append((domain, service, data))


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
async def test_adding_active_interlock_while_active_reconciles_to_blocked() -> None:
    hass = FakeHass(
        {"binary_sensor.motion": "on", "input_boolean.maintenance": "on"}
    )
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(trigger_entities=("binary_sensor.motion",), delay_seconds=300)
    )
    assert runtime.state is ControllerState.ACTIVE_TIMER

    await manager.async_update_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            interlock_entities=("input_boolean.maintenance",),
            delay_seconds=300,
        )
    )

    assert runtime.state is ControllerState.BLOCKED
    assert runtime.active_interlocks == ("input_boolean.maintenance",)
    assert runtime.expires_at is None


@pytest.mark.asyncio
async def test_adding_closed_constraint_while_active_reconciles_safely() -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    hass = FakeHass({"binary_sensor.motion": "on"})
    manager = EntityControllerManager(hass, FakeEntry(), now=lambda: now)
    runtime = await manager.async_add_controller(
        subentry(trigger_entities=("binary_sensor.motion",), delay_seconds=300)
    )
    assert runtime.state is ControllerState.ACTIVE_TIMER

    await manager.async_update_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            delay_seconds=300,
            constraint_window={
                "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
            },
        )
    )

    assert runtime.state is ControllerState.CONSTRAINED
    assert runtime.expires_at is None


@pytest.mark.asyncio
async def test_removing_constraint_reconciles_current_trigger_without_actions() -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    hass = FakeHass({"binary_sensor.motion": "on"})
    manager = EntityControllerManager(hass, FakeEntry(), now=lambda: now)
    closed_constraint = {
        "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
        "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
    }
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
            constraint_window=closed_constraint,
        )
    )
    assert runtime.state is ControllerState.CONSTRAINED

    await manager.async_update_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
        )
    )

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert hass.service_calls == []


@pytest.mark.asyncio
async def test_reconfigure_preserves_event_timer_after_trigger_releases() -> None:
    hass = FakeHass(
        {"binary_sensor.motion": "on", "light.hall": "off"}
    )
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
            delay_seconds=120,
        )
    )

    await hass.fire_state_change("binary_sensor.motion", "off")
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.sensor_active is False

    await manager.async_update_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
            delay_seconds=90,
        )
    )

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.expires_at is not None


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


@pytest.mark.asyncio
async def test_reconfiguring_block_timeout_reschedules_block_timer() -> None:
    now = [datetime(2026, 9, 30, 12, 0, tzinfo=UTC)]
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(
            subentry_id="test",
            name="Test",
            block_timeout_seconds=120,
        ),
        clock=lambda: now[0],
        schedule_at=scheduler,
    )
    runtime.state = ControllerState.BLOCKED
    runtime.blocked_at = now[0]
    runtime._schedule_block_timer()
    original = scheduler.calls[-1]

    await runtime.async_apply_config(
        ControllerConfig(
            subentry_id="test",
            name="Test",
            block_timeout_seconds=30,
        )
    )

    assert original.cancelled is True
    assert runtime.block_expires_at == now[0] + timedelta(seconds=30)
    assert scheduler.calls[-1].when == runtime.block_expires_at

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
    ReconcileReason,
)
from custom_components.entity_controller.storage import (
    apply_controller_restore_state,
    capture_controller_restore_state,
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


class RecoveringStates:
    def __init__(self) -> None:
        self.raise_for: set[str] = {"binary_sensor.motion"}
        self.values: dict[str, str] = {}

    def get(self, entity_id: str) -> Any:
        if entity_id in self.raise_for:
            raise RuntimeError("state registry unavailable")
        return type("State", (), {"state": self.values.get(entity_id, "off")})()


class FakeHass:
    def __init__(self) -> None:
        self.states = RecoveringStates()

    def track_state(self, _entity_id: str, _callback: Any) -> Callable[[], None]:
        return lambda: None


class FakeEntry:
    entry_id = "entry-id"


@dataclass(frozen=True)
class FakeSubentry:
    subentry_id: str
    data: dict[str, Any]


@pytest.mark.asyncio
async def test_active_timer_restore_reschedules_without_replaying_transition_actions() -> None:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    calls: list[str] = []
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="hall", name="Hall", delay_seconds=30),
        behavior_executor=lambda behavior: calls.append(behavior.value) or _done(),
        clock=lambda: now,
        schedule_at=scheduler,
    )
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    restore_state = capture_controller_restore_state(runtime)

    restored_scheduler = FakeScheduler()
    restored = ControllerRuntime(
        runtime.config,
        behavior_executor=lambda behavior: calls.append(behavior.value) or _done(),
        clock=lambda: now,
        schedule_at=restored_scheduler,
    )
    apply_controller_restore_state(restored, restore_state)

    assert restored.state is ControllerState.ACTIVE_TIMER
    assert restored.expires_at == now + timedelta(seconds=30)
    assert [call.when for call in restored_scheduler.calls] == [restored.expires_at]
    assert calls == ["on"]


@pytest.mark.asyncio
async def test_enabled_and_stay_mode_restore_as_controller_owned_state() -> None:
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="hall", name="Hall", stay_mode_default=False)
    )
    runtime.enabled = False
    runtime.stay_mode = True

    restore_state = capture_controller_restore_state(runtime)
    restored = ControllerRuntime(runtime.config)
    apply_controller_restore_state(restored, restore_state)

    assert restored.enabled is False
    assert restored.stay_mode is True
    assert restored.state is ControllerState.DISABLED


@pytest.mark.asyncio
async def test_unavailable_entity_error_clears_when_reconcile_recovers() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        FakeSubentry(
            "hall",
            {
                "name": "Hall",
                "trigger_entities": ("binary_sensor.motion",),
            },
        )
    )

    assert runtime.state is ControllerState.DISABLED
    assert "hall" in manager.controller_errors

    hass.states.raise_for.clear()
    await manager.async_reconcile_controller("hall", ReconcileReason.RESTORE)

    assert runtime.state is ControllerState.IDLE
    assert "hall" not in manager.controller_errors


async def _done() -> None:
    return None

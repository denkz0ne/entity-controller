from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.entity_controller.controller import (
    ControllerRuntime,
    ReconcileSnapshot,
)
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    ReconcileReason,
    SensorType,
    TransitionCause,
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


@pytest.mark.asyncio
async def test_backoff_uses_factor_and_caps_at_maximum() -> None:
    now = [datetime(2026, 9, 30, 12, 0, tzinfo=UTC)]
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(
            subentry_id="test",
            name="Test",
            delay_seconds=10,
            backoff_enabled=True,
            backoff_factor=2,
            backoff_max_seconds=25,
        ),
        clock=lambda: now[0],
        schedule_at=scheduler,
    )

    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.effective_delay_seconds == 10
    assert runtime.backoff_count == 0
    assert runtime.expires_at == now[0] + timedelta(seconds=10)

    now[0] += timedelta(seconds=1)
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert scheduler.calls[0].cancelled is True
    assert runtime.effective_delay_seconds == 20
    assert runtime.backoff_count == 1

    now[0] += timedelta(seconds=1)
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.effective_delay_seconds == 25
    assert runtime.backoff_count == 2


@pytest.mark.asyncio
async def test_stale_cancelled_timer_callback_does_not_transition() -> None:
    now = [datetime(2026, 9, 30, 12, 0, tzinfo=UTC)]
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="test", name="Test", delay_seconds=10),
        clock=lambda: now[0],
        schedule_at=scheduler,
    )

    await runtime.async_handle_sensor_on("binary_sensor.motion")
    stale = scheduler.calls[0]
    now[0] += timedelta(seconds=2)
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert stale.cancelled is True
    await stale.callback()
    assert runtime.state is ControllerState.ACTIVE_TIMER

    await scheduler.calls[-1].callback()
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
async def test_duration_sensor_on_ignores_timer_expiry_until_sensor_off() -> None:
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(
            subentry_id="test",
            name="Test",
            delay_seconds=10,
            sensor_type=SensorType.DURATION,
        ),
        schedule_at=scheduler,
    )

    await runtime.async_handle_sensor_on("binary_sensor.motion")
    await scheduler.calls[-1].callback()

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.timer_expired_pending_sensor is True
    assert runtime.expires_at is None


@pytest.mark.asyncio
async def test_block_timeout_is_scheduled_and_reactivates_event_controller() -> None:
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(
            subentry_id="hall",
            name="Hall",
            block_timeout_seconds=60,
        ),
        schedule_at=scheduler,
    )
    runtime.state_entities_on = True

    await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert runtime.state is ControllerState.BLOCKED
    assert runtime.block_expires_at is not None
    block_call = scheduler.calls[-1]
    await block_call.callback()
    assert runtime.state is ControllerState.ACTIVE_TIMER


@pytest.mark.asyncio
async def test_interlock_cancels_block_timeout_and_stays_blocked_after_stale_callback() -> None:
    scheduler = FakeScheduler()
    runtime = ControllerRuntime(
        ControllerConfig(
            subentry_id="hall",
            name="Hall",
            block_timeout_seconds=1,
        ),
        schedule_at=scheduler,
    )
    await runtime.async_transition(ControllerState.BLOCKED, TransitionCause.SERVICE)
    stale_block_timer = scheduler.calls[-1]

    await runtime.async_reconcile(
        ReconcileReason.RESTORE,
        ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=False,
            interlock_active=True,
            sensor_active=False,
            state_entities_on=False,
            active_interlocks=("input_boolean.maintenance",),
        ),
    )

    assert stale_block_timer.cancelled is True
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.blocked_by == "input_boolean.maintenance"
    assert runtime.block_reason == "interlock"
    assert runtime.block_expires_at is None

    await stale_block_timer.callback()
    expired = await runtime.async_handle_block_timer_expired()

    assert expired is False
    assert runtime.state is ControllerState.BLOCKED


@pytest.mark.asyncio
async def test_reconcile_honors_constraint_and_override_priority_over_interlock() -> None:
    runtime = ControllerRuntime(ControllerConfig(subentry_id="hall", name="Hall"))

    state = await runtime.async_reconcile(
        ReconcileReason.RESTORE,
        ReconcileSnapshot(
            enabled=True,
            constrained=True,
            override_active=True,
            interlock_active=True,
            sensor_active=False,
            state_entities_on=False,
            active_overrides=("input_boolean.guest",),
            active_interlocks=("input_boolean.maintenance",),
        ),
    )
    assert state is ControllerState.CONSTRAINED

    state = await runtime.async_reconcile(
        ReconcileReason.RESTORE,
        ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=True,
            interlock_active=True,
            sensor_active=False,
            state_entities_on=False,
            active_overrides=("input_boolean.guest",),
            active_interlocks=("input_boolean.maintenance",),
        ),
    )
    assert state is ControllerState.OVERRIDDEN

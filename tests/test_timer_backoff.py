from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

import pytest

from custom_components.entity_controller.controller import ControllerRuntime
from custom_components.entity_controller.model import ControllerConfig, ControllerState, SensorType


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

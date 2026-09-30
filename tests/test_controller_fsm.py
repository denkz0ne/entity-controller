from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.entity_controller.controller import ControllerRuntime, ReconcileSnapshot
from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    ReconcileReason,
    SensorType,
    TransitionBehavior,
    TransitionCause,
)


class BehaviorRecorder:
    def __init__(self) -> None:
        self.calls: list[TransitionBehavior] = []

    async def __call__(self, behavior: TransitionBehavior) -> None:
        self.calls.append(behavior)


def make_runtime(
    *,
    sensor_type: SensorType = SensorType.EVENT,
    blocking_enabled: bool = True,
    stay: bool = False,
    recorder: BehaviorRecorder | None = None,
) -> ControllerRuntime:
    config = ControllerConfig(
        subentry_id="test",
        name="Test",
        sensor_type=sensor_type,
        blocking_enabled=blocking_enabled,
        stay_mode_default=stay,
    )
    return ControllerRuntime(config, behavior_executor=recorder)


@pytest.mark.asyncio
async def test_event_sensor_idle_to_active_timer() -> None:
    runtime = make_runtime()

    changed = await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert changed is True
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.last_triggered_by == "binary_sensor.motion"
    assert runtime.last_transition_cause is TransitionCause.SENSOR_TRIGGER


@pytest.mark.asyncio
async def test_event_sensor_retrigger_keeps_active_and_updates_trigger_time() -> None:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    current = [now]
    runtime = make_runtime()
    runtime._clock = lambda: current[0]

    await runtime.async_handle_sensor_on("binary_sensor.motion")
    first = runtime.last_triggered_at
    current[0] = now + timedelta(seconds=30)
    changed = await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert changed is False
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.last_triggered_at == first + timedelta(seconds=30)
    assert runtime.trigger_generation == 2


@pytest.mark.asyncio
async def test_duration_sensor_waits_for_sensor_off_after_timer_expiry() -> None:
    runtime = make_runtime(sensor_type=SensorType.DURATION)
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    changed = await runtime.async_handle_timer_expired()

    assert changed is False
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.timer_expired_pending_sensor is True

    changed = await runtime.async_handle_sensor_off("binary_sensor.motion")

    assert changed is True
    assert runtime.state is ControllerState.IDLE
    assert runtime.timer_expired_pending_sensor is False


@pytest.mark.asyncio
async def test_manual_state_change_while_active_enters_blocked() -> None:
    runtime = make_runtime(blocking_enabled=True)
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    changed = await runtime.async_handle_state_entity_change(
        "light.hall", is_on=True, is_own_context=False
    )

    assert changed is True
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.blocked_by == "light.hall"
    assert runtime.last_transition_cause is TransitionCause.MANUAL_CONTROL


@pytest.mark.asyncio
async def test_own_state_change_does_not_block_controller() -> None:
    runtime = make_runtime(blocking_enabled=True)
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    changed = await runtime.async_handle_state_entity_change(
        "light.hall", is_on=True, is_own_context=True
    )

    assert changed is False
    assert runtime.state is ControllerState.ACTIVE_TIMER


@pytest.mark.asyncio
async def test_override_enter_and_leave_reconciles_event_sensor() -> None:
    runtime = make_runtime(sensor_type=SensorType.EVENT)
    await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert await runtime.async_handle_override_change(
        "input_boolean.override", is_active=True
    )
    assert runtime.state is ControllerState.OVERRIDDEN
    assert runtime.overridden_by == "input_boolean.override"

    runtime.state_entities_on = True
    runtime.sensor_active = False
    assert await runtime.async_handle_override_change(
        "input_boolean.override", is_active=False
    )
    assert runtime.state is ControllerState.ACTIVE_TIMER


@pytest.mark.asyncio
async def test_stay_mode_activates_active_stay_on() -> None:
    runtime = make_runtime(stay=True)

    assert await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.ACTIVE_STAY_ON


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected_without_side_effect() -> None:
    recorder = BehaviorRecorder()
    runtime = make_runtime(recorder=recorder)
    runtime.state = ControllerState.DISABLED

    changed = await runtime.async_transition(
        ControllerState.ACTIVE_TIMER,
        TransitionCause.SERVICE,
    )

    assert changed is False
    assert runtime.state is ControllerState.DISABLED
    assert recorder.calls == []


@pytest.mark.asyncio
async def test_reconcile_to_idle_does_not_run_enter_idle_action() -> None:
    recorder = BehaviorRecorder()
    runtime = make_runtime(recorder=recorder)
    runtime.state = ControllerState.BLOCKED

    state = await runtime.async_reconcile(
        ReconcileReason.STARTUP,
        ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=False,
            interlock_active=False,
            sensor_active=False,
            state_entities_on=False,
        ),
    )

    assert state is ControllerState.IDLE
    assert runtime.state is ControllerState.IDLE
    assert recorder.calls == []

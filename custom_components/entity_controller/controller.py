"""Explicit async state machine for Entity Controller v10."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .model import (
    ControllerConfig,
    ControllerState,
    ReconcileReason,
    SensorType,
    TransitionBehavior,
    TransitionCause,
)

BehaviorExecutor = Callable[[TransitionBehavior], Awaitable[None]]
TimerCallback = Callable[[], Awaitable[None]]
ScheduleAt = Callable[[datetime, TimerCallback], Callable[[], None]]


@dataclass(frozen=True, slots=True)
class ReconcileSnapshot:
    """Observed Home Assistant state used for side-effect-free reconciliation."""

    enabled: bool
    constrained: bool
    override_active: bool
    interlock_active: bool
    sensor_active: bool
    state_entities_on: bool


_ALLOWED_TRANSITIONS: dict[ControllerState, frozenset[ControllerState]] = {
    ControllerState.IDLE: frozenset(
        {
            ControllerState.ACTIVE_TIMER,
            ControllerState.ACTIVE_STAY_ON,
            ControllerState.BLOCKED,
            ControllerState.OVERRIDDEN,
            ControllerState.CONSTRAINED,
            ControllerState.DISABLED,
        }
    ),
    ControllerState.ACTIVE_TIMER: frozenset(
        {
            ControllerState.IDLE,
            ControllerState.ACTIVE_STAY_ON,
            ControllerState.BLOCKED,
            ControllerState.OVERRIDDEN,
            ControllerState.CONSTRAINED,
            ControllerState.DISABLED,
        }
    ),
    ControllerState.ACTIVE_STAY_ON: frozenset(
        {
            ControllerState.IDLE,
            ControllerState.ACTIVE_TIMER,
            ControllerState.BLOCKED,
            ControllerState.OVERRIDDEN,
            ControllerState.CONSTRAINED,
            ControllerState.DISABLED,
        }
    ),
    ControllerState.BLOCKED: frozenset(
        {
            ControllerState.IDLE,
            ControllerState.ACTIVE_TIMER,
            ControllerState.ACTIVE_STAY_ON,
            ControllerState.OVERRIDDEN,
            ControllerState.CONSTRAINED,
            ControllerState.DISABLED,
        }
    ),
    ControllerState.OVERRIDDEN: frozenset(
        {
            ControllerState.IDLE,
            ControllerState.ACTIVE_TIMER,
            ControllerState.ACTIVE_STAY_ON,
            ControllerState.BLOCKED,
            ControllerState.CONSTRAINED,
            ControllerState.DISABLED,
        }
    ),
    ControllerState.CONSTRAINED: frozenset(
        {
            ControllerState.IDLE,
            ControllerState.OVERRIDDEN,
            ControllerState.BLOCKED,
            ControllerState.DISABLED,
        }
    ),
    ControllerState.DISABLED: frozenset(
        {
            ControllerState.IDLE,
            ControllerState.BLOCKED,
            ControllerState.OVERRIDDEN,
            ControllerState.CONSTRAINED,
        }
    ),
}


def _behavior_state_name(state: ControllerState) -> str | None:
    if state in (ControllerState.ACTIVE_TIMER, ControllerState.ACTIVE_STAY_ON):
        return "active"
    if state is ControllerState.DISABLED:
        return None
    return state.value


class ControllerRuntime:
    """One controller's explicit FSM and observed runtime state."""

    def __init__(
        self,
        config: ControllerConfig,
        *,
        behavior_executor: BehaviorExecutor | None = None,
        clock: Callable[[], datetime] | None = None,
        schedule_at: ScheduleAt | None = None,
    ) -> None:
        self.config = config
        self.state = ControllerState.IDLE
        self._behavior_executor = behavior_executor
        self._clock = clock or (lambda: datetime.now(UTC))
        self._schedule_at = schedule_at

        self.enabled = True
        self.constrained = False
        self.override_active = False
        self.interlock_active = False
        self.sensor_active = False
        self.state_entities_on = False
        self.stay_mode = config.stay_mode_default

        self.last_triggered_by: str | None = None
        self.last_triggered_at: datetime | None = None
        self.last_transition_at: datetime | None = None
        self.last_transition_cause: TransitionCause | None = None
        self.last_reconcile_reason: ReconcileReason | None = None
        self.blocked_by: str | None = None
        self.overridden_by: str | None = None
        self.trigger_generation = 0
        self.timer_expired_pending_sensor = False
        self.backoff_count = 0
        self.effective_delay_seconds = config.delay_seconds
        self.expires_at: datetime | None = None
        self._timer_cancel: Callable[[], None] | None = None
        self._timer_generation = 0

    @staticmethod
    def _is_active_state(state: ControllerState) -> bool:
        return state in (ControllerState.ACTIVE_TIMER, ControllerState.ACTIVE_STAY_ON)

    def _cancel_timer(self) -> None:
        if self._timer_cancel is not None:
            self._timer_cancel()
            self._timer_cancel = None
        self._timer_generation += 1
        self.expires_at = None

    def _calculate_effective_delay(self) -> float:
        if not self.config.backoff_enabled or self.backoff_count == 0:
            return self.config.delay_seconds
        delay = self.config.delay_seconds * (self.config.backoff_factor ** self.backoff_count)
        return min(delay, self.config.backoff_max_seconds)

    def _schedule_main_timer(self, *, reset: bool) -> None:
        self._cancel_timer()
        if reset and self.config.backoff_enabled:
            self.backoff_count += 1
        elif not reset:
            self.backoff_count = 0

        self.effective_delay_seconds = self._calculate_effective_delay()
        self._schedule_timer_at(
            self._clock() + timedelta(seconds=self.effective_delay_seconds)
        )

    def _schedule_timer_at(self, expires_at: datetime) -> None:
        self.expires_at = expires_at
        self._timer_generation += 1
        generation = self._timer_generation

        async def _expire() -> None:
            if generation != self._timer_generation:
                return
            if self.state is not ControllerState.ACTIVE_TIMER:
                return
            self._timer_cancel = None
            self.expires_at = None
            await self.async_handle_timer_expired()

        if self._schedule_at is not None:
            self._timer_cancel = self._schedule_at(self.expires_at, _expire)

    async def async_reset_timer(self) -> None:
        """Reset the active timer and apply backoff when configured."""

        if self.state is ControllerState.ACTIVE_TIMER:
            self._schedule_main_timer(reset=True)

    async def async_start(self) -> None:
        """Start runtime-owned resources."""

    async def async_stop(self) -> None:
        """Stop runtime-owned resources and cancel pending callbacks."""

        self._cancel_timer()

    async def async_apply_config(self, new_config: ControllerConfig) -> None:
        """Apply changed configuration without rebuilding runtime state."""

        was_active_timer = self.state is ControllerState.ACTIVE_TIMER
        trigger_base = self.last_triggered_at
        self.config = new_config
        self.effective_delay_seconds = self._calculate_effective_delay()

        if not was_active_timer:
            return

        self._cancel_timer()
        base = trigger_base or self._clock()
        expires_at = base + timedelta(seconds=self.effective_delay_seconds)
        if expires_at <= self._clock():
            await self.async_handle_timer_expired()
            return
        self._schedule_timer_at(expires_at)

    @property
    def _active_target(self) -> ControllerState:
        return (
            ControllerState.ACTIVE_STAY_ON
            if self.stay_mode
            else ControllerState.ACTIVE_TIMER
        )

    async def _execute_behavior(self, key: str) -> None:
        behavior = self.config.transition_behaviors.get(
            key, TransitionBehavior.IGNORE
        )
        if behavior is TransitionBehavior.IGNORE or self._behavior_executor is None:
            return
        await self._behavior_executor(behavior)

    async def async_transition(
        self,
        target: ControllerState,
        cause: TransitionCause,
        *,
        source_entity_id: str | None = None,
    ) -> bool:
        """Transition through the FSM and execute configured enter/exit behavior."""

        if target is self.state:
            return False
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            return False

        source = self.state
        source_behavior = _behavior_state_name(source)
        target_behavior = _behavior_state_name(target)

        if source is ControllerState.ACTIVE_TIMER and target is not ControllerState.ACTIVE_TIMER:
            self._cancel_timer()

        if source_behavior is not None:
            await self._execute_behavior(f"on_exit_{source_behavior}")

        self.state = target
        self.last_transition_at = self._clock()
        self.last_transition_cause = cause

        if target is not ControllerState.BLOCKED:
            self.blocked_by = None
        if target is not ControllerState.OVERRIDDEN:
            self.overridden_by = None

        if target_behavior is not None:
            await self._execute_behavior(f"on_enter_{target_behavior}")

        if target is ControllerState.ACTIVE_TIMER and source is not ControllerState.ACTIVE_TIMER:
            self._schedule_main_timer(reset=False)
        elif not self._is_active_state(target):
            self.backoff_count = 0
            self.effective_delay_seconds = self.config.delay_seconds

        return True

    async def async_reconcile(
        self,
        reason: ReconcileReason,
        snapshot: ReconcileSnapshot | None = None,
    ) -> ControllerState:
        """Recompute logical state without transition enter/exit side effects."""

        if snapshot is not None:
            self.enabled = snapshot.enabled
            self.constrained = snapshot.constrained
            self.override_active = snapshot.override_active
            self.interlock_active = snapshot.interlock_active
            self.sensor_active = snapshot.sensor_active
            self.state_entities_on = snapshot.state_entities_on

        if not self.enabled:
            target = ControllerState.DISABLED
        elif self.constrained:
            target = ControllerState.CONSTRAINED
        elif self.override_active:
            target = ControllerState.OVERRIDDEN
        elif self.interlock_active:
            target = ControllerState.BLOCKED
        elif self.sensor_active:
            target = self._active_target
        elif self.state_entities_on and self.config.blocking_enabled:
            target = ControllerState.BLOCKED
        else:
            target = ControllerState.IDLE

        self.state = target
        self.last_reconcile_reason = reason
        if target is not ControllerState.BLOCKED:
            self.blocked_by = None
        if target is not ControllerState.OVERRIDDEN:
            self.overridden_by = None
        return target

    async def async_handle_sensor_on(self, entity_id: str) -> bool:
        """Handle an ON event from a configured trigger sensor."""

        self.sensor_active = True
        self.last_triggered_by = entity_id
        self.last_triggered_at = self._clock()
        self.trigger_generation += 1
        self.timer_expired_pending_sensor = False

        if self.state is ControllerState.ACTIVE_TIMER:
            await self.async_reset_timer()
            return False

        if self.state is ControllerState.IDLE:
            if self.state_entities_on and self.config.blocking_enabled:
                self.blocked_by = entity_id
                return await self.async_transition(
                    ControllerState.BLOCKED,
                    TransitionCause.SENSOR_TRIGGER,
                    source_entity_id=entity_id,
                )
            return await self.async_transition(
                self._active_target,
                TransitionCause.SENSOR_TRIGGER,
                source_entity_id=entity_id,
            )

        return False

    async def async_handle_sensor_off(self, entity_id: str) -> bool:
        """Handle an OFF event from a duration trigger sensor."""

        self.sensor_active = False
        self.last_triggered_by = entity_id
        if (
            self.config.sensor_type is SensorType.DURATION
            and self.state is ControllerState.ACTIVE_TIMER
            and self.config.sensor_resets_timer
        ):
            self.timer_expired_pending_sensor = False
            await self.async_reset_timer()
            return False

        if (
            self.config.sensor_type is SensorType.DURATION
            and self.state is ControllerState.ACTIVE_TIMER
            and self.timer_expired_pending_sensor
        ):
            self.timer_expired_pending_sensor = False
            return await self.async_transition(
                ControllerState.IDLE,
                TransitionCause.SENSOR_RELEASE,
                source_entity_id=entity_id,
            )
        return False

    async def async_handle_timer_expired(self) -> bool:
        """Apply v9-compatible event/duration expiry semantics."""

        if self.state is not ControllerState.ACTIVE_TIMER:
            return False
        self._timer_cancel = None
        self.expires_at = None
        if self.config.sensor_type is SensorType.DURATION and self.sensor_active:
            self.timer_expired_pending_sensor = True
            return False
        self.timer_expired_pending_sensor = False
        return await self.async_transition(
            ControllerState.IDLE,
            TransitionCause.TIMER_EXPIRED,
        )

    async def async_handle_state_entity_change(
        self,
        entity_id: str,
        *,
        is_on: bool,
        is_own_context: bool,
    ) -> bool:
        """Handle a significant state/control entity change."""

        self.state_entities_on = is_on
        if is_own_context:
            return False

        if self.state is ControllerState.ACTIVE_TIMER:
            if not is_on:
                return await self.async_transition(
                    ControllerState.IDLE,
                    TransitionCause.MANUAL_CONTROL,
                    source_entity_id=entity_id,
                )
            if self.config.blocking_enabled:
                self.blocked_by = entity_id
                return await self.async_transition(
                    ControllerState.BLOCKED,
                    TransitionCause.MANUAL_CONTROL,
                    source_entity_id=entity_id,
                )
            await self.async_reset_timer()
            return False

        if self.state in (ControllerState.BLOCKED, ControllerState.ACTIVE_STAY_ON):
            if not is_on:
                return await self.async_transition(
                    ControllerState.IDLE,
                    TransitionCause.MANUAL_CONTROL,
                    source_entity_id=entity_id,
                )

        return False

    async def async_handle_override_change(
        self,
        entity_id: str,
        *,
        is_active: bool,
    ) -> bool:
        """Handle a configured override entity changing state."""

        self.override_active = is_active
        if is_active:
            if self.state in (
                ControllerState.IDLE,
                ControllerState.ACTIVE_TIMER,
                ControllerState.ACTIVE_STAY_ON,
                ControllerState.BLOCKED,
            ):
                self.overridden_by = entity_id
                return await self.async_transition(
                    ControllerState.OVERRIDDEN,
                    TransitionCause.OVERRIDE,
                    source_entity_id=entity_id,
                )
            return False

        if self.state is not ControllerState.OVERRIDDEN:
            return False

        if not self.state_entities_on:
            target = ControllerState.IDLE
        elif self.config.sensor_type is SensorType.EVENT or self.sensor_active:
            target = self._active_target
        else:
            target = ControllerState.IDLE

        changed = await self.async_transition(
            target,
            TransitionCause.OVERRIDE,
            source_entity_id=entity_id,
        )
        if changed:
            self.overridden_by = None
        return changed

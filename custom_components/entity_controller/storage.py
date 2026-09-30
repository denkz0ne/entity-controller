"""Controller-owned restore state helpers for Entity Controller v10."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .controller import ControllerRuntime
from .model import ControllerState, ReconcileReason


@dataclass(frozen=True, slots=True)
class ControllerRestoreState:
    """Persistable runtime fields owned by Entity Controller."""

    state: str
    enabled: bool
    stay_mode: bool
    expires_at: datetime | None = None
    last_triggered_by: str | None = None
    last_triggered_at: datetime | None = None
    last_transition_at: datetime | None = None
    last_reconcile_reason: str | None = None


def capture_controller_restore_state(
    runtime: ControllerRuntime,
) -> ControllerRestoreState:
    """Capture the semantically valid runtime state EC owns."""

    return ControllerRestoreState(
        state=runtime.state.value,
        enabled=runtime.enabled,
        stay_mode=runtime.stay_mode,
        expires_at=runtime.expires_at,
        last_triggered_by=runtime.last_triggered_by,
        last_triggered_at=runtime.last_triggered_at,
        last_transition_at=runtime.last_transition_at,
        last_reconcile_reason=(
            runtime.last_reconcile_reason.value
            if runtime.last_reconcile_reason is not None
            else None
        ),
    )


def apply_controller_restore_state(
    runtime: ControllerRuntime,
    restore_state: ControllerRestoreState,
) -> None:
    """Apply restored EC-owned fields without replaying transition actions."""

    runtime.enabled = restore_state.enabled
    runtime.stay_mode = restore_state.stay_mode
    runtime.last_triggered_by = restore_state.last_triggered_by
    runtime.last_triggered_at = restore_state.last_triggered_at
    runtime.last_transition_at = restore_state.last_transition_at
    runtime.last_reconcile_reason = (
        ReconcileReason(restore_state.last_reconcile_reason)
        if restore_state.last_reconcile_reason is not None
        else None
    )

    if not runtime.enabled:
        runtime.state = ControllerState.DISABLED
        runtime._cancel_timer()
        return

    runtime.state = ControllerState(restore_state.state)
    if (
        runtime.state is ControllerState.ACTIVE_TIMER
        and restore_state.expires_at is not None
        and restore_state.expires_at > runtime._clock()
    ):
        runtime._schedule_timer_at(restore_state.expires_at)
        return

    runtime.expires_at = None

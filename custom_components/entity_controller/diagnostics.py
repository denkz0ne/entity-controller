"""Diagnostics support for Entity Controller v10."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .manager import EntityControllerManager

_REDACT_KEYS = ("password", "secret", "token")


async def async_get_config_entry_diagnostics(
    hass: Any,
    config_entry: Any,
) -> dict[str, Any]:
    """Return stable, redacted diagnostics for one EC config entry."""

    manager = getattr(config_entry, "runtime_data", None)
    if not isinstance(manager, EntityControllerManager):
        manager = None

    controllers = []
    if manager is not None:
        for subentry_id in sorted(manager.controllers):
            runtime = manager.controllers[subentry_id]
            controllers.append(
                {
                    "subentry_id": subentry_id,
                    "name": runtime.config.name,
                    "state": runtime.state.value,
                    "enabled": runtime.enabled,
                    "stay_mode": runtime.stay_mode,
                    "override_active": runtime.override_active,
                    "interlock_active": runtime.interlock_active,
                    "sensor_active": runtime.sensor_active,
                    "state_entities_on": runtime.state_entities_on,
                    "expires_at": runtime.expires_at.isoformat()
                    if runtime.expires_at is not None
                    else None,
                    "last_transition_at": runtime.last_transition_at.isoformat()
                    if runtime.last_transition_at is not None
                    else None,
                    "last_transition_cause": runtime.last_transition_cause.value
                    if runtime.last_transition_cause is not None
                    else None,
                    "last_transition_source": runtime.last_transition_source,
                    "last_reconcile_reason": runtime.last_reconcile_reason.value
                    if runtime.last_reconcile_reason is not None
                    else None,
                    "last_triggered_by": runtime.last_triggered_by,
                    "last_triggered_at": runtime.last_triggered_at.isoformat()
                    if runtime.last_triggered_at is not None
                    else None,
                    "blocked_by": runtime.blocked_by,
                    "blocked_at": runtime.blocked_at.isoformat()
                    if runtime.blocked_at is not None
                    else None,
                    "block_reason": runtime.block_reason,
                    "block_expires_at": runtime.block_expires_at.isoformat()
                    if runtime.block_expires_at is not None
                    else None,
                    "overridden_by": runtime.overridden_by,
                    "active_overrides": list(runtime.active_overrides),
                    "active_interlocks": list(runtime.active_interlocks),
                    "active_triggers": list(runtime.active_triggers),
                    "presence_active": runtime.presence_active,
                    "active_presence_entities": list(runtime.active_presence_entities),
                    "presence_hold_started_at": runtime.presence_hold_started_at.isoformat()
                    if runtime.presence_hold_started_at is not None else None,
                    "last_presence_changed_at": runtime.last_presence_changed_at.isoformat()
                    if runtime.last_presence_changed_at is not None else None,
                    "timer_expired_pending_presence": runtime.timer_expired_pending_presence,
                    "manual_control_kind": runtime.manual_control_kind,
                    "manual_control_entity": runtime.manual_control_entity,
                    "manual_control_at": runtime.manual_control_at.isoformat()
                    if runtime.manual_control_at is not None else None,
                    "manual_takeover_pending": runtime.manual_takeover_pending,
                    "manual_release_ready": runtime.manual_release_ready,
                    "snapshot_held": runtime.snapshot_held,
                    "last_action_hook": runtime.last_action_hook,
                    "last_action_result": runtime.last_action_result,
                    "last_action_error": runtime.last_action_error,
                    "last_action_at": runtime.last_action_at.isoformat()
                    if runtime.last_action_at is not None else None,
                    "snapshot_generation": runtime.snapshot_generation,
                    "selected_exit_strategy": runtime.selected_exit_strategy,
                    "restore_skipped_manual": runtime.restore_skipped_manual,
                    "active_state_entities": list(runtime.active_state_entities),
                    "effective_delay": runtime.effective_delay_seconds,
                    "backoff_count": runtime.backoff_count,
                    "timer_expired_pending_sensor": runtime.timer_expired_pending_sensor,
                    "profile": "night" if runtime.night_active else "day",
                    "config": _redact(
                        {
                            "trigger_entities": list(runtime.config.trigger_entities),
                            "presence_entities": list(runtime.config.presence_entities),
                            "presence_on_states": list(runtime.config.presence_on_states),
                            "presence_off_states": list(runtime.config.presence_off_states),
                            "protect_manual_off": runtime.config.protect_manual_off,
                            "protect_manual_on": runtime.config.protect_manual_on,
                            "control_entities": list(runtime.config.control_entities),
                            "state_entities": list(runtime.config.state_entities),
                            "override_entities": list(runtime.config.override_entities),
                            "interlock_entities": list(runtime.config.interlock_entities),
                            "delay_seconds": runtime.config.delay_seconds,
                            "backoff_enabled": runtime.config.backoff_enabled,
                            "constraint_window": runtime.config.constraint_window,
                            "night_mode": runtime.config.night_mode,
                        }
                    ),
                }
            )

    return {
        "entry": {
            "entry_id": getattr(config_entry, "entry_id", None),
            "data": _redact(getattr(config_entry, "data", {})),
        },
        "controllers": controllers,
        "controller_errors": dict(
            sorted((manager.controller_errors if manager is not None else {}).items())
        ),
    }


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "**REDACTED**" if _is_sensitive_key(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(marker in normalized for marker in _REDACT_KEYS)

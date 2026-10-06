"""Sensor platform for Entity Controller v10."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import ControllerRuntime
from .entity import EntityControllerEntity, controller_entity_add_kwargs


class EntityControllerStateSensor(EntityControllerEntity, SensorEntity):
    """Expose the exact controller FSM state."""

    _attr_icon = "mdi:state-machine"
    _attr_translation_key = "state"

    def __init__(
        self,
        runtime: ControllerRuntime,
        entry_id: str,
        *,
        diagnostic_key: str | None = None,
    ) -> None:
        super().__init__(
            runtime,
            entry_id,
            diagnostic_key or "state",
            "sensor",
            enabled_default=diagnostic_key is None,
        )
        self.diagnostic_key = diagnostic_key
        if diagnostic_key is not None:
            self._attr_translation_key = None

    @property
    def native_value(self) -> str:
        """Return the runtime FSM state value."""

        if self.diagnostic_key == "last_trigger":
            return (
                ""
                if self.runtime.last_triggered_at is None
                else self.runtime.last_triggered_at.isoformat()
            )
        return self.runtime.state.value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return useful runtime metadata without per-second countdown churn."""

        return {
            # Keep the original keys for automations created during early v10 RCs.
            "last_transition": self.runtime.last_transition_at,
            "transition_cause": None
            if self.runtime.last_transition_cause is None
            else self.runtime.last_transition_cause.value,
            "last_transition_at": self.runtime.last_transition_at,
            "last_transition_cause": None
            if self.runtime.last_transition_cause is None
            else self.runtime.last_transition_cause.value,
            "last_transition_source": self.runtime.last_transition_source,
            "last_reconcile_reason": None
            if self.runtime.last_reconcile_reason is None
            else self.runtime.last_reconcile_reason.value,
            "last_triggered_by": self.runtime.last_triggered_by,
            "last_triggered_at": self.runtime.last_triggered_at,
            "blocked_by": self.runtime.blocked_by,
            "blocked_at": self.runtime.blocked_at,
            "block_reason": self.runtime.block_reason,
            "block_expires_at": self.runtime.block_expires_at,
            "overridden_by": self.runtime.overridden_by,
            "active_overrides": list(self.runtime.active_overrides),
            "active_interlocks": list(self.runtime.active_interlocks),
            "active_triggers": list(self.runtime.active_triggers),
            "presence_active": self.runtime.presence_active,
            "active_presence_entities": list(self.runtime.active_presence_entities),
            "presence_hold_started_at": self.runtime.presence_hold_started_at,
            "last_presence_changed_at": self.runtime.last_presence_changed_at,
            "timer_expired_pending_presence": self.runtime.timer_expired_pending_presence,
            "manual_control_kind": self.runtime.manual_control_kind,
            "manual_control_entity": self.runtime.manual_control_entity,
            "manual_control_at": self.runtime.manual_control_at,
            "manual_takeover_pending": self.runtime.manual_takeover_pending,
            "manual_release_ready": self.runtime.manual_release_ready,
            "snapshot_held": self.runtime.snapshot_held,
            "last_action_hook": self.runtime.last_action_hook,
            "last_action_result": self.runtime.last_action_result,
            "last_action_error": self.runtime.last_action_error,
            "active_state_entities": list(self.runtime.active_state_entities),
            "enabled": self.runtime.enabled,
            "stay_mode": self.runtime.stay_mode,
            "override_active": self.runtime.override_active,
            "interlock_active": self.runtime.interlock_active,
            "sensor_active": self.runtime.sensor_active,
            "state_entities_on": self.runtime.state_entities_on,
            "effective_delay": self.runtime.effective_delay_seconds,
            "backoff_count": self.runtime.backoff_count,
            "timer_expired_pending_sensor": self.runtime.timer_expired_pending_sensor,
            "profile": "night" if self.runtime.night_active else "day",
            "expires_at": self.runtime.expires_at,
        }


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up controller state sensors."""

    manager = entry.runtime_data
    entities: dict[str, EntityControllerStateSensor] = {}

    def _add(runtime: ControllerRuntime) -> None:
        entity = EntityControllerStateSensor(runtime, entry.entry_id)
        entities[runtime.config.subentry_id] = entity
        async_add_entities(
            [entity], **controller_entity_add_kwargs(entry, runtime.config.subentry_id)
        )

    def _changed(event: str, subentry_id: str, runtime) -> None:
        if event == "added" and runtime is not None:
            _add(runtime)
        elif event == "removed" and (entity := entities.pop(subentry_id, None)):
            hass.async_create_task(entity.async_remove())

    for runtime in manager.controllers.values():
        _add(runtime)

    entry.async_on_unload(manager.add_controller_listener(_changed))

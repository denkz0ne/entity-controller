"""Sensor platform for Entity Controller v10."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import ControllerRuntime
from .entity import EntityControllerEntity


class EntityControllerStateSensor(EntityControllerEntity, SensorEntity):
    """Expose the exact controller FSM state."""

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
            enabled_default=diagnostic_key is None,
        )
        self.diagnostic_key = diagnostic_key

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
            "last_transition": self.runtime.last_transition_at,
            "transition_cause": None
            if self.runtime.last_transition_cause is None
            else self.runtime.last_transition_cause.value,
            "last_triggered_by": self.runtime.last_triggered_by,
            "last_triggered_at": self.runtime.last_triggered_at,
            "effective_delay": self.runtime.effective_delay_seconds,
            "profile": "night" if self.runtime.night_active else "day",
            "expires_at": self.runtime.expires_at,
            "block_expires_at": self.runtime.block_expires_at,
            "blocked_by": self.runtime.blocked_by,
            "overridden_by": self.runtime.overridden_by,
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
            [entity],
            config_subentry_id=runtime.config.subentry_id,
        )

    def _changed(event: str, subentry_id: str, runtime) -> None:
        if event == "added" and runtime is not None:
            _add(runtime)
        elif event == "removed" and (entity := entities.pop(subentry_id, None)):
            hass.async_create_task(entity.async_remove())

    for runtime in manager.controllers.values():
        _add(runtime)

    entry.async_on_unload(manager.add_controller_listener(_changed))

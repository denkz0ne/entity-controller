"""Binary sensor platform for Entity Controller v10."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import EntityControllerEntity
from .model import ControllerState


class EntityControllerBlockedBinarySensor(EntityControllerEntity, BinarySensorEntity):
    """Expose whether the controller is currently blocked."""

    _attr_icon = "mdi:shield-lock"
    _attr_translation_key = "blocked"

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "blocked")

    @property
    def is_on(self) -> bool:
        """Return whether the controller is blocked."""

        return self.runtime.state is ControllerState.BLOCKED

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return blocked reason/source metadata."""

        return {
            "reason": None
            if self.runtime.last_transition_cause is None
            else self.runtime.last_transition_cause.value,
            "blocked_by": self.runtime.blocked_by,
            "block_expires_at": self.runtime.block_expires_at,
        }


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up blocked binary sensors."""

    manager = entry.runtime_data
    entities: dict[str, EntityControllerBlockedBinarySensor] = {}

    def _add(runtime) -> None:
        entity = EntityControllerBlockedBinarySensor(runtime, entry.entry_id)
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

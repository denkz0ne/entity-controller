"""Button platform for Entity Controller v10."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .actions import async_activate
from .entity import EntityControllerEntity, controller_entity_add_kwargs


class EntityControllerActivateButton(EntityControllerEntity, ButtonEntity):
    """Activate a controller."""

    _attr_icon = "mdi:play-circle"
    _attr_translation_key = "activate"

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "activate", "button")

    async def async_press(self) -> None:
        """Activate the controller."""

        await async_activate(self.runtime)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up controller action buttons."""

    manager = entry.runtime_data
    entities: dict[str, EntityControllerActivateButton] = {}

    def _add(runtime) -> None:
        entity = EntityControllerActivateButton(runtime, entry.entry_id)
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

"""Switch platform for Entity Controller v10."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import EntityControllerEntity


class EntityControllerEnabledSwitch(EntityControllerEntity, SwitchEntity):
    """Enable or disable EC decisions for one controller."""

    _attr_icon = "mdi:toggle-switch"
    _attr_translation_key = "enabled"

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "enabled")

    @property
    def is_on(self) -> bool:
        """Return whether controller decision-making is enabled."""

        return self.runtime.enabled

    async def async_turn_off(self, **kwargs) -> None:
        """Disable EC decisions without turning controlled loads off."""

        await self.runtime.async_set_enabled(False)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable EC decisions and reconcile current reality."""

        await self.runtime.async_set_enabled(True)


class EntityControllerStayModeSwitch(EntityControllerEntity, SwitchEntity):
    """Control runtime stay mode."""

    _attr_icon = "mdi:pin"
    _attr_translation_key = "stay_mode"

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "stay_mode")

    @property
    def is_on(self) -> bool:
        """Return whether stay mode is active."""

        return self.runtime.stay_mode

    async def async_turn_on(self, **kwargs) -> None:
        """Enable stay mode."""

        await self.runtime.async_set_stay_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable stay mode."""

        await self.runtime.async_set_stay_mode(False)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up controller switches."""

    manager = entry.runtime_data
    entities: dict[str, list[EntityControllerEntity]] = {}

    def _add(runtime) -> None:
        controller_entities = [
            EntityControllerEnabledSwitch(runtime, entry.entry_id),
            EntityControllerStayModeSwitch(runtime, entry.entry_id),
        ]
        entities[runtime.config.subentry_id] = controller_entities
        async_add_entities(
            controller_entities,
            config_subentry_id=runtime.config.subentry_id,
        )

    def _changed(event: str, subentry_id: str, runtime) -> None:
        if event == "added" and runtime is not None:
            _add(runtime)
        elif event == "removed":
            for entity in entities.pop(subentry_id, ()):
                hass.async_create_task(entity.async_remove())

    for runtime in manager.controllers.values():
        _add(runtime)
    entry.async_on_unload(manager.add_controller_listener(_changed))

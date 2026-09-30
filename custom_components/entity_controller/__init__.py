"""Entity Controller integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .manager import EntityControllerManager


type EntityControllerConfigEntry = ConfigEntry[EntityControllerManager]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> bool:
    """Set up Entity Controller from a config entry."""

    manager = EntityControllerManager(hass, entry)
    await manager.async_setup()
    entry.runtime_data = manager
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> bool:
    """Unload an Entity Controller config entry."""

    await entry.runtime_data.async_unload()
    return True

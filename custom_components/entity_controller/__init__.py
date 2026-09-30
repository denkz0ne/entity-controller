"""Entity Controller integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .manager import EntityControllerManager

PLATFORMS: list[str] = ["sensor", "binary_sensor", "switch", "button"]


type EntityControllerConfigEntry = ConfigEntry[EntityControllerManager]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> bool:
    """Set up Entity Controller from a config entry."""

    manager = EntityControllerManager(hass, entry)
    await manager.async_setup()
    entry.runtime_data = manager
    if hasattr(hass, "config_entries") and hasattr(
        hass.config_entries, "async_forward_entry_setups"
    ):
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> bool:
    """Unload an Entity Controller config entry."""

    unload_ok = True
    if hasattr(hass, "config_entries") and hasattr(
        hass.config_entries, "async_unload_platforms"
    ):
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.async_unload()
    return unload_ok

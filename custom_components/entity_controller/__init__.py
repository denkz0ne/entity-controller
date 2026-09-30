"""Entity Controller integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .manager import EntityControllerManager
from .services import async_setup_services, async_unload_services

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
    if hasattr(hass, "data") and hasattr(hass, "services"):
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
        async_setup_services(hass)
    if hasattr(entry, "add_update_listener"):
        remove_listener = entry.add_update_listener(_async_entry_updated)
        if hasattr(entry, "async_on_unload"):
            entry.async_on_unload(remove_listener)
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
    if hasattr(hass, "data") and hasattr(hass, "services"):
        hass.data.setdefault(DOMAIN, {}).pop(entry.entry_id, None)
        async_unload_services(hass)
    return unload_ok


async def _async_entry_updated(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> None:
    """Apply config-subentry changes without reloading sibling controllers."""

    await entry.runtime_data.async_sync_subentries()

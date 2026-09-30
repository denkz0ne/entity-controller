import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.entity_controller import async_setup_entry, async_unload_entry
from custom_components.entity_controller.manager import EntityControllerManager


@pytest.mark.asyncio
async def test_setup_entry_stores_typed_manager() -> None:
    hass = HomeAssistant()
    entry = ConfigEntry()

    assert await async_setup_entry(hass, entry) is True
    assert isinstance(entry.runtime_data, EntityControllerManager)
    assert entry.runtime_data.is_loaded is True


@pytest.mark.asyncio
async def test_unload_entry_stops_manager() -> None:
    hass = HomeAssistant()
    entry = ConfigEntry()

    assert await async_setup_entry(hass, entry) is True
    manager = entry.runtime_data

    assert await async_unload_entry(hass, entry) is True
    assert manager.is_loaded is False

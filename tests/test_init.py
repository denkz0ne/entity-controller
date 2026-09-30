import pytest

from custom_components.entity_controller import async_setup_entry, async_unload_entry
from custom_components.entity_controller.manager import EntityControllerManager


class FakeConfigEntry:
    runtime_data: EntityControllerManager | None = None


@pytest.mark.asyncio
async def test_setup_entry_stores_typed_manager() -> None:
    hass = object()
    entry = FakeConfigEntry()

    assert await async_setup_entry(hass, entry) is True
    assert isinstance(entry.runtime_data, EntityControllerManager)
    assert entry.runtime_data.is_loaded is True


@pytest.mark.asyncio
async def test_unload_entry_stops_manager() -> None:
    hass = object()
    entry = FakeConfigEntry()

    assert await async_setup_entry(hass, entry) is True
    manager = entry.runtime_data

    assert await async_unload_entry(hass, entry) is True
    assert manager.is_loaded is False

import pytest

from custom_components.entity_controller import async_setup_entry, async_unload_entry
from custom_components.entity_controller.manager import EntityControllerManager


class FakeConfigEntry:
    runtime_data: EntityControllerManager | None = None
    entry_id = "entry-id"
    subentries = {}

    def add_update_listener(self, listener):
        self.update_listener = listener

        def remove():
            self.update_listener = None

        return remove

    def async_on_unload(self, remove):
        self.remove_listener = remove


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


@pytest.mark.asyncio
async def test_setup_entry_loads_existing_controller_subentries() -> None:
    entry = FakeConfigEntry()
    entry.subentries = {
        "controller-a": type(
            "Subentry",
            (),
            {
                "subentry_id": "controller-a",
                "subentry_type": "controller",
                "data": {
                    "name": "Hall",
                    "trigger_entities": ("binary_sensor.hall",),
                    "control_entities": ("light.hall",),
                },
            },
        )()
    }
    hass = type(
        "Hass",
        (),
        {
            "states": type("States", (), {"get": lambda self, entity_id: None})(),
            "track_state": lambda self, entity_id, callback: lambda: None,
        },
    )()

    assert await async_setup_entry(hass, entry) is True
    assert "controller-a" in entry.runtime_data.controllers

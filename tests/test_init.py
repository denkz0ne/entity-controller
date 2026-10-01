import asyncio
import logging
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState

import custom_components.entity_controller as integration
from custom_components.entity_controller import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.entity_controller.const import DOMAIN
from custom_components.entity_controller.manager import EntityControllerManager


class FakeConfigEntry:
    runtime_data: EntityControllerManager | None = None
    entry_id = "entry-id"
    subentries = {}
    data = {}

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


@pytest.mark.asyncio
async def test_setup_entry_loads_flat_controller_config_entry() -> None:
    entry = FakeConfigEntry()
    entry.data = {
        "_ec_controller_id": "controller-a",
        "_ec_entity_unique_id_prefix": "root-controller-a",
        "name": "Hall",
        "trigger_entities": ("binary_sensor.hall",),
        "control_entities": ("light.hall",),
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
    runtime = entry.runtime_data.controllers["controller-a"]
    assert runtime.config.name == "Hall"
    assert runtime.config.entity_unique_id_prefix == "root-controller-a"


@pytest.mark.asyncio
async def test_prerelease_entry_migration_preserves_controller_registry_identity() -> None:
    old_subentry = type(
        "Subentry",
        (),
        {
            "subentry_id": "controller-a",
            "subentry_type": "controller",
            "title": "Hall",
            "data": {"name": "Hall", "trigger_entities": ("binary_sensor.hall",)},
        },
    )()
    second_subentry = type(
        "Subentry",
        (),
        {
            "subentry_id": "controller-b",
            "subentry_type": "controller",
            "title": "Kitchen",
            "data": {"name": "Kitchen", "trigger_entities": ()},
        },
    )()
    old_entry = type(
        "Entry",
        (),
        {
            "entry_id": "old-root",
            "version": 10,
            "source": "user",
            "subentries": {
                "controller-a": old_subentry,
                "controller-b": second_subentry,
            },
            "data": {"name": "Entity Controller"},
            "title": "Entity Controller",
        },
    )()

    class ConfigEntries:
        def __init__(self):
            self.entries = {}
            self.removed_subentries = []

        def async_entry_for_domain_unique_id(self, domain, unique_id):
            return self.entries.get(unique_id)

        async def async_add(self, entry):
            object.__setattr__(entry, "state", ConfigEntryState.LOADED)
            self.entries[entry.unique_id] = entry

        async def async_reload(self, entry_id):
            return True

        def async_remove_subentry(self, entry, subentry_id):
            self.removed_subentries.append(subentry_id)
            entry.subentries.pop(subentry_id)

        def async_update_entry(self, entry, *, data, title, version, minor_version):
            entry.data = data
            entry.title = title
            entry.version = version
            entry.minor_version = minor_version

    entries = ConfigEntries()
    hass = type("Hass", (), {"config_entries": entries})()

    assert await async_migrate_entry(hass, old_entry) is True
    assert entries.removed_subentries == ["controller-a", "controller-b"]
    assert len(entries.entries) == 1
    migrated = next(iter(entries.entries.values()))
    assert migrated.data["_ec_controller_id"] == "controller-b"
    assert migrated.data["_ec_entity_unique_id_prefix"] == (
        "old-root_controller-b"
    )
    assert migrated.data["name"] == "Kitchen"
    assert old_entry.data["_ec_controller_id"] == "controller-a"
    assert old_entry.data["_ec_entity_unique_id_prefix"] == "old-root_controller-a"
    assert old_entry.title == "Hall"
    assert old_entry.version == 11


@pytest.mark.asyncio
async def test_prerelease_migration_keeps_legacy_root_when_target_fails_to_load() -> None:
    subentry = type(
        "Subentry",
        (),
        {
            "subentry_id": "controller-a",
            "subentry_type": "controller",
            "title": "Hall",
            "data": {"name": "Hall"},
        },
    )()
    second_subentry = type(
        "Subentry",
        (),
        {
            "subentry_id": "controller-b",
            "subentry_type": "controller",
            "title": "Kitchen",
            "data": {"name": "Kitchen"},
        },
    )()
    old_data = {"name": "Entity Controller"}
    old_entry = type(
        "Entry",
        (),
        {
            "entry_id": "old-root",
            "version": 10,
            "source": "user",
            "subentries": {
                "controller-a": subentry,
                "controller-b": second_subentry,
            },
            "data": old_data,
            "title": "Entity Controller",
        },
    )()

    class ConfigEntries:
        def __init__(self):
            self.removed_subentries = []
            self.updated = False

        def async_entry_for_domain_unique_id(self, domain, unique_id):
            return None

        async def async_add(self, entry):
            pass

        async def async_reload(self, entry_id):
            return True

        def async_remove_subentry(self, entry, subentry_id):
            self.removed_subentries.append(subentry_id)

        def async_update_entry(self, entry, **kwargs):
            self.updated = True

    entries = ConfigEntries()
    hass = type("Hass", (), {"config_entries": entries})()

    assert await async_migrate_entry(hass, old_entry) is False
    assert old_entry.data is old_data
    assert old_entry.subentries == {
        "controller-a": subentry,
        "controller-b": second_subentry,
    }
    assert entries.removed_subentries == []
    assert entries.updated is False


class _FakeImportFlow:
    def __init__(self, config_entries, failed_controller_ids=()):
        self.config_entries = config_entries
        self.failed_controller_ids = set(failed_controller_ids)
        self.calls = []

    async def async_init(self, domain, *, context, data):
        self.calls.append((domain, dict(context), dict(data)))
        controller_id = data["controller_id"]
        if controller_id in self.failed_controller_ids:
            raise RuntimeError("simulated flow failure")
        self.config_entries.entries.append(
            SimpleNamespace(
                unique_id=f"legacy-yaml:{controller_id}",
                data={
                    **{key: value for key, value in data.items() if key != "controller_id"},
                    "_ec_controller_id": controller_id,
                },
            )
        )
        return {"type": "create_entry"}


class _FakeImportConfigEntries:
    def __init__(self, failed_controller_ids=()):
        self.entries = []
        self.flow = _FakeImportFlow(self, failed_controller_ids)

    def async_entries(self, domain):
        assert domain == DOMAIN
        return self.entries


def _import_hass(failed_controller_ids=()):
    config_entries = _FakeImportConfigEntries(failed_controller_ids)
    tasks = []
    hass = SimpleNamespace(
        config_entries=config_entries,
        async_create_task=lambda task: tasks.append(asyncio.create_task(task)),
    )
    return hass, config_entries, tasks


async def _await_import_tasks(tasks):
    if tasks:
        await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_yaml_import_skips_absent_and_empty_configuration() -> None:
    hass, config_entries, tasks = _import_hass()

    assert await integration.async_setup(hass, {}) is True
    assert await integration.async_setup(hass, {DOMAIN: {}}) is True
    await _await_import_tasks(tasks)
    assert config_entries.flow.calls == []


@pytest.mark.asyncio
async def test_yaml_import_creates_one_entry_per_controller_and_is_idempotent() -> None:
    hass, config_entries, tasks = _import_hass()
    legacy_config = {
        DOMAIN: {
            "hall": {"sensor": "binary_sensor.hall_motion", "entity": "light.hall"},
            "kitchen": {"sensor": "binary_sensor.kitchen_motion", "entity": "light.kitchen"},
        }
    }

    assert await integration.async_setup(hass, legacy_config) is True
    await _await_import_tasks(tasks)
    assert [call[2]["controller_id"] for call in config_entries.flow.calls] == [
        "hall",
        "kitchen",
    ]
    assert all(call[0] == DOMAIN and call[1] == {"source": "import"} for call in config_entries.flow.calls)
    assert config_entries.flow.calls[0][2] == {
        "controller_id": "hall",
        "name": "Hall",
        "trigger_entities": ("binary_sensor.hall_motion",),
        "control_entities": ("light.hall",),
        "state_entities": (),
        "override_entities": (),
        "interlock_entities": (),
        "sensor_type": "event",
        "delay_seconds": 180.0,
        "sensor_resets_timer": False,
        "block_timeout_seconds": None,
        "blocking_enabled": True,
        "stay_mode_default": False,
        "backoff_enabled": False,
        "backoff_factor": 1.1,
        "backoff_max_seconds": 300.0,
        "service_data_on": {},
        "service_data_off": {},
        "state_attributes_ignore": (),
        "trigger_on_states": ("on", "playing", "home", "True"),
        "trigger_off_states": ("off", "idle", "paused", "away", "False"),
        "state_on_states": ("on", "playing", "home", "True"),
        "state_off_states": ("off", "idle", "paused", "away", "False"),
        "override_on_states": ("on", "playing", "home", "True"),
        "override_off_states": ("off", "idle", "paused", "away", "False"),
    }

    calls_before_retry = len(config_entries.flow.calls)
    assert await integration.async_setup(hass, legacy_config) is True
    await _await_import_tasks(tasks[1:])
    assert len(config_entries.flow.calls) == calls_before_retry


@pytest.mark.asyncio
async def test_yaml_import_rejects_unexpected_top_level_shape(caplog) -> None:
    hass, config_entries, tasks = _import_hass()

    with caplog.at_level(logging.ERROR):
        assert await integration.async_setup(hass, {DOMAIN: ["not", "a", "mapping"]}) is True
    await _await_import_tasks(tasks)

    assert config_entries.flow.calls == []
    assert "legacy yaml configuration must be a mapping" in caplog.text.lower()


@pytest.mark.asyncio
async def test_yaml_import_skips_bad_controller_and_continues_after_flow_error(caplog) -> None:
    hass, config_entries, tasks = _import_hass(failed_controller_ids={"flow_fails"})
    legacy_config = {
        DOMAIN: {
            "malformed": "not a controller mapping",
            "flow_fails": {"entity": "light.fails"},
            "valid": {"entity": "light.valid"},
        }
    }

    with caplog.at_level(logging.WARNING):
        assert await integration.async_setup(hass, legacy_config) is True
        await _await_import_tasks(tasks)

    assert [call[2]["controller_id"] for call in config_entries.flow.calls] == [
        "flow_fails",
        "valid",
    ]
    assert any("malformed" in record.message for record in caplog.records)
    assert any("flow_fails" in record.message for record in caplog.records)

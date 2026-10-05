from datetime import UTC, datetime
from types import SimpleNamespace

from homeassistant.helpers import entity_registry

from custom_components.entity_controller import panel
from custom_components.entity_controller.panel import serialize_controllers


class FakeRegistry:
    def __init__(self, entities):
        self.entities = entities

    def async_get_entity_id(self, domain, platform, unique_id):
        return self.entities.get((domain, platform, unique_id))


def test_panel_payload_is_dynamic_and_resolves_registered_entities(monkeypatch):
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            subentry_id="hall-id",
            entity_unique_id_prefix="entry-hall-id",
            name="Hall",
            icon="mdi:door",
            trigger_entities=("binary_sensor.hall_motion",),
            control_entities=("light.hall", "switch.fan"),
            state_entities=("binary_sensor.window",),
            override_entities=("input_boolean.manual",),
            interlock_entities=("binary_sensor.lock",),
        ),
        state=SimpleNamespace(value="active_timer"),
        enabled=True,
        stay_mode=False,
        last_transition_at="2026-10-01T10:00:00+00:00",
        last_transition_cause=SimpleNamespace(value="trigger_on"),
        last_triggered_at="2026-10-01T10:00:00+00:00",
        expires_at=datetime(2026, 10, 1, 10, 3, tzinfo=UTC),
        blocked_by=(),
        block_reason=None,
        active_triggers=("binary_sensor.hall_motion",),
        active_state_entities=(),
        active_overrides=(),
        active_interlocks=(),
    )
    manager = SimpleNamespace(
        controllers={"hall-id": runtime},
        entry=SimpleNamespace(
            data={
                "name": "Hall",
                "icon": "mdi:door",
                "trigger_entities": ["binary_sensor.hall_motion"],
                "control_entities": ["light.hall", "switch.fan"],
                "delay_seconds": 180,
            },
            subentries={},
        ),
    )
    hass = SimpleNamespace(
        data={"entity_controller": {"entry-1": manager}},
    )
    monkeypatch.setattr(
        entity_registry,
        "async_get",
        lambda _: FakeRegistry(
            {
                ("sensor", "entity_controller", "entry-hall-id_state"): "sensor.custom_hall_state",
                ("switch", "entity_controller", "entry-hall-id_enabled"): "switch.custom_hall_enabled",
            }
        ),
    )

    result = serialize_controllers(hass)

    assert len(result) == 1
    controller = result[0]
    assert controller["id"] == "hall-id"
    assert controller["name"] == "Hall"
    assert controller["state"] == "active_timer"
    assert controller["state_entity_id"] == "sensor.custom_hall_state"
    assert controller["enabled_entity_id"] == "switch.custom_hall_enabled"
    assert controller["triggers"] == ["binary_sensor.hall_motion"]
    assert controller["inputs"] == [
        "binary_sensor.hall_motion",
        "binary_sensor.window",
        "input_boolean.manual",
        "binary_sensor.lock",
    ]
    assert controller["outputs"] == ["light.hall", "switch.fan"]
    assert controller["constraints"] == [
        "binary_sensor.window",
        "input_boolean.manual",
        "binary_sensor.lock",
    ]
    assert controller["enabled"] is True
    assert controller["last_transition_cause"] == "trigger_on"
    assert controller["form"]["basic"]["name"] == "Hall"
    assert controller["form"]["basic"]["trigger_entities"] == [
        "binary_sensor.hall_motion"
    ]
    assert controller["form"]["basic"]["delay_seconds"] == {
        "hours": 0,
        "minutes": 3,
        "seconds": 0,
    }


def test_panel_payload_handles_no_controller_entries_and_missing_entity_registry():
    hass = SimpleNamespace(data={"entity_controller": {}})

    assert serialize_controllers(hass) == []


def test_panel_lifecycle_registers_once_and_removes_sidebar(monkeypatch):
    registrations = []
    removals = []
    websocket_registrations = []

    class Http:
        def register_static_path(self, url, path, cache_headers=False):
            registrations.append((url, path))

    hass = SimpleNamespace(data={}, http=Http())
    monkeypatch.setattr(
        panel.frontend,
        "async_register_built_in_panel",
        lambda *args, **kwargs: registrations.append((args, kwargs)),
    )
    monkeypatch.setattr(
        panel.frontend,
        "async_remove_panel",
        lambda *args, **kwargs: removals.append((args, kwargs)),
    )
    monkeypatch.setattr(
        panel.websocket_api,
        "async_register_command",
        lambda *args, **kwargs: websocket_registrations.append(args),
    )

    import asyncio

    async def setup_lifecycle():
        await asyncio.gather(
            panel.async_setup_panel(hass),
            panel.async_setup_panel(hass),
            panel.async_setup_panel(hass),
        )
        panel.async_unsetup_panel(hass)
        await panel.async_setup_panel(hass)

    asyncio.run(setup_lifecycle())

    assert len([item for item in registrations if item[0] == panel.PANEL_JS]) == 1
    assert len([item for item in registrations if isinstance(item[0], tuple)]) == 2
    assert len(websocket_registrations) == 2
    assert len(removals) == 1

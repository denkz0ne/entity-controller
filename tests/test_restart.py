"""Regressions for session ownership and restart observation comparisons."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import ControllerState
from tests.test_manager import FakeEntry, FakeHass, FakeState, subentry


class MemoryStore:
    def __init__(self):
        self.data = None

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        self.data = deepcopy(data)

    def async_delay_save(self, getter, delay):
        self.data = deepcopy(getter())


async def setup(values, store, **options):
    hass = FakeHass(values)
    entry = FakeEntry()
    entry.subentries = {"hall": subentry(
        "hall", trigger_entities=("binary_sensor.motion",),
        control_entities=("light.hall",), **options,
    )}
    manager = EntityControllerManager(hass, entry, runtime_store=store)
    await manager.async_setup()
    return hass, manager, manager.controllers["hall"]


@pytest.mark.asyncio
async def test_active_session_resumes_original_deadline_with_motion_off():
    store = MemoryStore()
    hass, manager, runtime = await setup(
        {"binary_sensor.motion": "off", "light.hall": "off"}, store,
    )
    await hass.fire_state_change("binary_sensor.motion", "on")
    hass.states._values["light.hall"] = "on"
    await hass.fire_state_change("binary_sensor.motion", "off", old_state="on")
    deadline = runtime.expires_at
    await manager.async_unload()
    after, restored_manager, restored = await setup(
        {"binary_sensor.motion": "off", "light.hall": "on"}, store,
    )
    assert restored.state is ControllerState.ACTIVE_TIMER
    assert restored.expires_at == deadline
    assert restored.restart_restore_status == "matched"
    assert after.service_calls == []
    await restored.async_handle_timer_expired()
    assert restored.state is ControllerState.IDLE
    assert any(call[1] == "turn_off" for call in after.service_calls)
    await restored_manager.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", (False, True))
async def test_missing_or_changed_checkpoint_never_creates_output_on_block(saved):
    store = MemoryStore()
    if saved:
        _, before, _ = await setup(
            {"binary_sensor.motion": "off", "light.hall": "off"}, store,
        )
        await before.async_unload()
    hass, manager, runtime = await setup(
        {"binary_sensor.motion": "off", "light.hall": "on"}, store,
    )
    assert runtime.state is ControllerState.IDLE
    assert runtime.block_reason is None
    assert runtime.manual_release_ready is True
    assert hass.service_calls == []
    await hass.fire_state_change("binary_sensor.motion", "on")
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert any(call[1] == "turn_on" for call in hass.service_calls)
    await manager.async_unload()


@pytest.mark.asyncio
async def test_real_manual_takeover_is_restored_only_when_observations_match():
    store = MemoryStore()
    hass, manager, runtime = await setup(
        {"binary_sensor.motion": "off", "light.hall": "off"}, store,
    )
    await hass.fire_state_change("light.hall", "on")
    assert runtime.manual_takeover_pending
    await manager.async_unload()
    _, restored_manager, restored = await setup(
        {"binary_sensor.motion": "off", "light.hall": "on"}, store,
    )
    assert restored.state is ControllerState.BLOCKED
    assert restored.manual_control_kind == "manual_on"
    assert restored.manual_takeover_pending
    await restored_manager.async_unload()
    _, changed_manager, changed = await setup(
        {"binary_sensor.motion": "off", "light.hall": "off"}, store,
    )
    assert changed.state is ControllerState.IDLE
    assert changed.manual_takeover_pending is False
    await changed_manager.async_unload()


@pytest.mark.asyncio
async def test_changed_brightness_does_not_restore_old_manual_block():
    store = MemoryStore()
    hass, manager, _ = await setup(
        {"binary_sensor.motion": "off", "light.hall": "off"}, store,
    )
    await hass.fire_state_change("light.hall", "on")
    get_original = hass.states.get
    hass.states.get = lambda entity_id: (
        FakeState("on", {"brightness": 100}) if entity_id == "light.hall"
        else get_original(entity_id)
    )
    await manager.async_unload()
    after = FakeHass({"binary_sensor.motion": "off", "light.hall": "on"})
    get_after = after.states.get
    after.states.get = lambda entity_id: (
        FakeState("on", {"brightness": 200}) if entity_id == "light.hall"
        else get_after(entity_id)
    )
    restored = EntityControllerManager(after, manager.entry, runtime_store=store)
    await restored.async_setup()
    assert restored.controllers["hall"].state is ControllerState.IDLE
    assert restored.controllers["hall"].restart_restore_status == "changed"
    await restored.async_unload()


@pytest.mark.asyncio
async def test_actual_interlock_still_has_priority_over_startup_fallback():
    _, manager, runtime = await setup(
        {"binary_sensor.motion": "off", "light.hall": "on", "binary_sensor.lock": "on"},
        MemoryStore(), interlock_entities=("binary_sensor.lock",),
    )
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.block_reason == "interlock"
    await manager.async_unload()


@pytest.mark.asyncio
async def test_expired_checkpoint_is_rescheduled_for_evaluation_not_blocked():
    store = MemoryStore()
    hass, manager, runtime = await setup(
        {"binary_sensor.motion": "off", "light.hall": "off"}, store,
    )
    await hass.fire_state_change("binary_sensor.motion", "on")
    hass.states._values["light.hall"] = "on"
    await hass.fire_state_change("binary_sensor.motion", "off", old_state="on")
    runtime.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await manager.async_unload()
    _, after, restored = await setup(
        {"binary_sensor.motion": "off", "light.hall": "on"}, store,
    )
    assert restored.state is ControllerState.ACTIVE_TIMER
    assert restored.expires_at >= datetime.now(UTC) - timedelta(seconds=1)
    await after.async_unload()


class StartupBus:
    def __init__(self):
        self.listeners = {}

    def async_listen_once(self, event_type, callback):
        listeners = self.listeners.setdefault(event_type, [])
        listeners.append(callback)

        def remove():
            if callback in listeners:
                listeners.remove(callback)

        return remove

    async def fire(self, event_type):
        for callback in tuple(self.listeners.get(event_type, [])):
            self.listeners[event_type].remove(callback)
            await callback(None)


@pytest.mark.asyncio
async def test_startup_availability_events_do_not_create_manual_takeover():
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

    hass = FakeHass({"binary_sensor.motion": "unknown", "light.hall": "unavailable"})
    hass.bus = StartupBus()
    hass.is_running = False
    store = MemoryStore()
    manager = EntityControllerManager(hass, FakeEntry(), runtime_store=store)
    await manager._restart.async_load()
    runtime = await manager.async_add_controller(subentry(
        "hall", trigger_entities=("binary_sensor.motion",), control_entities=("light.hall",),
    ))
    await hass.fire_state_change("light.hall", "on", old_state="unavailable")
    await hass.fire_state_change("binary_sensor.motion", "off", old_state="unknown")
    assert "hall" in manager._restart.pending
    assert store.data is None
    assert not runtime.manual_takeover_pending
    hass.is_running = True
    await hass.bus.fire(EVENT_HOMEASSISTANT_STARTED)
    assert "hall" not in manager._restart.pending
    assert runtime.state is ControllerState.IDLE
    assert runtime.manual_release_ready
    assert store.data["controllers"]["hall"]["entities"]["light.hall"]["state"] == "on"
    await manager.async_unload()


@pytest.mark.asyncio
async def test_unavailable_sensor_cannot_leave_startup_pending_forever(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "custom_components.entity_controller.manager.schedule_at_home_assistant",
        lambda hass, when, callback: lambda: None,
    )
    monkeypatch.setattr(
        "homeassistant.helpers.event.async_call_later",
        lambda hass, delay, callback: scheduled.append((delay, callback)) or (lambda: None),
    )
    hass = FakeHass({"binary_sensor.motion": "unavailable", "light.hall": "on"})
    hass.bus = StartupBus()
    hass.is_running = True
    manager = EntityControllerManager(hass, FakeEntry(), runtime_store=MemoryStore())
    await manager._restart.async_load()
    runtime = await manager.async_add_controller(subentry(
        "hall", trigger_entities=("binary_sensor.motion",), control_entities=("light.hall",),
    ))
    assert "hall" in manager._restart.pending
    assert scheduled[0][0] == 30
    await scheduled[0][1](None)
    assert "hall" not in manager._restart.pending
    assert runtime.state is ControllerState.IDLE
    await hass.fire_state_change("binary_sensor.motion", "on", old_state="unavailable")
    assert runtime.state is ControllerState.ACTIVE_TIMER
    await manager.async_unload()

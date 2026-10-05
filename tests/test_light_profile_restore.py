from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import ControllerState, TransitionCause


class Lights:
    def __init__(self):
        self.values = {"light.room": SimpleNamespace(state="off", attributes={"brightness": 180, "color_temp_kelvin": 4000, "color_mode": "color_temp"})}
        self.calls = []
        self.states = self.services = self
        self.listeners = {}

    def get(self, entity_id):
        return self.values.get(entity_id)

    def track_state(self, entity_id, callback):
        self.listeners.setdefault(entity_id, []).append(callback)
        return lambda: self.listeners[entity_id].remove(callback)

    async def async_call(self, domain, service, data, **kwargs):
        self.calls.append((domain, service, data))
        for entity_id in data["entity_id"]:
            if entity_id not in self.values:
                continue
            state = self.values[entity_id]
            state.state = "on" if service == "turn_on" else "off"
            state.attributes.update({k: v for k, v in data.items() if k != "entity_id"})


async def setup_light(**data):
    hass = Lights()
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room"], "service_data_on": {"brightness": 40, "color_temp_kelvin": 2700}, **data}))
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    return hass, manager, runtime


@pytest.mark.asyncio
async def test_session_restores_attributes_before_turning_off():
    hass, _, runtime = await setup_light()
    await runtime.async_transition(ControllerState.IDLE, TransitionCause.TIMER_EXPIRED)
    assert len(hass.calls) == 3, "activation, restoration, then off must run"
    assert hass.calls[-2] == ("light", "turn_on", {"entity_id": ["light.room"], "brightness": 180, "color_temp_kelvin": 4000})
    assert hass.values["light.room"].state == "off"


@pytest.mark.asyncio
async def test_manual_takeover_preserves_changed_brightness_restores_unchanged_kelvin():
    hass, _, runtime = await setup_light()
    hass.values["light.room"].attributes["brightness"] = 90
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert hass.calls[-1][2] == {"entity_id": ["light.room"], "color_temp_kelvin": 4000}
    assert hass.values["light.room"].attributes["brightness"] == 90


@pytest.mark.asyncio
async def test_off_takeover_never_turns_light_on_and_restores_when_next_on():
    hass, manager, runtime = await setup_light()
    state = hass.values["light.room"]
    state.state = "off"
    before = len(hass.calls)
    await runtime.async_handle_state_entity_change("light.room", is_on=False, is_own_context=False)
    assert all(service != "turn_on" for _, service, _ in hass.calls[before:])
    state.state = "on"
    await manager._state_listener(runtime)({"entity_id": "light.room", "old_state": SimpleNamespace(state="off", attributes={}), "new_state": state})
    assert state.attributes["brightness"] == 180
    assert state.attributes["color_temp_kelvin"] == 4000


@pytest.mark.asyncio
async def test_light_parameters_are_not_sent_to_switch_or_fan():
    hass, _, _ = await setup_light(control_entities=["light.room", "switch.room", "fan.room"])
    for domain, _, data in hass.calls:
        if domain != "light":
            assert data == {"entity_id": [f"{domain}.room"]}


@pytest.mark.asyncio
async def test_disable_reconcile_discards_profile_without_service_calls():
    hass, _, runtime = await setup_light()
    await runtime.async_set_enabled(False)
    assert hass.values["light.room"].state == "on"
    assert hass.values["light.room"].attributes["brightness"] == 40
    assert len(hass.calls) == 1


@pytest.mark.asyncio
async def test_stay_mode_manual_takeover_restores_without_waiting_for_off():
    hass, _, runtime = await setup_light(stay_mode=True)
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert hass.values["light.room"].attributes["brightness"] == 180


@pytest.mark.asyncio
async def test_deferred_restore_preserves_manual_on_parameters():
    hass, manager, runtime = await setup_light()
    state = hass.values["light.room"]
    state.state = "off"
    await runtime.async_handle_state_entity_change("light.room", is_on=False, is_own_context=False)
    state.state = "on"
    state.attributes.update(brightness=80, color_temp_kelvin=5000)
    before = len(hass.calls)
    await manager._state_listener(runtime)({"entity_id": "light.room", "old_state": SimpleNamespace(state="off", attributes={}), "new_state": state})
    assert len(hass.calls) == before
    assert state.attributes["brightness"] == 80
    assert state.attributes["color_temp_kelvin"] == 5000


@pytest.mark.asyncio
async def test_unload_restores_on_light():
    hass, manager, _ = await setup_light()
    await manager.async_unload()
    assert hass.values["light.room"].attributes["brightness"] == 180


@pytest.mark.asyncio
async def test_restore_returns_original_rgb_color_mode():
    hass = Lights()
    hass.values["light.room"].attributes.update(color_mode="rgb", rgb_color=(10, 20, 30))
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room"], "service_data_on": {"color_temp_kelvin": 2700}}))
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    hass.values["light.room"].attributes["color_mode"] = "color_temp"
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert hass.calls[-1][2] == {"entity_id": ["light.room"], "rgb_color": (10, 20, 30)}


@pytest.mark.asyncio
async def test_active_stay_transition_retains_first_snapshot():
    hass, _, runtime = await setup_light()
    await runtime.async_set_stay_mode(True)
    assert len(hass.calls) == 1
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert hass.values["light.room"].attributes["brightness"] == 180


@pytest.mark.asyncio
async def test_night_boundary_restores_original_profile():
    hass, manager, runtime = await setup_light()
    runtime.night_active = True
    await manager._async_refresh_time_windows(runtime)
    assert hass.values["light.room"].attributes["brightness"] == 180
    assert not runtime.night_active


@pytest.mark.asyncio
async def test_missing_original_attributes_are_never_invented():
    hass = Lights()
    hass.values["light.room"].attributes = {}
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room"], "service_data_on": {"brightness": 40}}))
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    await runtime.async_set_enabled(False)
    assert len(hass.calls) == 1


@pytest.mark.asyncio
async def test_ignored_manual_field_is_not_reclaimed_if_user_returns_to_profile_value():
    hass, manager, runtime = await setup_light(state_attributes_ignore=["brightness"], blocking_enabled=False)
    state = hass.values["light.room"]
    state.attributes["brightness"] = 90
    await manager._state_listener(runtime)({"entity_id": "light.room", "old_state": SimpleNamespace(state="on", attributes={"brightness": 40, "color_temp_kelvin": 2700, "color_mode": "color_temp"}), "new_state": state})
    state.attributes["brightness"] = 40
    await runtime.async_transition(ControllerState.IDLE, TransitionCause.TIMER_EXPIRED)
    assert state.attributes["brightness"] == 40
    assert state.attributes["color_temp_kelvin"] == 4000


@pytest.mark.asyncio
async def test_presence_never_activates_idle_controller():
    hass = Lights()
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "presence_entities": ["binary_sensor.presence"]}))
    await manager._presence_listener(runtime)({"entity_id": "binary_sensor.presence", "new_state": SimpleNamespace(state="on")})
    assert runtime.presence_active
    assert runtime.state is ControllerState.IDLE
    assert hass.calls == []


@pytest.mark.asyncio
async def test_presence_holds_timer_and_final_clear_restarts_full_delay():
    _, manager, runtime = await setup_light(presence_entities=["binary_sensor.one", "binary_sensor.two"], delay_seconds=45)
    listener = manager._presence_listener(runtime)
    for entity in ("binary_sensor.one", "binary_sensor.two"):
        await listener({"entity_id": entity, "new_state": SimpleNamespace(state="on")})
    await runtime.async_handle_timer_expired()
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.timer_expired_pending_presence
    await listener({"entity_id": "binary_sensor.one", "new_state": SimpleNamespace(state="off")})
    assert runtime.presence_active
    assert runtime.expires_at is None
    await listener({"entity_id": "binary_sensor.two", "new_state": SimpleNamespace(state="off")})
    assert not runtime.presence_active
    assert not runtime.timer_expired_pending_presence
    assert runtime.expires_at is not None
    assert runtime.effective_delay_seconds == 45


@pytest.mark.asyncio
async def test_unknown_presence_does_not_clear_hold():
    _, manager, runtime = await setup_light(presence_entities=["binary_sensor.one"])
    listener = manager._presence_listener(runtime)
    await listener({"entity_id": "binary_sensor.one", "new_state": SimpleNamespace(state="on")})
    await listener({"entity_id": "binary_sensor.one", "new_state": SimpleNamespace(state="unavailable")})
    assert runtime.presence_active
    assert runtime.active_presence_entities == ("binary_sensor.one",)


@pytest.mark.asyncio
async def test_presence_cannot_prevent_disable():
    _, _, runtime = await setup_light()
    await runtime.async_handle_presence_change("binary_sensor.presence", is_active=True)
    await runtime.async_set_enabled(False)
    assert runtime.state is ControllerState.DISABLED


@pytest.mark.asyncio
async def test_manual_takeover_blocks_until_triggers_and_presence_clear():
    hass, manager, runtime = await setup_light(presence_entities=["binary_sensor.presence"])
    await manager._presence_listener(runtime)({"entity_id": "binary_sensor.presence", "new_state": SimpleNamespace(state="on")})
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False, manual_control_kind="manual_attribute_change")
    assert runtime.block_reason == "manual_attribute_change"
    assert runtime.manual_takeover_pending
    assert hass.values["light.room"].state == "on"
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.BLOCKED
    await runtime.async_handle_sensor_off("binary_sensor.motion")
    assert runtime.manual_takeover_pending
    await manager._presence_listener(runtime)({"entity_id": "binary_sensor.presence", "new_state": SimpleNamespace(state="off")})
    assert runtime.state is ControllerState.IDLE
    assert not runtime.manual_takeover_pending
    assert hass.values["light.room"].state == "on"
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.ACTIVE_TIMER


@pytest.mark.asyncio
async def test_manual_off_does_not_rearm_while_occupied():
    hass, _, runtime = await setup_light()
    hass.values["light.room"].state = "off"
    await runtime.async_handle_state_entity_change("light.room", is_on=False, is_own_context=False)
    assert runtime.manual_control_kind == "manual_off"
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.IDLE
    assert hass.values["light.room"].state == "off"
    await runtime.async_handle_sensor_off("binary_sensor.motion")
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.ACTIVE_TIMER


@pytest.mark.asyncio
async def test_explicit_restore_returns_original_on_state_and_attributes():
    hass = Lights()
    hass.values["light.room"].state = "on"
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "blocking_enabled": False, "control_entities": ["light.room"], "service_data_on": {"brightness": 40}, "transition_behaviors": {"on_exit_active": "restore", "on_enter_idle": "ignore"}}))
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    await runtime.async_transition(ControllerState.IDLE, TransitionCause.TIMER_EXPIRED)
    assert hass.values["light.room"].state == "on"
    assert hass.values["light.room"].attributes["brightness"] == 180


@pytest.mark.asyncio
async def test_manual_takeover_skips_selected_activity_exit_off():
    hass, _, runtime = await setup_light(transition_behaviors={"on_exit_active": "off", "on_enter_idle": "ignore"})
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert hass.values["light.room"].state == "on"
    assert runtime.state is ControllerState.BLOCKED


@pytest.mark.asyncio
async def test_custom_enter_replaces_basic_turn_on_and_keeps_own_context():
    import sys
    from unittest.mock import patch
    captured = []
    async def sequence_executor(hass, sequence, **kwargs):
        captured.append(kwargs["context"])
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        hass, manager, runtime = await setup_light(transition_behaviors={"on_enter_active": "custom"}, lifecycle_actions={"on_enter_active": [{"action": "scene.turn_on", "target": {"entity_id": "scene.evening"}}]})
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert len(captured) == 1
    assert manager.contexts.is_own_context(captured[0])
    assert hass.calls == []


@pytest.mark.asyncio
async def test_manual_takeover_cancels_custom_sequence_before_later_steps():
    import asyncio
    import sys
    from unittest.mock import patch
    started = asyncio.Event()
    finish = asyncio.Event()
    later_steps = []
    async def sequence_executor(hass, sequence, **kwargs):
        started.set()
        await finish.wait()
        later_steps.append("ran")
    hass = Lights()
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room"], "transition_behaviors": {"on_enter_active": "custom"}, "lifecycle_actions": {"on_enter_active": [{"delay": 10}]}}))
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        activation = asyncio.create_task(runtime.async_handle_sensor_on("binary_sensor.motion"))
        await started.wait()
        hass.values["light.room"].state = "on"
        await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
        finish.set()
        await activation
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.expires_at is None
    assert later_steps == []


@pytest.mark.asyncio
async def test_failed_custom_hook_reports_error_without_fallback_action():
    import sys
    from unittest.mock import patch
    async def sequence_executor(hass, sequence, **kwargs):
        raise ValueError("bad action")
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        hass, manager, runtime = await setup_light(transition_behaviors={"on_enter_active": "custom"}, lifecycle_actions={"on_enter_active": [{"action": "scene.turn_on"}]})
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert "bad action" in manager.controller_errors["a"]
    assert hass.calls == []


@pytest.mark.asyncio
async def test_custom_activity_exit_does_not_run_on_manual_takeover():
    import sys
    from unittest.mock import patch
    ran = []
    async def sequence_executor(hass, sequence, **kwargs):
        ran.append("exit")
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        hass, _, runtime = await setup_light(transition_behaviors={"on_exit_active": "custom"}, lifecycle_actions={"on_exit_active": [{"action": "light.turn_off"}]})
        await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert hass.values["light.room"].state == "on"
    assert ran == []


@pytest.mark.asyncio
async def test_manual_on_protection_can_be_disabled_without_blocking():
    hass, _, runtime = await setup_light(protect_manual_on=False)
    hass.values["light.room"].attributes["brightness"] = 90
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False, manual_control_kind="manual_attribute_change")
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert not runtime.manual_takeover_pending
    assert hass.values["light.room"].attributes["brightness"] == 90


@pytest.mark.asyncio
async def test_manual_off_protection_can_be_disabled_for_legacy_rearm():
    hass, _, runtime = await setup_light(protect_manual_off=False)
    hass.values["light.room"].state = "off"
    await runtime.async_handle_state_entity_change("light.room", is_on=False, is_own_context=False)
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert not runtime.manual_takeover_pending


@pytest.mark.asyncio
async def test_default_override_takeover_preserves_on_output():
    hass, _, runtime = await setup_light()
    await runtime.async_handle_override_change("input_boolean.guest", is_active=True)
    assert runtime.state is ControllerState.OVERRIDDEN
    assert hass.values["light.room"].state == "on"


@pytest.mark.asyncio
async def test_manual_latch_survives_override_until_room_clears():
    _, _, runtime = await setup_light()
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    await runtime.async_handle_override_change("input_boolean.guest", is_active=True)
    await runtime.async_handle_override_change("input_boolean.guest", is_active=False)
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.manual_takeover_pending
    await runtime.async_handle_sensor_off("binary_sensor.motion")
    assert runtime.state is ControllerState.IDLE
    assert not runtime.manual_takeover_pending


@pytest.mark.asyncio
async def test_fan_percentage_is_routed_only_to_fan():
    hass, _, _ = await setup_light(control_entities=["light.room", "switch.room", "fan.room"], service_data_on={"brightness": 40, "percentage": 60})
    calls = {domain: data for domain, _, data in hass.calls}
    assert "percentage" not in calls["light"]
    assert "percentage" not in calls["switch"]
    assert calls["fan"] == {"entity_id": ["fan.room"], "percentage": 60}


@pytest.mark.asyncio
async def test_failed_domain_does_not_prevent_other_outputs_or_claim_light_ownership():
    hass = Lights()
    original_call = hass.async_call
    async def failing_light(domain, service, data, **kwargs):
        if domain == "light":
            raise ValueError("light unavailable")
        await original_call(domain, service, data, **kwargs)
    hass.async_call = failing_light
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room", "fan.room"], "service_data_on": {"brightness": 40, "percentage": 60}}))
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert hass.calls == [("fan", "turn_on", {"entity_id": ["fan.room"], "percentage": 60})]
    assert not manager._light_profiles["a"]
    assert "light unavailable" in manager.controller_errors["a"]
    assert runtime.last_action_result == "failed"


@pytest.mark.asyncio
async def test_unload_cancels_custom_enter_without_rearming_timer():
    import asyncio
    import sys
    from unittest.mock import patch
    started = asyncio.Event()
    finish = asyncio.Event()
    later_steps = []
    async def sequence_executor(hass, sequence, **kwargs):
        started.set()
        await finish.wait()
        later_steps.append("ran")
    hass = Lights()
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room"], "transition_behaviors": {"on_enter_active": "custom"}, "lifecycle_actions": {"on_enter_active": [{"delay": 10}]}}))
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        activation = asyncio.create_task(runtime.async_handle_sensor_on("binary_sensor.motion"))
        await started.wait()
        await manager.async_unload()
        finish.set()
        await activation
    assert runtime.expires_at is None
    assert later_steps == []
    assert manager.controllers == {}


@pytest.mark.asyncio
async def test_stored_custom_enter_does_not_override_selected_on():
    import sys
    from unittest.mock import patch
    ran = []
    async def sequence_executor(hass, sequence, **kwargs):
        ran.append("scene")
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        hass, _, runtime = await setup_light(transition_behaviors={"on_enter_active": "on"}, lifecycle_actions={"on_enter_active": [{"action": "scene.turn_on"}]})
    assert ran == []
    assert hass.calls[0][1] == "turn_on"
    assert runtime.snapshot_held


@pytest.mark.asyncio
async def test_stored_custom_exit_does_not_override_selected_restore():
    import sys
    from unittest.mock import patch
    ran = []
    async def sequence_executor(hass, sequence, **kwargs):
        ran.append("scene")
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        hass, _, runtime = await setup_light(transition_behaviors={"on_exit_active": "restore", "on_enter_idle": "ignore"}, lifecycle_actions={"on_exit_active": [{"action": "scene.turn_on"}]})
        await runtime.async_transition(ControllerState.IDLE, TransitionCause.TIMER_EXPIRED)
    assert ran == []
    assert hass.values["light.room"].state == "off"


@pytest.mark.asyncio
async def test_stored_custom_enter_does_not_capture_snapshot_when_selected_ignore():
    import sys
    from unittest.mock import patch
    ran = []
    async def sequence_executor(hass, sequence, **kwargs):
        ran.append("scene")
    with patch.dict(sys.modules, {"custom_components.entity_controller.lifecycle": SimpleNamespace(async_execute_sequence=sequence_executor)}):
        hass, _, runtime = await setup_light(transition_behaviors={"on_enter_active": "ignore"}, lifecycle_actions={"on_enter_active": [{"action": "scene.turn_on"}]})
    assert ran == []
    assert hass.calls == []
    assert not runtime.snapshot_held


@pytest.mark.asyncio
async def test_light_metadata_change_is_not_manual_takeover():
    hass, manager, runtime = await setup_light()
    state = hass.values["light.room"]
    previous = dict(state.attributes)
    state.attributes.update(friendly_name="New name", battery_level=80)
    await manager._state_listener(runtime)({"entity_id": "light.room", "old_state": SimpleNamespace(state="on", attributes=previous), "new_state": state})
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.manual_control_kind is None


@pytest.mark.asyncio
async def test_meaningful_light_brightness_change_is_manual_takeover():
    hass, manager, runtime = await setup_light()
    state = hass.values["light.room"]
    previous = dict(state.attributes)
    state.attributes["brightness"] = 90
    await manager._state_listener(runtime)({"entity_id": "light.room", "old_state": SimpleNamespace(state="on", attributes=previous), "new_state": state})
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.manual_control_kind == "manual_attribute_change"
    assert state.attributes["brightness"] == 90


@pytest.mark.asyncio
async def test_other_ec_manager_context_is_not_manual_takeover():
    hass, manager, runtime = await setup_light()
    other = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    hass.data = {"entity_controller": {"a": manager, "b": other}}
    context = other.contexts.new_action_context(None)
    state = hass.values["light.room"]
    previous = dict(state.attributes)
    state.attributes["brightness"] = 90
    await manager._state_listener(runtime)({"entity_id": "light.room", "context": context, "old_state": SimpleNamespace(state="on", attributes=previous), "new_state": state})
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.manual_control_kind is None


@pytest.mark.asyncio
async def test_idle_manual_on_preserves_light_and_waits_for_fresh_room_session():
    hass = Lights()
    manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
    runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["light.room"], "service_data_on": {"brightness": 40}}))
    hass.values["light.room"].state = "on"
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert runtime.manual_control_kind == "manual_on"
    assert runtime.manual_takeover_pending
    assert hass.calls == []
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert hass.calls == []
    await runtime.async_handle_sensor_off("binary_sensor.motion")
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert hass.values["light.room"].attributes["brightness"] == 40


@pytest.mark.asyncio
async def test_manual_protection_operates_independently_of_legacy_blocking():
    _, _, runtime = await setup_light(blocking_enabled=False)
    assert runtime.config.protect_manual_on
    assert runtime.config.protect_manual_off
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.manual_takeover_pending


@pytest.mark.asyncio
async def test_lifecycle_diagnostics_record_time_generation_and_strategy():
    _, _, runtime = await setup_light(transition_behaviors={"on_exit_active": "restore", "on_enter_idle": "ignore"})
    assert runtime.last_action_at is not None
    assert runtime.snapshot_generation == 1
    assert runtime.snapshot_held
    assert runtime.selected_exit_strategy == "restore"
    assert runtime.last_action_context_is_own
    await runtime.async_handle_state_entity_change("light.room", is_on=True, is_own_context=False)
    assert runtime.restore_skipped_manual
    assert not runtime.snapshot_held


@pytest.mark.asyncio
async def test_fan_metadata_is_ignored_and_speed_direction_changes_are_manual():
    for field, value in (("percentage", 75), ("speed", "high"), ("direction", "reverse")):
        hass = Lights()
        hass.values["fan.room"] = SimpleNamespace(state="off", attributes={"percentage": 30, "speed": "low", "direction": "forward"})
        manager = EntityControllerManager(hass, SimpleNamespace(data={}), now=lambda: datetime.now(UTC))
        runtime = await manager.async_add_controller(SimpleNamespace(subentry_id="a", data={"name": "A", "control_entities": ["fan.room"], "service_data_on": {"percentage": 40}}))
        await runtime.async_handle_sensor_on("binary_sensor.motion")
        state = hass.values["fan.room"]
        previous = dict(state.attributes)
        state.attributes["friendly_name"] = "New fan name"
        await manager._state_listener(runtime)({"entity_id": "fan.room", "old_state": SimpleNamespace(state="on", attributes=previous), "new_state": state})
        assert runtime.state is ControllerState.ACTIVE_TIMER
        previous = dict(state.attributes)
        state.attributes[field] = value
        await manager._state_listener(runtime)({"entity_id": "fan.room", "old_state": SimpleNamespace(state="on", attributes=previous), "new_state": state})
        assert runtime.state is ControllerState.BLOCKED
        assert runtime.manual_control_kind == "manual_attribute_change"


@pytest.mark.asyncio
async def test_default_manual_off_protection_holds_with_legacy_blocking_disabled():
    hass, _, runtime = await setup_light(blocking_enabled=False)
    hass.values["light.room"].state = "off"
    await runtime.async_handle_state_entity_change("light.room", is_on=False, is_own_context=False)
    before = len(hass.calls)
    await runtime.async_handle_sensor_on("binary_sensor.motion")
    assert runtime.state is ControllerState.IDLE
    assert runtime.manual_takeover_pending
    assert len(hass.calls) == before

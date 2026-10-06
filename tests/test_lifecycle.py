"""Native HA execution contracts for controller lifecycle action sequences."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

pytest.importorskip("homeassistant")

import voluptuous as vol
from homeassistant.core import Context, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers.script import DATA_SCRIPTS

from custom_components.entity_controller.lifecycle import (
    async_execute_sequence,
    normalize_lifecycle_actions,
)


@pytest.mark.asyncio
async def test_normalization_validates_without_persisting_compiled_templates(tmp_path):
    # HA 2026.9 validates dynamic templates in its active event-loop context.
    hass = HomeAssistant(str(tmp_path))
    assert hass.loop is asyncio.get_running_loop()
    raw = {"on_enter_active": [{"service": "test.record", "data": {"name": "{{ controller_id }}"}}]}
    original = deepcopy(raw)
    result = normalize_lifecycle_actions(raw)
    assert result == original
    assert isinstance(result["on_enter_active"][0]["data"]["name"], str)
    assert raw == original
    with pytest.raises(vol.Invalid):
        normalize_lifecycle_actions({
            "on_enter_active": [{"action": "test.record", "data": {"name": "{{"}}],
        })


@pytest.mark.parametrize("value", [
    {"unknown_hook": []},
    {"on_enter_active": "test.record"},
    {"on_enter_active": [{"service": "not_a_service"}]},
])
def test_invalid_lifecycle_configuration_is_rejected(value):
    with pytest.raises(vol.Invalid):
        normalize_lifecycle_actions(value)


@pytest.mark.asyncio
async def test_native_sequence_renders_variables_and_preserves_owned_context(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    context = Context()

    @callback
    def record(call: ServiceCall):
        hass.states.async_set("test.result", call.data["name"], context=call.context)

    hass.services.async_register("test", "record", record)
    raw = [{"service": "test.record", "data": {"name": "{{ controller_id }}"}}]
    original = deepcopy(raw)
    await async_execute_sequence(hass, raw, name="hall start", context=context,
                                 variables={"controller_id": "hall"})
    state = hass.states.get("test.result")
    assert state.state == "hall"
    assert state.context.id == context.id
    assert raw == original
    assert len(hass.data.get(DATA_SCRIPTS, [])) == 0


@pytest.mark.asyncio
async def test_native_scene_action_runs_and_scripts_do_not_accumulate(tmp_path):
    hass = HomeAssistant(str(tmp_path))

    @callback
    def activate_scene(call: ServiceCall):
        hass.states.async_set("test.scene", call.data["entity_id"])

    hass.services.async_register("scene", "turn_on", activate_scene)
    for _ in range(3):
        await async_execute_sequence(hass, [{"scene": "scene.relax"}],
                                     name="hall scene", context=Context())
        assert len(hass.data.get(DATA_SCRIPTS, [])) == 0
    scene = hass.states.get("test.scene")
    assert "scene.relax" in scene.state


@pytest.mark.asyncio
async def test_service_error_propagates_for_controller_diagnostics(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    with pytest.raises(ServiceNotFound):
        await async_execute_sequence(hass, [{"service": "missing.service"}],
                                     name="hall error", context=Context())
    assert len(hass.data.get(DATA_SCRIPTS, [])) == 0


@pytest.mark.asyncio
async def test_cancelled_lifecycle_sequence_cannot_execute_later_steps(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    started = asyncio.Event()

    @callback
    def record(call: ServiceCall):
        hass.states.async_set("test.result", call.data["phase"])
        started.set()

    hass.services.async_register("test", "record", record)
    task = asyncio.create_task(async_execute_sequence(hass, [
        {"service": "test.record", "data": {"phase": "before"}},
        {"delay": 60},
        {"service": "test.record", "data": {"phase": "after"}},
    ], name="hall delayed", context=Context()))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hass.states.get("test.result").state == "before"
    assert len(hass.data.get(DATA_SCRIPTS, [])) == 0

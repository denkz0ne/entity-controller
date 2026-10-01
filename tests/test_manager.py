from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.entity_controller.manager import EntityControllerManager
from custom_components.entity_controller.model import ControllerState


@dataclass(frozen=True)
class FakeSubentry:
    subentry_id: str
    data: dict[str, Any]


class FakeState:
    def __init__(self, state: str, attributes: dict[str, Any] | None = None) -> None:
        self.state = state
        self.attributes = attributes or {}
        self.context = None


class FakeStates:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = values or {}

    def get(self, entity_id: str) -> FakeState | None:
        if entity_id not in self._values:
            return None
        return FakeState(self._values[entity_id])


class FakeHass:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.states = FakeStates(values)
        self.listeners: dict[str, list[Any]] = {}
        self.service_calls: list[tuple[str, str, dict[str, Any], Any]] = []
        self.services = self

    def track_state(self, entity_id: str, callback: Any) -> Any:
        self.listeners.setdefault(entity_id, []).append(callback)

        def _remove() -> None:
            self.listeners[entity_id].remove(callback)

        return _remove

    async def fire_state_change(
        self,
        entity_id: str,
        new_state: str,
        *,
        old_state: str = "off",
        context: Any = None,
        old_attributes: dict[str, Any] | None = None,
        new_attributes: dict[str, Any] | None = None,
    ) -> None:
        self.states._values[entity_id] = new_state
        callbacks = list(self.listeners.get(entity_id, ()))
        event = {
            "entity_id": entity_id,
            "old_state": FakeState(old_state, old_attributes),
            "new_state": FakeState(new_state, new_attributes),
            "context": context,
        }
        for callback in callbacks:
            await callback(event)

    def listener_count(self) -> int:
        return sum(len(callbacks) for callbacks in self.listeners.values())

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        blocking: bool,
        context: Any,
    ) -> None:
        self.service_calls.append((domain, service, data, context))


class FakeEntry:
    entry_id = "entry-id"


def subentry(subentry_id: str = "controller-a", **data: Any) -> FakeSubentry:
    return FakeSubentry(
        subentry_id,
        {
            "name": "Controller A",
            "delay_seconds": 30,
            **data,
        },
    )


@pytest.mark.asyncio
async def test_add_controller_reconciles_control_entity_on_without_forcing_off() -> (
    None
):
    hass = FakeHass({"light.hall": "on"})
    manager = EntityControllerManager(hass, FakeEntry())

    runtime = await manager.async_add_controller(
        subentry(control_entities=("light.hall",), state_entities=("light.hall",))
    )

    assert runtime.state is ControllerState.BLOCKED
    assert runtime.last_reconcile_reason.value == "startup"


@pytest.mark.asyncio
async def test_reconcile_retains_active_sources_for_runtime_diagnostics() -> None:
    hass = FakeHass(
        {
            "input_boolean.block_a": "on",
            "input_boolean.block_b": "on",
            "input_boolean.guest": "on",
            "binary_sensor.motion": "on",
            "light.hall": "on",
        }
    )
    manager = EntityControllerManager(hass, FakeEntry())

    runtime = await manager.async_add_controller(
        subentry(
            interlock_entities=("input_boolean.block_a", "input_boolean.block_b"),
            override_entities=("input_boolean.guest",),
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
        )
    )

    assert runtime.active_interlocks == (
        "input_boolean.block_a",
        "input_boolean.block_b",
    )
    assert runtime.active_overrides == ("input_boolean.guest",)
    assert runtime.active_triggers == ("binary_sensor.motion",)
    assert runtime.active_state_entities == ("light.hall",)
    assert runtime.overridden_by == "input_boolean.guest"


@pytest.mark.asyncio
async def test_last_interlock_clear_reconciles_current_trigger_state() -> None:
    hass = FakeHass(
        {
            "input_boolean.block_a": "on",
            "input_boolean.block_b": "on",
            "binary_sensor.motion": "on",
        }
    )
    manager = EntityControllerManager(hass, FakeEntry())

    runtime = await manager.async_add_controller(
        subentry(
            interlock_entities=("input_boolean.block_a", "input_boolean.block_b"),
            trigger_entities=("binary_sensor.motion",),
            block_timeout_seconds=60,
        )
    )

    assert runtime.state is ControllerState.BLOCKED
    assert runtime.active_interlocks == (
        "input_boolean.block_a",
        "input_boolean.block_b",
    )
    assert runtime.block_expires_at is None

    await hass.fire_state_change("input_boolean.block_a", "off", old_state="on")
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.active_interlocks == ("input_boolean.block_b",)

    await hass.fire_state_change("input_boolean.block_b", "off", old_state="on")
    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.active_interlocks == ()


@pytest.mark.asyncio
async def test_manager_routes_multiple_trigger_entities_to_one_controller() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(trigger_entities=("binary_sensor.one", "binary_sensor.two"))
    )

    await hass.fire_state_change("binary_sensor.one", "on")
    await hass.fire_state_change("binary_sensor.two", "on")

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.last_triggered_by == "binary_sensor.two"
    assert runtime.trigger_generation == 2
    assert runtime.active_triggers == ("binary_sensor.one", "binary_sensor.two")


@pytest.mark.asyncio
async def test_one_trigger_turning_off_keeps_duration_controller_active() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.one", "binary_sensor.two"),
            sensor_type="duration",
        )
    )

    await hass.fire_state_change("binary_sensor.one", "on")
    await hass.fire_state_change("binary_sensor.two", "on")
    await hass.fire_state_change("binary_sensor.one", "off", old_state="on")

    assert runtime.sensor_active is True


@pytest.mark.asyncio
async def test_one_override_turning_off_keeps_other_override_active() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            override_entities=("input_boolean.one", "input_boolean.two"),
        )
    )

    await hass.fire_state_change("input_boolean.one", "on")
    await hass.fire_state_change("input_boolean.two", "on")
    await hass.fire_state_change("input_boolean.one", "off", old_state="on")

    assert runtime.override_active is True
    assert runtime.state is ControllerState.OVERRIDDEN
    assert runtime.active_overrides == ("input_boolean.two",)
    assert runtime.overridden_by == "input_boolean.two"


@pytest.mark.asyncio
async def test_external_override_helper_updates_controller_immediately() -> None:
    hass = FakeHass({"input_boolean.guest": "off"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(override_entities=("input_boolean.guest",))
    )

    await hass.fire_state_change("input_boolean.guest", "on")

    assert runtime.state is ControllerState.OVERRIDDEN
    assert runtime.overridden_by == "input_boolean.guest"
    assert runtime.active_overrides == ("input_boolean.guest",)


@pytest.mark.asyncio
async def test_remove_controller_cleans_up_all_registered_callbacks() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.one", "binary_sensor.two"),
            override_entities=("input_boolean.override",),
            interlock_entities=("input_boolean.block",),
        )
    )

    assert hass.listener_count() == 4

    await manager.async_remove_controller("controller-a")

    assert "controller-a" not in manager.controllers
    assert hass.listener_count() == 0


@pytest.mark.asyncio
async def test_controller_transition_calls_home_assistant_control_service() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall", "switch.fan"),
        )
    )

    await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert [
        (domain, service, data) for domain, service, data, _ in hass.service_calls
    ] == [
        ("light", "turn_on", {"entity_id": ["light.hall"]}),
        ("switch", "turn_on", {"entity_id": ["switch.fan"]}),
    ]


@pytest.mark.asyncio
async def test_night_profile_uses_its_delay_and_service_data() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(
        hass,
        FakeEntry(),
        now=lambda: datetime(2026, 10, 1, 1, 0, tzinfo=UTC),
    )
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
            delay_seconds=180,
            service_data_on={"brightness_pct": 80},
            night_mode={
                "start": {
                    "source": "fixed",
                    "time": "20:00:00",
                    "offset_seconds": 0,
                },
                "end": {
                    "source": "fixed",
                    "time": "06:00:00",
                    "offset_seconds": 0,
                },
                "delay_seconds": 30,
                "service_data_on": {"brightness_pct": 15},
                "service_data_off": {},
            },
        )
    )

    await runtime.async_handle_sensor_on("binary_sensor.motion")

    assert runtime.night_active is True
    assert runtime.effective_delay_seconds == 30
    assert hass.service_calls[-1][2] == {
        "entity_id": ["light.hall"],
        "brightness_pct": 15,
    }


@pytest.mark.asyncio
async def test_constraint_window_blocks_controller_outside_allowed_time() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(
        hass,
        FakeEntry(),
        now=lambda: datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )
    runtime = await manager.async_add_controller(
        subentry(
            constraint_window={
                "start": {
                    "source": "fixed",
                    "time": "20:00:00",
                    "offset_seconds": 0,
                },
                "end": {
                    "source": "fixed",
                    "time": "06:00:00",
                    "offset_seconds": 0,
                },
            }
        )
    )

    assert runtime.state is ControllerState.CONSTRAINED


@pytest.mark.asyncio
async def test_trigger_rechecks_constraint_and_profile_at_event_time() -> None:
    now = [datetime(2026, 10, 1, 12, 0, tzinfo=UTC)]
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry(), now=lambda: now[0])
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            constraint_window={
                "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
            },
            night_mode={
                "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
                "delay_seconds": 20,
            },
        )
    )
    assert runtime.state is ControllerState.CONSTRAINED

    now[0] = datetime(2026, 10, 1, 21, 0, tzinfo=UTC)
    await hass.fire_state_change("binary_sensor.motion", "on")

    assert runtime.state is ControllerState.ACTIVE_TIMER
    assert runtime.night_active is True
    assert runtime.effective_delay_seconds == 20


@pytest.mark.asyncio
async def test_time_window_refresh_updates_controller_without_entity_event() -> None:
    now = [datetime(2026, 10, 1, 12, 0, tzinfo=UTC)]
    manager = EntityControllerManager(FakeHass(), FakeEntry(), now=lambda: now[0])
    runtime = await manager.async_add_controller(
        subentry(
            constraint_window={
                "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
            },
            night_mode={
                "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
            },
        )
    )
    assert runtime.state is ControllerState.CONSTRAINED

    now[0] = datetime(2026, 10, 1, 21, 0, tzinfo=UTC)
    await manager.async_refresh_time_windows()

    assert runtime.state is ControllerState.IDLE
    assert runtime.night_active is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condition", "expected"),
    (
        ("override", ControllerState.OVERRIDDEN),
        ("interlock", ControllerState.BLOCKED),
        ("duration_trigger", ControllerState.ACTIVE_TIMER),
        ("none", ControllerState.IDLE),
    ),
)
async def test_constraint_exit_reconciles_current_conditions(
    condition: str,
    expected: ControllerState,
) -> None:
    now = [datetime(2026, 10, 1, 12, 0, tzinfo=UTC)]
    values = {
        "input_boolean.override": "on" if condition == "override" else "off",
        "input_boolean.interlock": "on" if condition == "interlock" else "off",
        "binary_sensor.motion": "on" if condition == "duration_trigger" else "off",
        "light.hall": "off",
    }
    hass = FakeHass(values)
    manager = EntityControllerManager(hass, FakeEntry(), now=lambda: now[0])
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
            override_entities=("input_boolean.override",),
            interlock_entities=("input_boolean.interlock",),
            sensor_type="duration",
            constraint_window={
                "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
                "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
            },
        )
    )
    assert runtime.state is ControllerState.CONSTRAINED

    now[0] = datetime(2026, 10, 1, 21, 0, tzinfo=UTC)
    await manager.async_refresh_time_windows()

    assert runtime.state is expected
    if condition == "duration_trigger":
        assert hass.service_calls[-1][1] == "turn_on"
        assert hass.service_calls[-1][2]["entity_id"] == ["light.hall"]


@pytest.mark.asyncio
async def test_custom_trigger_and_override_states_are_honored() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("media_player.room",),
            override_entities=("input_select.mode",),
            trigger_on_states=("playing",),
            trigger_off_states=("idle", "paused"),
            override_on_states=("blocked",),
            override_off_states=("normal",),
        )
    )

    await hass.fire_state_change("media_player.room", "playing", old_state="idle")
    assert runtime.state is ControllerState.ACTIVE_TIMER

    await hass.fire_state_change("input_select.mode", "blocked", old_state="normal")
    assert runtime.state is ControllerState.OVERRIDDEN


@pytest.mark.asyncio
async def test_unmapped_trigger_state_does_not_release_active_condition() -> None:
    hass = FakeHass({"media_player.room": "playing"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("media_player.room",),
            trigger_on_states=("playing",),
            trigger_off_states=("idle", "paused"),
        )
    )

    await hass.fire_state_change(
        "media_player.room", "buffering", old_state="playing"
    )

    assert runtime.sensor_active is True
    assert runtime.state is ControllerState.ACTIVE_TIMER

    await hass.fire_state_change(
        "media_player.room", "paused", old_state="buffering"
    )

    assert runtime.sensor_active is False


@pytest.mark.asyncio
async def test_trigger_off_recomputes_or_using_other_explicitly_on_triggers() -> None:
    hass = FakeHass(
        {"media_player.a": "playing", "media_player.b": "playing"}
    )
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("media_player.a", "media_player.b"),
            trigger_on_states=("playing",),
            trigger_off_states=("idle", "paused"),
        )
    )

    await hass.fire_state_change("media_player.a", "idle", old_state="playing")
    assert runtime.sensor_active is True
    assert runtime.active_triggers == ("media_player.b",)

    await hass.fire_state_change("media_player.b", "buffering", old_state="playing")
    assert runtime.sensor_active is True

    await hass.fire_state_change("media_player.a", "paused", old_state="idle")
    assert runtime.sensor_active is False


@pytest.mark.asyncio
async def test_unmapped_state_entity_does_not_clear_another_mapped_on_entity() -> None:
    hass = FakeHass({"light.a": "on", "light.b": "off"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            state_entities=("light.a", "light.b"),
            state_on_states=("on", "playing"),
            state_off_states=("off", "paused"),
        )
    )
    assert runtime.state_entities_on is True

    await hass.fire_state_change("light.a", "unknown", old_state="on")

    assert runtime.state_entities_on is True
    assert runtime.state is ControllerState.BLOCKED
    assert runtime.active_state_entities == ()

    await hass.fire_state_change("light.a", "paused", old_state="unknown")

    assert runtime.state_entities_on is False
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
async def test_explicit_off_recomputes_state_entity_or_semantics() -> None:
    hass = FakeHass({"light.a": "on", "light.b": "on"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            state_entities=("light.a", "light.b"),
            state_on_states=("on",),
            state_off_states=("off",),
        )
    )

    await hass.fire_state_change("light.a", "off", old_state="on")
    assert runtime.state_entities_on is True
    assert runtime.state is ControllerState.BLOCKED

    await hass.fire_state_change("light.b", "off", old_state="on")
    assert runtime.state_entities_on is False
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
async def test_unmapped_override_state_does_not_clear_active_override() -> None:
    hass = FakeHass({"input_select.mode": "blocked"})
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            override_entities=("input_select.mode",),
            override_on_states=("blocked",),
            override_off_states=("normal",),
        )
    )
    assert runtime.state is ControllerState.OVERRIDDEN

    await hass.fire_state_change(
        "input_select.mode", "transitioning", old_state="blocked"
    )

    assert runtime.override_active is True
    assert runtime.state is ControllerState.OVERRIDDEN
    assert runtime.active_overrides == ()

    await hass.fire_state_change(
        "input_select.mode", "normal", old_state="transitioning"
    )

    assert runtime.override_active is False
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
@pytest.mark.parametrize("neutral", ("unknown", "unavailable", "buffering"))
async def test_neutral_startup_states_are_not_active(neutral: str) -> None:
    hass = FakeHass(
        {
            "media_player.trigger": neutral,
            "media_player.controlled": neutral,
            "input_select.override": neutral,
        }
    )
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("media_player.trigger",),
            control_entities=("media_player.controlled",),
            override_entities=("input_select.override",),
            trigger_on_states=("playing",),
            trigger_off_states=("idle", "paused"),
            state_on_states=("playing",),
            state_off_states=("idle", "paused"),
            override_on_states=("blocked",),
            override_off_states=("normal",),
        )
    )

    assert runtime.sensor_active is False
    assert runtime.state_entities_on is False
    assert runtime.override_active is False
    assert runtime.state is ControllerState.IDLE


@pytest.mark.asyncio
async def test_ignored_attribute_only_change_does_not_block_controller() -> None:
    hass = FakeHass()
    manager = EntityControllerManager(hass, FakeEntry())
    runtime = await manager.async_add_controller(
        subentry(
            trigger_entities=("binary_sensor.motion",),
            control_entities=("light.hall",),
            state_attributes_ignore=("brightness",),
        )
    )
    await hass.fire_state_change("binary_sensor.motion", "on")
    assert runtime.state is ControllerState.ACTIVE_TIMER

    await hass.fire_state_change(
        "light.hall",
        "on",
        old_state="on",
        old_attributes={"brightness": 100},
        new_attributes={"brightness": 150},
    )

    assert runtime.state is ControllerState.ACTIVE_TIMER


@pytest.mark.asyncio
async def test_manager_syncs_added_updated_and_removed_subentries() -> None:
    hass = FakeHass()
    entry = FakeEntry()
    entry.subentries = {"controller-a": subentry()}
    manager = EntityControllerManager(hass, entry)

    await manager.async_setup()
    assert set(manager.controllers) == {"controller-a"}

    entry.subentries = {
        "controller-a": subentry(trigger_entities=("binary_sensor.changed",)),
        "controller-b": subentry("controller-b", control_entities=("light.b",)),
    }
    await manager.async_sync_subentries()
    assert set(manager.controllers) == {"controller-a", "controller-b"}
    assert manager.controllers["controller-a"].config.trigger_entities == (
        "binary_sensor.changed",
    )

    entry.subentries = {"controller-b": entry.subentries["controller-b"]}
    await manager.async_sync_subentries()
    assert set(manager.controllers) == {"controller-b"}

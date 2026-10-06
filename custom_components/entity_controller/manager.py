"""Controller runtime manager for Entity Controller v10."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from functools import partial
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from .const import DOMAIN
from .context import ContextTracker
from .controller import ControllerRuntime, ReconcileSnapshot
from .entry_migration import CONTROLLER_ID_KEY, ENTITY_UNIQUE_ID_PREFIX_KEY
from .model import (
    ControllerConfig,
    ControllerState,
    ReconcileReason,
    SensorType,
    TransitionBehavior,
    TransitionCause,
    normalize_transition_behaviors,
)
from .schedule import schedule_at_home_assistant, window_is_active_from_data

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_ENTITY_FIELDS = {
    "trigger_entities",
    "presence_entities",
    "control_entities",
    "state_entities",
    "override_entities",
    "interlock_entities",
}
_STATE_LIST_FIELDS = {
    "trigger_on_states",
    "presence_on_states",
    "presence_off_states",
    "trigger_off_states",
    "state_on_states",
    "state_off_states",
    "override_on_states",
    "override_off_states",
    "state_attributes_ignore",
}
# Light service fields cannot be forwarded to switch/fan turn services.
_LIGHT_ONLY_FIELDS = {
    "brightness", "brightness_pct", "brightness_step", "brightness_step_pct",
    "color_temp", "color_temp_kelvin", "kelvin", "hs_color", "rgb_color",
    "rgbw_color", "rgbww_color", "xy_color", "color_name", "white",
    "flash", "effect", "transition",
}
_OFF_STATES = {"off", "unavailable", "unknown", ""}


class EntityControllerManager:
    """Own controller runtimes for one Entity Controller config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry[Any],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.controllers: dict[str, ControllerRuntime] = {}
        self.controller_errors: dict[str, str] = {}
        self._remove_callbacks: dict[str, list[Callable[[], None]]] = {}
        self._subentry_fingerprints: dict[str, tuple[tuple[str, Any], ...]] = {}
        self._controller_listeners: set[
            Callable[[str, str, ControllerRuntime | None], None]
        ] = set()
        self.contexts = ContextTracker()
        # original/last owned values, per controller and light; pending off lights
        # remain observed until ON. These are deliberately not persisted.
        self._light_profiles: dict[str, dict[str, dict[str, Any]]] = {}
        self._pending_light_restore: set[tuple[str, str]] = set()
        self._lifecycle_tasks: dict[str, asyncio.Task[Any]] = {}
        self._original_output_states: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {}
        self._output_session_open: set[str] = set()
        self._output_session_started: dict[str, datetime | None] = {}
        self._manual_output_sessions: set[str] = set()
        self._remove_time_listener: Callable[[], None] | None = None
        if now is None:
            from homeassistant.util import dt as dt_util

            now = dt_util.now
        self._now = now
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return whether the manager lifecycle is active."""

        return self._loaded

    async def async_setup(self) -> None:
        """Initialize manager-owned runtime resources."""

        self._loaded = True
        await self.async_sync_subentries()
        if hasattr(self.hass, "bus"):
            from homeassistant.helpers.event import async_track_time_change

            async def _refresh(_: datetime) -> None:
                await self.async_refresh_time_windows()

            self._remove_time_listener = async_track_time_change(
                self.hass,
                _refresh,
                second=0,
            )

    async def async_unload(self) -> None:
        """Release manager-owned runtime resources."""

        for subentry_id in tuple(self.controllers):
            await self.async_remove_controller(subentry_id)
        if self._remove_time_listener is not None:
            self._remove_time_listener()
            self._remove_time_listener = None
        self._loaded = False

    async def async_add_controller(self, subentry: Any) -> ControllerRuntime:
        """Create, start and reconcile a controller runtime for a subentry."""

        config = self._config_from_subentry(subentry)
        runtime = ControllerRuntime(
            config,
            behavior_executor=partial(self._async_execute_behavior, config.subentry_id),
            schedule_at=(
                partial(schedule_at_home_assistant, self.hass)
                if hasattr(self.hass, "bus")
                else None
            ),
            state_persistor=self._async_persist_runtime_state,
            session_finisher=partial(self._async_release_light_profile, config.subentry_id),
            session_discarder=partial(self._discard_light_profile, config.subentry_id),
            lifecycle_executor=partial(self._async_execute_lifecycle, config.subentry_id),
        )
        self.controllers[config.subentry_id] = runtime
        self._subentry_fingerprints[config.subentry_id] = self._fingerprint(subentry)
        self.controller_errors.pop(config.subentry_id, None)
        await runtime.async_start()
        self._register_controller_listeners(runtime)
        await self._safe_reconcile(runtime, ReconcileReason.STARTUP)
        self._notify_controller_listeners("added", config.subentry_id, runtime)
        return runtime

    async def async_remove_controller(self, subentry_id: str) -> None:
        """Remove one controller and all callbacks it registered."""

        runtime = self.controllers.get(subentry_id)
        for remove in self._remove_callbacks.pop(subentry_id, ()):
            remove()
        self.controller_errors.pop(subentry_id, None)
        self._subentry_fingerprints.pop(subentry_id, None)
        if runtime is not None:
            self._notify_controller_listeners("removed", subentry_id, runtime)
            await runtime.async_stop()
        self.controllers.pop(subentry_id, None)
        self._light_profiles.pop(subentry_id, None)
        self._pending_light_restore = {item for item in self._pending_light_restore if item[0] != subentry_id}

    async def async_update_controller(self, subentry: Any) -> ControllerRuntime:
        """Hot-update one controller runtime from updated subentry data."""

        runtime = self.controllers.get(subentry.subentry_id)
        if runtime is None:
            return await self.async_add_controller(subentry)

        self._discard_light_profile(subentry.subentry_id)
        was_active_timer = runtime.state is ControllerState.ACTIVE_TIMER
        was_constrained = runtime.state is ControllerState.CONSTRAINED
        for remove in self._remove_callbacks.pop(subentry.subentry_id, ()):
            remove()
        await runtime.async_apply_config(self._config_from_subentry(subentry))
        self._subentry_fingerprints[subentry.subentry_id] = self._fingerprint(subentry)
        self._register_controller_listeners(runtime)
        if was_constrained:
            snapshot = self._snapshot(runtime.config, enabled=runtime.enabled)
            if snapshot.constrained:
                await runtime.async_reconcile(ReconcileReason.RECONFIGURE, snapshot)
            else:
                await runtime.async_reconcile(ReconcileReason.RECONFIGURE, snapshot)
        elif runtime.state is ControllerState.ACTIVE_TIMER or (
            was_active_timer and runtime.state is ControllerState.IDLE
        ):
            snapshot = self._snapshot(runtime.config, enabled=runtime.enabled)
            runtime.active_presence_entities = snapshot.active_presence_entities
            runtime.presence_active = bool(snapshot.active_presence_entities)
            if (
                not snapshot.enabled
                or snapshot.constrained
                or snapshot.override_active
                or snapshot.interlock_active
            ):
                await runtime.async_reconcile(ReconcileReason.RECONFIGURE, snapshot)
        else:
            await self._safe_reconcile(runtime, ReconcileReason.RECONFIGURE)
        self._notify_controller_listeners("updated", subentry.subentry_id, runtime)
        return runtime

    async def async_sync_subentries(self) -> None:
        """Synchronize live runtimes with this entry's controller configuration."""

        if controller_id := getattr(self.entry, "data", {}).get(CONTROLLER_ID_KEY):
            controller_data = {
                key: value
                for key, value in self.entry.data.items()
                if key != CONTROLLER_ID_KEY
            }
            subentries = {
                controller_id: SimpleNamespace(
                    subentry_id=controller_id,
                    data=controller_data,
                )
            }
        else:
            subentries = {
                subentry_id: subentry
                for subentry_id, subentry in getattr(
                    self.entry, "subentries", {}
                ).items()
                if getattr(subentry, "subentry_type", "controller") == "controller"
            }
        for subentry_id in set(self.controllers) - set(subentries):
            await self.async_remove_controller(subentry_id)
        for subentry_id, subentry in subentries.items():
            if subentry_id not in self.controllers:
                await self.async_add_controller(subentry)
            elif self._subentry_fingerprints.get(subentry_id) != self._fingerprint(
                subentry
            ):
                await self.async_update_controller(subentry)

    def add_controller_listener(
        self,
        callback: Callable[[str, str, ControllerRuntime | None], None],
    ) -> Callable[[], None]:
        """Subscribe entity platforms to controller lifecycle changes."""

        self._controller_listeners.add(callback)

        def _remove() -> None:
            self._controller_listeners.discard(callback)

        return _remove

    def _notify_controller_listeners(
        self,
        event: str,
        subentry_id: str,
        runtime: ControllerRuntime | None,
    ) -> None:
        for callback in tuple(self._controller_listeners):
            callback(event, subentry_id, runtime)

    @staticmethod
    def _fingerprint(subentry: Any) -> tuple[tuple[str, Any], ...]:
        return tuple(sorted(dict(getattr(subentry, "data", {})).items()))

    async def _async_execute_behavior(self, subentry_id: str, behavior: Any) -> None:
        """Apply a transition behavior to every configured controlled entity."""

        runtime = self.controllers.get(subentry_id)
        if runtime is None:
            return
        config = runtime.config
        if behavior is TransitionBehavior.RESTORE:
            await self._async_restore_outputs(subentry_id)
            return
        if behavior.value not in {"on", "off"} or not config.control_entities:
            return
        service_data: dict[str, Any] = dict(
            config.service_data_on if behavior.value == "on" else config.service_data_off
        )
        if runtime.night_active and config.night_mode is not None:
            night_key = (
                "service_data_on" if behavior.value == "on" else "service_data_off"
            )
            if night_data := config.night_mode.get(night_key):
                service_data = dict(night_data)
        by_domain: dict[str, list[str]] = defaultdict(list)
        for entity_id in config.control_entities:
            domain, _, _ = entity_id.partition(".")
            if domain:
                by_domain[domain].append(entity_id)
        context = self.contexts.new_action_context(None)
        runtime.last_action_context_is_own = self.contexts.is_own_context(context)
        for domain, entity_ids in by_domain.items():
            domain_data = {
                key: value for key, value in service_data.items()
                if (domain == "light" or key not in _LIGHT_ONLY_FIELDS)
                and (domain == "fan" or key != "percentage")
            }
            previous_profiles = {
                entity_id: deepcopy(self._light_profiles.get(subentry_id, {}).get(entity_id))
                for entity_id in entity_ids
            }
            if domain == "light" and behavior.value == "on":
                for entity_id in entity_ids:
                    self._capture_light_profile(subentry_id, entity_id, domain_data)
            try:
                await self.hass.services.async_call(
                    domain,
                    f"turn_{behavior.value}",
                    {"entity_id": entity_ids, **domain_data},
                    blocking=True,
                    context=context,
                )
            except Exception as err:
                self.controller_errors[subentry_id] = f"{domain}.turn_{behavior.value}: {err}"
                runtime.last_action_result = "failed"
                runtime.last_action_error = str(err)
                if behavior.value == "on":
                    for entity_id in entity_ids:
                        old_profile = previous_profiles[entity_id]
                        profiles = self._light_profiles.get(subentry_id, {})
                        if old_profile is None:
                            profiles.pop(entity_id, None)
                        else:
                            profiles[entity_id] = old_profile
                        self._original_output_states.get(subentry_id, {}).pop(entity_id, None)
                    runtime.snapshot_held = bool(self._original_output_states.get(subentry_id))

    async def _async_execute_lifecycle(self, subentry_id: str, key: str) -> bool:
        runtime = self.controllers.get(subentry_id)
        if runtime is None:
            return False
        behavior = runtime.config.transition_behaviors.get(key, TransitionBehavior.IGNORE)
        sequence = runtime.config.lifecycle_actions.get(key) if behavior is TransitionBehavior.CUSTOM else None
        if key == "on_enter_active" and (sequence or behavior is TransitionBehavior.ON):
            self._original_output_states[subentry_id] = {
                entity_id: (state.state, dict(state.attributes or {}))
                for entity_id in runtime.config.control_entities
                if (state := self.hass.states.get(entity_id)) is not None
            }
            self._output_session_open.add(subentry_id)
            self._output_session_started[subentry_id] = runtime.last_transition_at
            self._manual_output_sessions.discard(subentry_id)
            runtime.snapshot_held = bool(self._original_output_states[subentry_id])
            runtime.snapshot_generation += 1
            runtime.restore_skipped_manual = False
        elif key.startswith("on_enter_") and key != "on_enter_active":
            self._original_output_states.pop(subentry_id, None)
            runtime.snapshot_held = False
        if not sequence:
            return False
        from .lifecycle import async_execute_sequence

        context = self.contexts.new_action_context(None)
        runtime.last_action_context_is_own = self.contexts.is_own_context(context)
        task = asyncio.create_task(async_execute_sequence(
            self.hass, sequence, name=f"EC {runtime.config.name}: {key}",
            context=context,
            variables={"controller_id": subentry_id, "controller_name": runtime.config.name, "night_active": runtime.night_active},
        ))
        self._lifecycle_tasks[subentry_id] = task
        runtime.last_action_hook = key
        runtime.last_action_at = runtime._clock()
        runtime.last_action_result = "running"
        runtime.last_action_error = None
        try:
            await task
            runtime.last_action_result = "completed"
        except asyncio.CancelledError:
            runtime.last_action_result = "cancelled"
            if not task.cancelled():
                raise
        except Exception as err:
            self.controller_errors[subentry_id] = f"{key}: {err}"
            runtime.last_action_result = "failed"
            runtime.last_action_error = str(err)
        finally:
            if self._lifecycle_tasks.get(subentry_id) is task:
                self._lifecycle_tasks.pop(subentry_id, None)
        return True

    async def _async_restore_outputs(self, subentry_id: str) -> None:
        runtime = self.controllers.get(subentry_id)
        if runtime is None or subentry_id in self._manual_output_sessions or runtime.transition_cause_in_progress is TransitionCause.MANUAL_CONTROL:
            self._original_output_states.pop(subentry_id, None)
            if runtime is not None:
                runtime.snapshot_held = False
                runtime.restore_skipped_manual = True
            return
        runtime.snapshot_held = False
        originals = self._original_output_states.pop(subentry_id, {})
        for entity_id, (original_state, attributes) in originals.items():
            current = self.hass.states.get(entity_id)
            if current is None or original_state not in {"on", "off"} or current.state not in {"on", "off"}:
                self.controller_errors[subentry_id] = f"Restore skipped unavailable or unknown output: {entity_id}"
                continue
            domain = entity_id.partition(".")[0]
            data: dict[str, Any] = {"entity_id": [entity_id]}
            if domain == "light" and original_state == "on":
                values = self._light_values(attributes)
                if values.get("brightness") is not None:
                    data["brightness"] = values["brightness"]
                color_key = {"hs": "hs_color", "xy": "xy_color", "rgb": "rgb_color", "rgbw": "rgbw_color", "rgbww": "rgbww_color"}.get(values.get("color_mode"), "color_temp_kelvin")
                if values.get(color_key) is not None:
                    data[color_key] = values[color_key]
            if domain == "fan" and original_state == "on" and attributes.get("percentage") is not None:
                data["percentage"] = attributes["percentage"]
            if domain == "light" and original_state == "on" and attributes.get("effect") in (attributes.get("effect_list") or ()):
                data["effect"] = attributes["effect"]
            current_values = self._light_values(current.attributes)
            if current.state == original_state and all(current_values.get(key) == value for key, value in data.items() if key != "entity_id"):
                continue
            try:
                await self.hass.services.async_call(domain, f"turn_{original_state}", data, blocking=True, context=self.contexts.new_action_context(None))
            except Exception as err:
                self.controller_errors[subentry_id] = f"Restore failed for {entity_id}: {err}"

    def _discard_light_profile(self, subentry_id: str) -> None:
        runtime = self.controllers.get(subentry_id)
        if runtime is not None:
            runtime.snapshot_held = False
        task = self._lifecycle_tasks.pop(subentry_id, None)
        if task is not None:
            task.cancel()
        self._light_profiles.pop(subentry_id, None)
        self._original_output_states.pop(subentry_id, None)
        self._output_session_started.pop(subentry_id, None)
        self._manual_output_sessions.discard(subentry_id)
        self._output_session_open.discard(subentry_id)
        self._pending_light_restore = {item for item in self._pending_light_restore if item[0] != subentry_id}

    @staticmethod
    def _light_values(attributes: Any) -> dict[str, Any]:
        values = dict(attributes or {})
        if values.get("color_temp_kelvin") is None and values.get("color_temp"):
            values["color_temp_kelvin"] = round(1000000 / values["color_temp"])
        return values

    def _capture_light_profile(self, subentry_id: str, entity_id: str, data: dict[str, Any]) -> None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return
        values = self._light_values(state.attributes)
        changes = {}
        if "brightness" in data:
            changes["brightness"] = data["brightness"]
        elif "brightness_pct" in data:
            changes["brightness"] = round(float(data["brightness_pct"]) * 255 / 100)
        kelvin = data.get("color_temp_kelvin", data.get("kelvin"))
        if kelvin is None and data.get("color_temp"):
            kelvin = round(1000000 / data["color_temp"])
        if kelvin is not None:
            changes["color_temp_kelvin"] = kelvin
        profiles = self._light_profiles.setdefault(subentry_id, {})
        profile = profiles.setdefault(entity_id, {"original": {}, "owned": {}})
        for key, value in changes.items():
            if key == "color_temp_kelvin":
                original_key = {
                    "hs": "hs_color", "xy": "xy_color", "rgb": "rgb_color",
                    "rgbw": "rgbw_color", "rgbww": "rgbww_color",
                }.get(values.get("color_mode"), key)
            else:
                original_key = key
            if original_key in values and values[original_key] is not None:
                profile["original"].setdefault(key, (original_key, values[original_key]))
                profile["owned"][key] = value
        self._pending_light_restore.discard((subentry_id, entity_id))

    def _relinquish_changed_light_fields(self, subentry_id: str, entity_id: str, event: Any) -> None:
        profile = self._light_profiles.get(subentry_id, {}).get(entity_id)
        if not profile:
            return
        event_data = event if isinstance(event, dict) else event.data
        state = event_data.get("new_state")
        if state is None:
            return
        values = self._light_values(state.attributes)
        for key, owned in tuple(profile["owned"].items()):
            # Many devices omit attributes while off: omission is not a manual edit.
            if key in values and values[key] is not None and values[key] != owned:
                profile["owned"].pop(key)
            elif key == "color_temp_kelvin" and state.state == "on" and values.get("color_mode") not in (None, "color_temp"):
                profile["owned"].pop(key)

    async def _async_release_light_profile(self, subentry_id: str) -> None:
        runtime = self.controllers.get(subentry_id)
        started = self._output_session_started.get(subentry_id)
        if runtime is not None and runtime.manual_control_at is not None and started is not None and runtime.manual_control_at >= started:
            self._manual_output_sessions.add(subentry_id)
            self._original_output_states.pop(subentry_id, None)
            runtime.snapshot_held = False
            if runtime.selected_exit_strategy == "restore":
                runtime.restore_skipped_manual = True
        task = self._lifecycle_tasks.pop(subentry_id, None)
        if task is not None and not task.done():
            task.cancel()
        self._output_session_open.discard(subentry_id)
        for entity_id in tuple(self._light_profiles.get(subentry_id, {})):
            await self._async_restore_light(subentry_id, entity_id)

    async def _async_restore_light(self, subentry_id: str, entity_id: str) -> None:
        profiles = self._light_profiles.get(subentry_id, {})
        profile = profiles.get(entity_id)
        if profile is None:
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state != "on":
            self._pending_light_restore.add((subentry_id, entity_id))
            return
        values = self._light_values(state.attributes)
        data = {}
        for key, owned in profile["owned"].items():
            if values.get(key) != owned:
                continue
            if key == "color_temp_kelvin" and values.get("color_mode") not in (None, "color_temp"):
                continue
            original_key, original = profile["original"][key]
            data[original_key] = original
        # Remove before the service call: own state events can re-enter listeners.
        profiles.pop(entity_id, None)
        self._pending_light_restore.discard((subentry_id, entity_id))
        if data:
            try:
                await self.hass.services.async_call(
                    "light", "turn_on", {"entity_id": [entity_id], **data},
                    blocking=True, context=self.contexts.new_action_context(None),
                )
            except Exception as err:
                self.controller_errors[subentry_id] = f"Profile restore failed for {entity_id}: {err}"

    async def _async_persist_runtime_state(self, runtime: ControllerRuntime) -> None:
        """Persist controller-owned switches in the entry or legacy subentry."""

        if not hasattr(self.hass, "config_entries"):
            return
        if getattr(self.entry, "data", {}).get(CONTROLLER_ID_KEY):
            data = dict(self.entry.data)
            data["enabled"] = runtime.enabled
            data["stay_mode"] = runtime.stay_mode
            self.hass.config_entries.async_update_entry(self.entry, data=data)
            return
        subentry = getattr(self.entry, "subentries", {}).get(runtime.config.subentry_id)
        if subentry is None or not hasattr(
            self.hass.config_entries, "async_update_subentry"
        ):
            return
        data = dict(subentry.data)
        data["enabled"] = runtime.enabled
        data["stay_mode"] = runtime.stay_mode
        self.hass.config_entries.async_update_subentry(
            self.entry,
            subentry,
            data=data,
        )

    async def async_reconcile_controller(
        self,
        subentry_id: str,
        reason: ReconcileReason,
    ) -> ControllerState | None:
        """Reconcile one controller without affecting sibling controllers."""

        runtime = self.controllers.get(subentry_id)
        if runtime is None:
            return None
        return await self._safe_reconcile(runtime, reason)

    def _config_from_subentry(self, subentry: Any) -> ControllerConfig:
        data = dict(getattr(subentry, "data", {}))
        kwargs: dict[str, Any] = {
            "subentry_id": subentry.subentry_id,
            "name": data.pop("name", subentry.subentry_id),
            "entity_unique_id_prefix": data.pop(ENTITY_UNIQUE_ID_PREFIX_KEY, None),
        }
        data.pop(CONTROLLER_ID_KEY, None)
        for field in _ENTITY_FIELDS:
            if field in data:
                kwargs[field] = tuple(data.pop(field) or ())
        for field in _STATE_LIST_FIELDS:
            if field in data:
                kwargs[field] = tuple(data.pop(field) or ())
        if "sensor_type" in data:
            data["sensor_type"] = SensorType(data["sensor_type"])
        if "transition_behaviors" in data:
            data["transition_behaviors"] = normalize_transition_behaviors(data["transition_behaviors"])
        if "enabled" in data:
            data["enabled_default"] = bool(data.pop("enabled"))
        if "stay_mode" in data:
            data["stay_mode_default"] = bool(data.pop("stay_mode"))
        kwargs.update(data)
        return ControllerConfig(**kwargs)

    def _register_controller_listeners(self, runtime: ControllerRuntime) -> None:
        config = runtime.config
        removers: list[Callable[[], None]] = []
        for entity_id in config.trigger_entities:
            removers.append(
                self._track_state(entity_id, self._trigger_listener(runtime))
            )
        for entity_id in config.presence_entities:
            removers.append(self._track_state(entity_id, self._presence_listener(runtime)))
        for entity_id in (*config.control_entities, *config.state_entities):
            removers.append(self._track_state(entity_id, self._state_listener(runtime)))
        for entity_id in config.override_entities:
            removers.append(
                self._track_state(entity_id, self._override_listener(runtime))
            )
        for entity_id in config.interlock_entities:
            removers.append(
                self._track_state(entity_id, self._interlock_listener(runtime))
            )
        self._remove_callbacks[config.subentry_id] = removers

    def _track_state(
        self, entity_id: str, callback: Callable[[Any], Any]
    ) -> Callable[[], None]:
        if hasattr(self.hass, "track_state"):
            return self.hass.track_state(entity_id, callback)

        from homeassistant.helpers.event import async_track_state_change_event

        return async_track_state_change_event(self.hass, [entity_id], callback)

    def _trigger_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            await self._async_refresh_time_windows(runtime)
            entity_id = self._event_entity_id(event)
            runtime.active_triggers = tuple(
                candidate
                for candidate in runtime.config.trigger_entities
                if self._entity_matches(candidate, runtime.config.trigger_on_states)
            )
            if self._event_matches(event, runtime.config.trigger_on_states):
                await runtime.async_handle_sensor_on(entity_id)
            elif self._event_matches(event, runtime.config.trigger_off_states):
                other_active = any(
                    self._entity_matches(candidate, runtime.config.trigger_on_states)
                    for candidate in runtime.config.trigger_entities
                    if candidate != entity_id
                )
                await runtime.async_handle_sensor_off(
                    entity_id, sensor_active=other_active
                )

        return _handle

    def _presence_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            entity_id = self._event_entity_id(event)
            if self._event_matches(event, runtime.config.presence_on_states):
                active = set(runtime.active_presence_entities)
                active.add(entity_id)
            elif self._event_matches(event, runtime.config.presence_off_states):
                active = set(runtime.active_presence_entities)
                active.discard(entity_id)
            else:
                return  # Unknown/unavailable is not an explicit vacancy event.
            runtime.active_presence_entities = tuple(
                candidate for candidate in runtime.config.presence_entities if candidate in active
            )
            await runtime.async_handle_presence_change(entity_id, is_active=bool(active))
        return _handle

    async def _async_refresh_time_windows(self, runtime: ControllerRuntime) -> None:
        """Refresh constraint and day/night profile before processing an event."""

        now = self._now()
        sunrise, sunset = self._sun_events(
            now,
            runtime.config.constraint_window,
            runtime.config.night_mode,
        )
        constrained = bool(
            runtime.config.constraint_window
            and not window_is_active_from_data(
                dict(runtime.config.constraint_window),
                now,
                sunrise=sunrise,
                sunset=sunset,
            )
        )
        night_active = bool(
            runtime.config.night_mode
            and window_is_active_from_data(
                dict(runtime.config.night_mode),
                now,
                sunrise=sunrise,
                sunset=sunset,
            )
        )
        if runtime.night_active != night_active:
            await self._async_release_light_profile(runtime.config.subentry_id)
        runtime.night_active = night_active
        was_constrained = runtime.constrained
        runtime.constrained = constrained
        if constrained and (
            not was_constrained or runtime.state is not ControllerState.CONSTRAINED
        ):
            if runtime.enabled:
                await runtime.async_transition(
                    ControllerState.CONSTRAINED,
                    TransitionCause.CONSTRAINT,
                )
            else:
                await runtime.async_reconcile(
                    ReconcileReason.RESTORE,
                    self._snapshot(runtime.config, enabled=runtime.enabled),
                )
        elif not constrained and runtime.state is ControllerState.CONSTRAINED:
            await runtime.async_resume_after_constraint(
                self._snapshot(runtime.config, enabled=runtime.enabled)
            )

    async def async_refresh_time_windows(self) -> None:
        """Refresh every configured schedule on a shared minute boundary."""

        for runtime in tuple(self.controllers.values()):
            if runtime.config.constraint_window or runtime.config.night_mode:
                await self._async_refresh_time_windows(runtime)

    def _state_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            entity_id = self._event_entity_id(event)
            context = self._event_context(event)
            if not self._is_ec_context(context):
                self._relinquish_changed_light_fields(runtime.config.subentry_id, entity_id, event)
            if (runtime.config.subentry_id, entity_id) in self._pending_light_restore:
                await self._async_restore_light(runtime.config.subentry_id, entity_id)
            if self._only_ignored_attributes_changed(
                event, runtime.config.state_attributes_ignore
            ) or not self._is_significant_output_change(event, runtime):
                return
            context = self._event_context(event)
            entity_id = self._event_entity_id(event)
            runtime.active_state_entities = tuple(
                candidate
                for candidate in (
                    *runtime.config.state_entities,
                    *runtime.config.control_entities,
                )
                if self._entity_matches(candidate, runtime.config.state_on_states)
            )
            if not (
                self._event_matches(event, runtime.config.state_on_states)
                or self._event_matches(event, runtime.config.state_off_states)
            ):
                return
            is_on = self._event_matches(event, runtime.config.state_on_states)
            other_is_on = any(
                self._entity_matches(candidate, runtime.config.state_on_states)
                for candidate in (
                    *runtime.config.control_entities,
                    *runtime.config.state_entities,
                )
                if candidate != entity_id
            )
            await runtime.async_handle_state_entity_change(
                entity_id,
                is_on=is_on or other_is_on,
                is_own_context=self._is_ec_context(context),
                manual_control_kind=self._manual_event_kind(event),
            )

        return _handle

    def _is_ec_context(self, context: Any) -> bool:
        """Recognize contexts of every loaded EC entry on this HA instance."""

        if self.contexts.is_own_context(context):
            return True
        managers = getattr(self.hass, "data", {}).get(DOMAIN, {})
        if not isinstance(managers, dict):
            return False
        return any(
            getattr(manager, "contexts", None) is not None
            and manager.contexts.is_own_context(context)
            for manager in managers.values()
        )

    @staticmethod
    def _is_significant_output_change(event: Any, runtime: ControllerRuntime) -> bool:
        data = event if isinstance(event, dict) else event.data
        entity_id = data.get("entity_id", "")
        if entity_id not in runtime.config.control_entities:
            return True
        old, new = data.get("old_state"), data.get("new_state")
        if old is None or new is None or old.state != new.state:
            return True
        fields = {
            "light": {"brightness", "color_temp", "color_temp_kelvin", "color_mode", "hs_color", "rgb_color", "rgbw_color", "rgbww_color", "xy_color", "effect", "white"},
            "fan": {"percentage", "speed", "preset_mode", "direction", "oscillating"},
            "switch": set(),
            "input_boolean": set(),
        }.get(entity_id.partition(".")[0])
        if fields is None:
            return True
        fields -= set(runtime.config.state_attributes_ignore)
        old_attributes = dict(getattr(old, "attributes", {}) or {})
        new_attributes = dict(getattr(new, "attributes", {}) or {})
        return any(old_attributes.get(key) != new_attributes.get(key) for key in fields)

    @staticmethod
    def _manual_event_kind(event: Any) -> str:
        data = event if isinstance(event, dict) else event.data
        old, new = data.get("old_state"), data.get("new_state")
        if old is not None and new is not None and old.state == new.state:
            return "manual_attribute_change"
        return "manual_on" if new is not None and new.state == "on" else "manual_off"

    @staticmethod
    def _only_ignored_attributes_changed(
        event: Any,
        ignored_attributes: tuple[str, ...],
    ) -> bool:
        if not ignored_attributes:
            return False
        data = event if isinstance(event, dict) else event.data
        old_state = data.get("old_state")
        new_state = data.get("new_state")
        if old_state is None or new_state is None or old_state.state != new_state.state:
            return False
        old_attributes = dict(getattr(old_state, "attributes", {}) or {})
        new_attributes = dict(getattr(new_state, "attributes", {}) or {})
        changed = {
            key
            for key in old_attributes.keys() | new_attributes.keys()
            if old_attributes.get(key) != new_attributes.get(key)
        }
        return bool(changed) and changed <= set(ignored_attributes)

    def _override_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            entity_id = self._event_entity_id(event)
            runtime.active_overrides = tuple(
                candidate
                for candidate in runtime.config.override_entities
                if self._entity_matches(candidate, runtime.config.override_on_states)
            )
            is_on_event = self._event_matches(event, runtime.config.override_on_states)
            is_off_event = self._event_matches(event, runtime.config.override_off_states)
            if not (is_on_event or is_off_event):
                return
            is_active = is_on_event or any(
                self._entity_matches(candidate, runtime.config.override_on_states)
                for candidate in runtime.config.override_entities
                if candidate != entity_id
            )
            await runtime.async_handle_override_change(
                entity_id,
                is_active=is_active,
            )
            if runtime.state is ControllerState.OVERRIDDEN:
                runtime.overridden_by = next(iter(runtime.active_overrides), None)

        return _handle

    def _interlock_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            await self._safe_reconcile(runtime, ReconcileReason.RESTORE)

        return _handle

    async def _safe_reconcile(
        self,
        runtime: ControllerRuntime,
        reason: ReconcileReason,
    ) -> ControllerState:
        try:
            snapshot = self._snapshot(runtime.config, enabled=runtime.enabled)
        except Exception as err:
            self.controller_errors[runtime.config.subentry_id] = str(err)
            configured_enabled = runtime.enabled
            state = await runtime.async_reconcile(
                reason,
                ReconcileSnapshot(
                    enabled=False,
                    constrained=False,
                    override_active=False,
                    interlock_active=False,
                    sensor_active=False,
                    state_entities_on=False,
                ),
            )
            runtime.enabled = configured_enabled
            return state
        self.controller_errors.pop(runtime.config.subentry_id, None)
        return await runtime.async_reconcile(reason, snapshot)

    def _snapshot(
        self, config: ControllerConfig, *, enabled: bool = True
    ) -> ReconcileSnapshot:
        now = self._now()
        observed_runtime = self.controllers.get(config.subentry_id)
        previous_presence = set(observed_runtime.active_presence_entities) if observed_runtime is not None else set()
        sunrise, sunset = self._sun_events(
            now,
            config.constraint_window,
            config.night_mode,
        )
        constrained = bool(
            config.constraint_window
            and not window_is_active_from_data(
                dict(config.constraint_window),
                now,
                sunrise=sunrise,
                sunset=sunset,
            )
        )
        night_active = bool(
            config.night_mode
            and window_is_active_from_data(
                dict(config.night_mode),
                now,
                sunrise=sunrise,
                sunset=sunset,
            )
        )
        return ReconcileSnapshot(
            enabled=enabled,
            constrained=constrained,
            override_active=any(
                self._entity_matches(entity_id, config.override_on_states)
                for entity_id in config.override_entities
            ),
            interlock_active=any(
                self._entity_is_on(entity_id) for entity_id in config.interlock_entities
            ),
            sensor_active=any(
                self._entity_matches(entity_id, config.trigger_on_states)
                for entity_id in config.trigger_entities
            ),
            state_entities_on=any(
                self._entity_matches(entity_id, config.state_on_states)
                for entity_id in (*config.state_entities, *config.control_entities)
            ),
            night_active=night_active,
            active_presence_entities=tuple(
                entity_id
                for entity_id in config.presence_entities
                if self._entity_matches(entity_id, config.presence_on_states)
                or (entity_id in previous_presence and not self._entity_matches(entity_id, config.presence_off_states))
            ),
            active_overrides=tuple(
                entity_id
                for entity_id in config.override_entities
                if self._entity_matches(entity_id, config.override_on_states)
            ),
            active_interlocks=tuple(
                entity_id
                for entity_id in config.interlock_entities
                if self._entity_is_on(entity_id)
            ),
            active_triggers=tuple(
                entity_id
                for entity_id in config.trigger_entities
                if self._entity_matches(entity_id, config.trigger_on_states)
            ),
            active_state_entities=tuple(
                entity_id
                for entity_id in (*config.state_entities, *config.control_entities)
                if self._entity_matches(entity_id, config.state_on_states)
            ),
        )

    def _sun_events(
        self,
        now: datetime,
        *windows: Any,
    ) -> tuple[datetime | None, datetime | None]:
        sources = {
            point.get("source")
            for window in windows
            if window
            for point in (window.get("start", {}), window.get("end", {}))
        }
        if not sources.intersection({"sunrise", "sunset"}):
            return None, None
        from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
        from homeassistant.helpers.sun import get_astral_event_date

        sunrise = (
            get_astral_event_date(self.hass, SUN_EVENT_SUNRISE, now.date())
            if "sunrise" in sources
            else None
        )
        sunset = (
            get_astral_event_date(self.hass, SUN_EVENT_SUNSET, now.date())
            if "sunset" in sources
            else None
        )
        return sunrise, sunset

    def _entity_is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        return str(state.state).lower() not in _OFF_STATES

    def _entity_matches(self, entity_id: str, active_states: tuple[str, ...]) -> bool:
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        return str(state.state).lower() in {
            candidate.lower() for candidate in active_states
        }

    @staticmethod
    def _event_entity_id(event: Any) -> str:
        if isinstance(event, dict):
            return event["entity_id"]
        return event.data["entity_id"]

    @staticmethod
    def _event_matches(event: Any, active_states: tuple[str, ...]) -> bool:
        if isinstance(event, dict):
            new_state = event["new_state"]
        else:
            new_state = event.data["new_state"]
        return new_state is not None and str(new_state.state).lower() in {
            candidate.lower() for candidate in active_states
        }

    @staticmethod
    def _event_context(event: Any) -> Any:
        if isinstance(event, dict):
            return event.get("context") or getattr(
                event.get("new_state"), "context", None
            )
        return event.context

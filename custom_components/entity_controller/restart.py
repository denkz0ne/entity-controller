"""Persist controller sessions and reconcile observations after HA startup."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from .const import DOMAIN
from .model import ControllerState, ReconcileReason, TransitionCause

_LOGGER = logging.getLogger(__name__)
_DATES = (
    "expires_at", "blocked_at", "block_expires_at", "last_triggered_at",
    "last_transition_at", "manual_control_at", "presence_hold_started_at",
    "last_presence_changed_at",
)
_FIELDS = (
    "manual_takeover_pending", "manual_release_ready", "manual_control_kind",
    "manual_control_entity", "blocked_by", "block_reason", "last_triggered_by",
    "last_transition_source", "backoff_count", "timer_expired_pending_sensor",
    "timer_expired_pending_presence", "snapshot_held",
)
_OUTPUT_ATTRIBUTES = (
    "brightness", "color_temp_kelvin", "color_temp", "hs_color", "rgb_color",
    "rgbw_color", "rgbww_color", "xy_color", "effect", "percentage",
    "volume_level", "source", "preset_mode",
)


def _json_copy(value: Any) -> Any:
    """Use the same representation before saving and after loading JSON."""
    return json.loads(json.dumps(value))


class RestartStateManager:
    """Own one config entry's durable checkpoints and startup readiness gate."""

    def __init__(self, manager: Any, store: Any = None) -> None:
        self.manager = manager
        self.store = store
        self.records: dict[str, Any] = {}
        self.pending: set[str] = set()
        self.removers: dict[str, list[Any]] = {}
        self.stop_listener: Any = None
        self.stopping = False

    async def async_load(self) -> None:
        hass = self.manager.hass
        if self.store is None and hasattr(hass, "async_add_executor_job"):
            from homeassistant.helpers.storage import Store

            self.store = Store(hass, 1, f"{DOMAIN}.{self.manager.entry.entry_id}.runtime")
        if self.store is not None:
            try:
                data = await self.store.async_load()
                if isinstance(data, dict) and isinstance(data.get("controllers"), dict):
                    self.records = data["controllers"]
            except Exception:
                _LOGGER.exception("Could not load EC runtime checkpoint")
        if hasattr(hass, "bus"):
            from homeassistant.const import EVENT_HOMEASSISTANT_STOP

            self.stop_listener = hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self.async_stop
            )

    def prepare(self, runtime: Any) -> None:
        self.pending.add(runtime.config.subentry_id)
        # An observed ON during boot is not evidence of a manual action.
        runtime.manual_release_ready = True
        self.removers[runtime.config.subentry_id] = [
            runtime.add_update_listener(lambda: self.capture(runtime))
        ]

    def entities(self, runtime: Any) -> dict[str, Any]:
        config = runtime.config
        entities = {}
        for entity_id in dict.fromkeys((
            *config.trigger_entities, *config.presence_entities,
            *config.control_entities, *config.state_entities,
            *config.override_entities, *config.interlock_entities,
        )):
            observed = self.manager.hass.states.get(entity_id)
            attributes = getattr(observed, "attributes", {}) or {}
            entities[entity_id] = {
                "state": getattr(observed, "state", None),
                "attributes": {
                    key: attributes[key] for key in _OUTPUT_ATTRIBUTES
                    if key in attributes and entity_id in config.control_entities
                },
            }
        return _json_copy(entities)

    def capture(self, runtime: Any) -> None:
        controller_id = runtime.config.subentry_id
        if self.stopping or controller_id in self.pending:
            return
        try:
            self.records[controller_id] = {
                "state": runtime.state.value,
                "entities": self.entities(runtime),
                "config": _json_copy(dict(self.manager._subentry_fingerprints[controller_id])),
                "fields": {key: getattr(runtime, key) for key in _FIELDS},
                "dates": {
                    key: value.isoformat() if (value := getattr(runtime, key)) else None
                    for key in _DATES
                },
                "cause": runtime.last_transition_cause.value if runtime.last_transition_cause else None,
                "profiles": _json_copy(self.manager._light_profiles.get(controller_id, {})),
                "original_outputs": _json_copy(self.manager._original_output_states.get(controller_id, {})),
                "session_open": controller_id in self.manager._output_session_open,
                "session_started": (
                    value.isoformat() if (value := self.manager._output_session_started.get(controller_id)) else None
                ),
            }
            if self.store is not None:
                self.store.async_delay_save(self._data, 1)
        except Exception:
            _LOGGER.exception("Could not capture EC runtime checkpoint for %s", controller_id)

    def _data(self) -> dict[str, Any]:
        return _json_copy({"controllers": self.records})

    async def async_stop(self, _event: Any = None) -> None:
        if not self.stopping:
            for runtime in self.manager.controllers.values():
                self.capture(runtime)
            self.stopping = True
        if self.store is not None:
            try:
                await self.store.async_save(self._data())
            except Exception:
                _LOGGER.exception("Could not save EC runtime checkpoint")

    def remove(self, runtime: Any) -> None:
        controller_id = runtime.config.subentry_id
        for remove in self.removers.pop(controller_id, []):
            remove()
        self.pending.discard(controller_id)
        if not self.stopping:
            self.records.pop(controller_id, None)
            if self.store is not None:
                self.store.async_delay_save(self._data, 1)

    async def async_start(self, runtime: Any) -> None:
        hass = self.manager.hass
        if not hasattr(hass, "bus"):
            await self._initialize(runtime, allow_partial=True)
            return

        async def started(_event: Any = None) -> None:
            if runtime.config.subentry_id not in self.pending:
                return
            if await self._initialize(runtime):
                return
            from homeassistant.helpers.event import async_call_later

            async def settle(_now: Any) -> None:
                if runtime.config.subentry_id in self.pending:
                    await self._initialize(runtime, allow_partial=True)

            self.removers[runtime.config.subentry_id].append(async_call_later(hass, 30, settle))

        if hass.is_running:
            await started()
        else:
            from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

            self.removers[runtime.config.subentry_id].append(
                hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, started)
            )

    def guard(self, runtime: Any, callback: Any) -> Any:
        async def guarded(event: Any) -> None:
            if self.stopping:
                return
            if runtime.config.subentry_id in self.pending:
                if getattr(self.manager.hass, "is_running", True):
                    await self._initialize(runtime)
                return
            await callback(event)
            self.capture(runtime)

        return guarded

    async def _initialize(self, runtime: Any, *, allow_partial: bool = False) -> bool:
        controller_id = runtime.config.subentry_id
        try:
            entities = self.entities(runtime)
            if not allow_partial and any(
                value["state"] in {None, "unknown", "unavailable"} for value in entities.values()
            ):
                return False
            snapshot = self.manager._snapshot(runtime.config, enabled=runtime.enabled)
            saved = self.records.get(controller_id, {})
            matches = (
                saved.get("entities") == entities
                and saved.get("config") == _json_copy(dict(self.manager._subentry_fingerprints[controller_id]))
                and all(value["state"] not in {None, "unknown", "unavailable"} for value in entities.values())
            )
            runtime.restart_restore_status = "matched" if matches else "changed" if saved else "missing"
            resumed = False
            if matches and snapshot.enabled and not (
                snapshot.constrained or snapshot.override_active or snapshot.interlock_active
            ):
                resumed = self._restore(runtime, saved, snapshot)
            if not resumed:
                runtime.manual_takeover_pending = False
                runtime.manual_release_ready = True
                await self.manager._safe_reconcile(runtime, ReconcileReason.STARTUP)
        except Exception:
            _LOGGER.exception("Could not restore EC startup state for %s", controller_id)
            runtime.manual_takeover_pending = False
            runtime.manual_release_ready = True
            runtime.restart_restore_status = "invalid"
            await self.manager._safe_reconcile(runtime, ReconcileReason.STARTUP)
        self.pending.discard(controller_id)
        runtime._notify_updated()
        return True

    def _restore(self, runtime: Any, saved: dict[str, Any], snapshot: Any) -> bool:
        state = ControllerState(saved["state"])
        fields = saved["fields"]
        # Preserve real manual protection, never the old generic startup block.
        if state is ControllerState.BLOCKED and not fields.get("manual_takeover_pending"):
            return False
        if state not in {
            ControllerState.ACTIVE_TIMER, ControllerState.ACTIVE_STAY_ON,
            ControllerState.BLOCKED, ControllerState.IDLE,
        }:
            return False
        dates = {
            key: datetime.fromisoformat(value) if value else None
            for key, value in saved["dates"].items() if key in _DATES
        }
        if any(value is not None and value.tzinfo is None for value in dates.values()):
            return False
        cause = TransitionCause(saved["cause"]) if saved.get("cause") else None
        runtime._apply_snapshot(snapshot)
        runtime.state = state
        runtime.last_reconcile_reason = ReconcileReason.RESTORE
        runtime.last_transition_cause = cause
        for key in _FIELDS:
            if key in fields:
                setattr(runtime, key, fields[key])
        for key, value in dates.items():
            setattr(runtime, key, value)
        if state in {ControllerState.ACTIVE_TIMER, ControllerState.ACTIVE_STAY_ON}:
            controller_id = runtime.config.subentry_id
            self.manager._light_profiles[controller_id] = saved.get("profiles", {})
            self.manager._original_output_states[controller_id] = saved.get("original_outputs", {})
            if saved.get("session_open"):
                self.manager._output_session_open.add(controller_id)
                self.manager._output_session_started[controller_id] = (
                    datetime.fromisoformat(saved["session_started"]) if saved.get("session_started") else None
                )
        if state is ControllerState.ACTIVE_TIMER and runtime.expires_at is not None:
            runtime._schedule_timer_at(max(runtime.expires_at, runtime._clock()))
        elif state is ControllerState.ACTIVE_TIMER and not (
            runtime.timer_expired_pending_sensor or runtime.timer_expired_pending_presence
        ):
            runtime._schedule_main_timer(reset=False)
        elif state is ControllerState.BLOCKED:
            runtime._schedule_block_timer()
        return True

"""Root runtime manager for Entity Controller v10."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from .context import ContextTracker
from .controller import ControllerRuntime, ReconcileSnapshot
from .model import ControllerConfig, ControllerState, ReconcileReason, SensorType
from .schedule import schedule_at_home_assistant

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_ENTITY_FIELDS = {
    "trigger_entities",
    "control_entities",
    "state_entities",
    "override_entities",
    "interlock_entities",
}
_OFF_STATES = {"off", "unavailable", "unknown", ""}


class EntityControllerManager:
    """Own controller runtimes for one Entity Controller config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
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
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return whether the manager lifecycle is active."""

        return self._loaded

    async def async_setup(self) -> None:
        """Initialize manager-owned runtime resources."""

        self._loaded = True
        await self.async_sync_subentries()

    async def async_unload(self) -> None:
        """Release manager-owned runtime resources."""

        for subentry_id in tuple(self.controllers):
            await self.async_remove_controller(subentry_id)
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

        runtime = self.controllers.pop(subentry_id, None)
        for remove in self._remove_callbacks.pop(subentry_id, ()):
            remove()
        self.controller_errors.pop(subentry_id, None)
        self._subentry_fingerprints.pop(subentry_id, None)
        if runtime is not None:
            self._notify_controller_listeners("removed", subentry_id, runtime)
            await runtime.async_stop()

    async def async_update_controller(self, subentry: Any) -> ControllerRuntime:
        """Hot-update one controller runtime from updated subentry data."""

        runtime = self.controllers.get(subentry.subentry_id)
        if runtime is None:
            return await self.async_add_controller(subentry)

        for remove in self._remove_callbacks.pop(subentry.subentry_id, ()):
            remove()
        await runtime.async_apply_config(self._config_from_subentry(subentry))
        self._subentry_fingerprints[subentry.subentry_id] = self._fingerprint(subentry)
        self._register_controller_listeners(runtime)
        if runtime.state is not ControllerState.ACTIVE_TIMER:
            await self._safe_reconcile(runtime, ReconcileReason.RECONFIGURE)
        self._notify_controller_listeners("updated", subentry.subentry_id, runtime)
        return runtime

    async def async_sync_subentries(self) -> None:
        """Synchronize live runtimes with the config entry's controller subentries."""

        subentries = {
            subentry_id: subentry
            for subentry_id, subentry in getattr(self.entry, "subentries", {}).items()
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
        if behavior.value not in {"on", "off"} or not config.control_entities:
            return
        by_domain: dict[str, list[str]] = defaultdict(list)
        for entity_id in config.control_entities:
            domain, _, _ = entity_id.partition(".")
            if domain:
                by_domain[domain].append(entity_id)
        context = self.contexts.new_action_context(None)
        for domain, entity_ids in by_domain.items():
            await self.hass.services.async_call(
                domain,
                f"turn_{behavior.value}",
                {"entity_id": entity_ids},
                blocking=True,
                context=context,
            )

    async def _async_persist_runtime_state(self, runtime: ControllerRuntime) -> None:
        """Persist controller-owned switches in its config subentry."""

        if not hasattr(self.hass, "config_entries"):
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
        }
        for field in _ENTITY_FIELDS:
            if field in data:
                kwargs[field] = tuple(data.pop(field) or ())
        if "sensor_type" in data:
            data["sensor_type"] = SensorType(data["sensor_type"])
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
            entity_id = self._event_entity_id(event)
            if self._event_new_is_on(event):
                await runtime.async_handle_sensor_on(entity_id)
            else:
                other_active = any(
                    self._entity_is_on(candidate)
                    for candidate in runtime.config.trigger_entities
                    if candidate != entity_id
                )
                await runtime.async_handle_sensor_off(
                    entity_id, sensor_active=other_active
                )

        return _handle

    def _state_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            context = self._event_context(event)
            entity_id = self._event_entity_id(event)
            is_on = self._event_new_is_on(event)
            other_is_on = any(
                self._entity_is_on(candidate)
                for candidate in (
                    *runtime.config.control_entities,
                    *runtime.config.state_entities,
                )
                if candidate != entity_id
            )
            await runtime.async_handle_state_entity_change(
                entity_id,
                is_on=is_on or other_is_on,
                is_own_context=self.contexts.is_own_context(context),
            )

        return _handle

    def _override_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            entity_id = self._event_entity_id(event)
            is_active = self._event_new_is_on(event)
            if not is_active:
                is_active = any(
                    self._entity_is_on(candidate)
                    for candidate in runtime.config.override_entities
                    if candidate != entity_id
                )
            await runtime.async_handle_override_change(
                entity_id,
                is_active=is_active,
            )

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
        return ReconcileSnapshot(
            enabled=enabled,
            constrained=False,
            override_active=any(
                self._entity_is_on(entity_id) for entity_id in config.override_entities
            ),
            interlock_active=any(
                self._entity_is_on(entity_id) for entity_id in config.interlock_entities
            ),
            sensor_active=any(
                self._entity_is_on(entity_id) for entity_id in config.trigger_entities
            ),
            state_entities_on=any(
                self._entity_is_on(entity_id)
                for entity_id in (*config.state_entities, *config.control_entities)
            ),
        )

    def _entity_is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        return str(state.state).lower() not in _OFF_STATES

    @staticmethod
    def _event_entity_id(event: Any) -> str:
        if isinstance(event, dict):
            return event["entity_id"]
        return event.data["entity_id"]

    @staticmethod
    def _event_new_is_on(event: Any) -> bool:
        if isinstance(event, dict):
            new_state = event["new_state"]
        else:
            new_state = event.data["new_state"]
        return new_state is not None and str(new_state.state).lower() not in _OFF_STATES

    @staticmethod
    def _event_context(event: Any) -> Any:
        if isinstance(event, dict):
            return event.get("context") or getattr(
                event.get("new_state"), "context", None
            )
        return event.context

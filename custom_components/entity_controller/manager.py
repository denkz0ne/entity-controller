"""Root runtime manager for Entity Controller v10."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .controller import ControllerRuntime, ReconcileSnapshot
from .model import ControllerConfig, ControllerState, ReconcileReason, SensorType

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
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return whether the manager lifecycle is active."""

        return self._loaded

    async def async_setup(self) -> None:
        """Initialize manager-owned runtime resources."""

        self._loaded = True

    async def async_unload(self) -> None:
        """Release manager-owned runtime resources."""

        for subentry_id in tuple(self.controllers):
            await self.async_remove_controller(subentry_id)
        self._loaded = False

    async def async_add_controller(self, subentry: Any) -> ControllerRuntime:
        """Create, start and reconcile a controller runtime for a subentry."""

        config = self._config_from_subentry(subentry)
        runtime = ControllerRuntime(config)
        self.controllers[config.subentry_id] = runtime
        self.controller_errors.pop(config.subentry_id, None)
        await runtime.async_start()
        self._register_controller_listeners(runtime)
        await self._safe_reconcile(runtime, ReconcileReason.STARTUP)
        return runtime

    async def async_remove_controller(self, subentry_id: str) -> None:
        """Remove one controller and all callbacks it registered."""

        runtime = self.controllers.pop(subentry_id, None)
        for remove in self._remove_callbacks.pop(subentry_id, ()):
            remove()
        self.controller_errors.pop(subentry_id, None)
        if runtime is not None:
            await runtime.async_stop()

    async def async_update_controller(self, subentry: Any) -> ControllerRuntime:
        """Hot-update one controller runtime from updated subentry data."""

        runtime = self.controllers.get(subentry.subentry_id)
        if runtime is None:
            return await self.async_add_controller(subentry)

        for remove in self._remove_callbacks.pop(subentry.subentry_id, ()):
            remove()
        await runtime.async_apply_config(self._config_from_subentry(subentry))
        self._register_controller_listeners(runtime)
        if runtime.state is not ControllerState.ACTIVE_TIMER:
            await self._safe_reconcile(runtime, ReconcileReason.RECONFIGURE)
        return runtime

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
        kwargs.update(data)
        return ControllerConfig(**kwargs)

    def _register_controller_listeners(self, runtime: ControllerRuntime) -> None:
        config = runtime.config
        removers: list[Callable[[], None]] = []
        for entity_id in config.trigger_entities:
            removers.append(self._track_state(entity_id, self._trigger_listener(runtime)))
        for entity_id in (*config.control_entities, *config.state_entities):
            removers.append(self._track_state(entity_id, self._state_listener(runtime)))
        for entity_id in config.override_entities:
            removers.append(self._track_state(entity_id, self._override_listener(runtime)))
        for entity_id in config.interlock_entities:
            removers.append(self._track_state(entity_id, self._interlock_listener(runtime)))
        self._remove_callbacks[config.subentry_id] = removers

    def _track_state(self, entity_id: str, callback: Callable[[Any], Any]) -> Callable[[], None]:
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
                await runtime.async_handle_sensor_off(entity_id)

        return _handle

    def _state_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            await runtime.async_handle_state_entity_change(
                self._event_entity_id(event),
                is_on=self._event_new_is_on(event),
                is_own_context=False,
            )

        return _handle

    def _override_listener(self, runtime: ControllerRuntime) -> Callable[[Any], Any]:
        async def _handle(event: Any) -> None:
            await runtime.async_handle_override_change(
                self._event_entity_id(event),
                is_active=self._event_new_is_on(event),
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
            snapshot = self._snapshot(runtime.config)
        except Exception as err:
            self.controller_errors[runtime.config.subentry_id] = str(err)
            return await runtime.async_reconcile(
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
        self.controller_errors.pop(runtime.config.subentry_id, None)
        return await runtime.async_reconcile(reason, snapshot)

    def _snapshot(self, config: ControllerConfig) -> ReconcileSnapshot:
        return ReconcileSnapshot(
            enabled=True,
            constrained=False,
            override_active=any(self._entity_is_on(entity_id) for entity_id in config.override_entities),
            interlock_active=any(self._entity_is_on(entity_id) for entity_id in config.interlock_entities),
            sensor_active=any(self._entity_is_on(entity_id) for entity_id in config.trigger_entities),
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

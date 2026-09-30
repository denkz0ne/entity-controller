"""Config and config subentry flows for Entity Controller v10."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DEFAULT_DELAY_SECONDS, DOMAIN

try:
    ConfigSubentryFlow = config_entries.ConfigSubentryFlow
except AttributeError:
    class ConfigSubentryFlow:
        """Compatibility shim for test environments without HA subentry support."""


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def normalize_controller_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize controller flow input into v10 subentry data."""

    return {
        "name": str(user_input["name"]),
        "trigger_entities": _as_tuple(user_input.get("trigger_entities")),
        "control_entities": _as_tuple(user_input.get("control_entities")),
        "state_entities": _as_tuple(user_input.get("state_entities")),
        "override_entities": _as_tuple(user_input.get("override_entities")),
        "interlock_entities": _as_tuple(user_input.get("interlock_entities")),
        "sensor_type": user_input.get("sensor_type", "event"),
        "delay_seconds": float(user_input.get("delay_seconds", DEFAULT_DELAY_SECONDS)),
        "blocking_enabled": bool(user_input.get("blocking_enabled", True)),
        "stay_mode_default": bool(user_input.get("stay_mode_default", False)),
    }


class EntityControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the root Entity Controller config flow."""

    VERSION = 10

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls,
        config_entry: Any,
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentry types supported by Entity Controller."""

        return {"controller": ControllerSubentryFlowHandler}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create the single root Entity Controller entry."""

        if user_input is None:
            return {"type": "form", "step_id": "user", "errors": {}}
        return {"type": "create_entry", "title": "Entity Controller", "data": {}}


class ControllerSubentryFlowHandler(ConfigSubentryFlow):
    """Handle add/reconfigure flow for one controller subentry."""

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a controller subentry."""

        if user_input is None:
            return {"type": "form", "step_id": "user", "errors": {}}
        data = normalize_controller_user_input(user_input)
        return {
            "type": "create_entry",
            "title": data["name"],
            "subentry_type": "controller",
            "data": data,
        }

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reconfigure one controller without reloading the root entry."""

        if user_input is None:
            return {"type": "form", "step_id": "reconfigure", "errors": {}}
        return {
            "type": "update_subentry",
            "data": normalize_controller_user_input(user_input),
            "reload": False,
        }

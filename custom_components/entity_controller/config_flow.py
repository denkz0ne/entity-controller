"""Config and config subentry flows for Entity Controller v10."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import callback

from .const import DEFAULT_DELAY_SECONDS, DOMAIN

try:
    ConfigSubentryFlow = config_entries.ConfigSubentryFlow
except AttributeError:
    class ConfigSubentryFlow(data_entry_flow.FlowHandler):
        """Compatibility shim for test environments without HA subentry support."""


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(value)


ROOT_SCHEMA = vol.Schema(
    {
        vol.Required("name", default="Entity Controller"): str,
    }
)


CONTROLLER_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("trigger_entities"): str,
        vol.Required("control_entities"): str,
        vol.Optional("state_entities", default=""): str,
        vol.Optional("override_entities", default=""): str,
        vol.Optional("interlock_entities", default=""): str,
        vol.Optional("sensor_type", default="event"): vol.In(("event", "duration")),
        vol.Optional("delay_seconds", default=DEFAULT_DELAY_SECONDS): vol.Coerce(float),
        vol.Optional("blocking_enabled", default=True): bool,
        vol.Optional("stay_mode_default", default=False): bool,
    }
)


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
            return self.async_show_form(
                step_id="user",
                data_schema=ROOT_SCHEMA,
                errors={},
            )
        title = str(user_input.get("name") or "Entity Controller")
        return self.async_create_entry(title=title, data={"name": title})


class ControllerSubentryFlowHandler(ConfigSubentryFlow):
    """Handle add/reconfigure flow for one controller subentry."""

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a controller subentry."""

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=CONTROLLER_SCHEMA,
                errors={},
            )
        data = normalize_controller_user_input(user_input)
        return self.async_create_entry(title=data["name"], data=data)

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reconfigure one controller without reloading the root entry."""

        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=CONTROLLER_SCHEMA,
                errors={},
            )
        data = normalize_controller_user_input(user_input)
        return self.async_update_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            data=data,
            title=data["name"],
        )

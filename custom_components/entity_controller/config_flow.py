"""Config and config subentry flows for Entity Controller v10."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import callback
from homeassistant.helpers import selector

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
        vol.Required("name"): selector.TextSelector(),
        vol.Required("trigger_entities"): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Required("control_entities"): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Optional("state_entities", default=[]): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Optional("override_entities", default=[]): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Optional("interlock_entities", default=[]): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Optional("sensor_type", default="event"): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["event", "duration"])
        ),
        vol.Optional(
            "delay_seconds", default=DEFAULT_DELAY_SECONDS
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Optional("blocking_enabled", default=True): selector.BooleanSelector(),
        vol.Optional("stay_mode_default", default=False): selector.BooleanSelector(),
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> config_entries.OptionsFlow:
        """Open a controller form from the Helpers settings action."""

        return ControllerOptionsFlow()

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
        if (
            self.hass is not None
            and hasattr(self, "_async_current_entries")
            and self._async_current_entries()
        ):
            return self.async_abort(reason="single_instance_allowed")
        title = str(user_input.get("name") or "Entity Controller")
        return self.async_create_entry(title=title, data={"name": title})

    async def async_on_create_entry(self, result: dict[str, Any]) -> dict[str, Any]:
        """Open the first controller form immediately after creating the root."""

        subentries = self.hass.config_entries.subentries
        subentry_result = await subentries.async_init(
            (result["result"].entry_id, "controller"),
            context={"source": "user"},
        )
        try:
            from homeassistant.config_entries import FlowType

            flow_type = FlowType.CONFIG_SUBENTRIES_FLOW
        except ImportError:
            flow_type = "config_subentries_flow"
        result["next_flow"] = (flow_type, subentry_result["flow_id"])
        return result

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Rename the root entry without breaking the helper settings action."""

        entry = self._get_reconfigure_entry()
        if user_input is None:
            schema = self.add_suggested_values_to_schema(
                ROOT_SCHEMA, {"name": entry.title}
            )
            return self.async_show_form(
                step_id="reconfigure", data_schema=schema, errors={}
            )
        title = str(user_input.get("name") or "Entity Controller")
        return self.async_update_and_abort(
            entry,
            title=title,
            data={"name": title},
        )


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
            schema = CONTROLLER_SCHEMA
            if self.source == "reconfigure":
                subentry = self._get_reconfigure_subentry()
                schema = self.add_suggested_values_to_schema(
                    schema, dict(subentry.data)
                )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=schema,
                errors={},
            )
        data = normalize_controller_user_input(user_input)
        current_data = dict(getattr(self._get_reconfigure_subentry(), "data", {}))
        for key in ("enabled", "stay_mode"):
            if key in current_data:
                data[key] = current_data[key]
        return self.async_update_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            data=data,
            title=data["name"],
        )


class ControllerOptionsFlow(config_entries.OptionsFlow):
    """Add a controller when Entity Controller is opened from Helpers."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Show the add-controller form and attach the new subentry."""

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=CONTROLLER_SCHEMA,
                errors={},
            )
        data = normalize_controller_user_input(user_input)
        subentry_type = getattr(config_entries, "ConfigSubentry", None)
        if subentry_type is None:
            return self.async_abort(reason="subentries_not_supported")
        self.hass.config_entries.async_add_subentry(
            self.config_entry,
            subentry_type(
                data=MappingProxyType(data),
                subentry_type="controller",
                title=data["name"],
                unique_id=None,
            ),
        )
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

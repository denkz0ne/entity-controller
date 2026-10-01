"""Config and config subentry flows for Entity Controller v10."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_DELAY_SECONDS, DOMAIN
from .model import DEFAULT_TRANSITION_BEHAVIORS

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


def _flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Accept both native section payloads and legacy flat test/import data."""

    flattened: dict[str, Any] = {}
    for key, value in user_input.items():
        if isinstance(value, dict) and key in {
            "identity",
            "triggers",
            "targets",
            "timer",
            "blocking",
            "rules",
            "constraints",
            "night",
            "stay",
            "actions",
            "advanced",
        }:
            flattened.update(value)
        else:
            flattened[key] = value
    return flattened


def _state_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    states = _as_tuple(value)
    return states or default


def _schedule_point(data: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "source": data.get(f"{prefix}_source", "fixed"),
        "time": str(data.get(f"{prefix}_time", "00:00:00")),
        "offset_seconds": float(data.get(f"{prefix}_offset_seconds", 0)),
    }


def _number_selector(
    default: float,
    *,
    minimum: float = 0,
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


SCHEDULE_SOURCE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(options=["fixed", "sunrise", "sunset"])
)
BEHAVIOR_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(options=["on", "off", "ignore"])
)


ROOT_SCHEMA = vol.Schema(
    {
        vol.Required("name", default="Entity Controller"): str,
    }
)


CONTROLLER_SCHEMA = vol.Schema(
    {
        vol.Required("identity"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Required("name"): selector.TextSelector(),
                    vol.Optional("icon"): selector.IconSelector(),
                }
            )
        ),
        vol.Required("triggers"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Required("trigger_entities"): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional("sensor_type", default="event"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=["event", "duration"])
                    ),
                    vol.Optional(
                        "sensor_resets_timer", default=False
                    ): selector.BooleanSelector(),
                }
            )
        ),
        vol.Required("targets"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Required("control_entities"): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional("state_entities", default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                }
            )
        ),
        vol.Required("timer"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional(
                        "delay_seconds", default=DEFAULT_DELAY_SECONDS
                    ): _number_selector(DEFAULT_DELAY_SECONDS),
                    vol.Optional("backoff_enabled", default=False): selector.BooleanSelector(),
                    vol.Optional("backoff_factor", default=1.1): _number_selector(
                        1.1, minimum=1
                    ),
                    vol.Optional(
                        "backoff_max_seconds", default=300
                    ): _number_selector(300),
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("blocking"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional(
                        "blocking_enabled", default=True
                    ): selector.BooleanSelector(),
                    vol.Optional("block_timeout_seconds", default=0): _number_selector(0),
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("rules"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional("override_entities", default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional("interlock_entities", default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("constraints"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional(
                        "constraint_enabled", default=False
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "constraint_start_source", default="fixed"
                    ): SCHEDULE_SOURCE_SELECTOR,
                    vol.Optional(
                        "constraint_start_time", default="06:00:00"
                    ): selector.TimeSelector(),
                    vol.Optional(
                        "constraint_start_offset_seconds", default=0
                    ): _number_selector(0, minimum=-86400),
                    vol.Optional(
                        "constraint_end_source", default="fixed"
                    ): SCHEDULE_SOURCE_SELECTOR,
                    vol.Optional(
                        "constraint_end_time", default="23:00:00"
                    ): selector.TimeSelector(),
                    vol.Optional(
                        "constraint_end_offset_seconds", default=0
                    ): _number_selector(0, minimum=-86400),
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("night"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional(
                        "night_mode_enabled", default=False
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "night_start_source", default="sunset"
                    ): SCHEDULE_SOURCE_SELECTOR,
                    vol.Optional(
                        "night_start_time", default="20:00:00"
                    ): selector.TimeSelector(),
                    vol.Optional(
                        "night_start_offset_seconds", default=0
                    ): _number_selector(0, minimum=-86400),
                    vol.Optional(
                        "night_end_source", default="sunrise"
                    ): SCHEDULE_SOURCE_SELECTOR,
                    vol.Optional(
                        "night_end_time", default="06:00:00"
                    ): selector.TimeSelector(),
                    vol.Optional(
                        "night_end_offset_seconds", default=0
                    ): _number_selector(0, minimum=-86400),
                    vol.Optional("night_delay_seconds", default=0): _number_selector(0),
                    vol.Optional(
                        "night_service_data_on", default={}
                    ): selector.ObjectSelector(),
                    vol.Optional(
                        "night_service_data_off", default={}
                    ): selector.ObjectSelector(),
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("stay"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional(
                        "enabled_default", default=True
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "stay_mode_default", default=False
                    ): selector.BooleanSelector(),
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("actions"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional("service_data_on", default={}): selector.ObjectSelector(),
                    vol.Optional("service_data_off", default={}): selector.ObjectSelector(),
                    vol.Optional("on_enter_idle", default="off"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_idle", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_enter_active", default="on"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_active", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_enter_overridden", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_overridden", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_enter_constrained", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_constrained", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_enter_blocked", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_blocked", default="ignore"): BEHAVIOR_SELECTOR,
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("advanced"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional("trigger_on_states", default="on"): selector.TextSelector(),
                    vol.Optional("trigger_off_states", default="off"): selector.TextSelector(),
                    vol.Optional("state_on_states", default="on"): selector.TextSelector(),
                    vol.Optional("state_off_states", default="off"): selector.TextSelector(),
                    vol.Optional("override_on_states", default="on"): selector.TextSelector(),
                    vol.Optional("override_off_states", default="off"): selector.TextSelector(),
                    vol.Optional("state_attributes_ignore", default=""): selector.TextSelector(),
                }
            ),
            {"collapsed": True},
        ),
    }
)

_SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "identity": ("name", "icon"),
    "triggers": ("trigger_entities", "sensor_type", "sensor_resets_timer"),
    "targets": ("control_entities", "state_entities"),
    "timer": (
        "delay_seconds",
        "backoff_enabled",
        "backoff_factor",
        "backoff_max_seconds",
    ),
    "blocking": ("blocking_enabled", "block_timeout_seconds"),
    "rules": ("override_entities", "interlock_entities"),
    "constraints": (
        "constraint_enabled",
        "constraint_start_source",
        "constraint_start_time",
        "constraint_start_offset_seconds",
        "constraint_end_source",
        "constraint_end_time",
        "constraint_end_offset_seconds",
    ),
    "night": (
        "night_mode_enabled",
        "night_start_source",
        "night_start_time",
        "night_start_offset_seconds",
        "night_end_source",
        "night_end_time",
        "night_end_offset_seconds",
        "night_delay_seconds",
        "night_service_data_on",
        "night_service_data_off",
    ),
    "stay": ("enabled_default", "stay_mode_default"),
    "actions": (
        "service_data_on",
        "service_data_off",
        "on_enter_idle",
        "on_exit_idle",
        "on_enter_active",
        "on_exit_active",
        "on_enter_overridden",
        "on_exit_overridden",
        "on_enter_constrained",
        "on_exit_constrained",
        "on_enter_blocked",
        "on_exit_blocked",
    ),
    "advanced": (
        "trigger_on_states",
        "trigger_off_states",
        "state_on_states",
        "state_off_states",
        "override_on_states",
        "override_off_states",
        "state_attributes_ignore",
    ),
}


def controller_form_values(stored_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expand normalized subentry data back into native UI sections."""

    flat = dict(stored_data)
    constraint = flat.pop("constraint_window", None)
    flat["constraint_enabled"] = constraint is not None
    if constraint:
        for boundary in ("start", "end"):
            point = dict(constraint[boundary])
            for key, value in point.items():
                flat[f"constraint_{boundary}_{key}"] = value

    night = flat.pop("night_mode", None)
    flat["night_mode_enabled"] = night is not None
    if night:
        night = dict(night)
        for boundary in ("start", "end"):
            point = dict(night.pop(boundary))
            for key, value in point.items():
                flat[f"night_{boundary}_{key}"] = value
        flat["night_delay_seconds"] = night.pop("delay_seconds", None) or 0
        flat["night_service_data_on"] = dict(
            night.pop("service_data_on", {}) or {}
        )
        flat["night_service_data_off"] = dict(
            night.pop("service_data_off", {}) or {}
        )

    flat.update(dict(flat.pop("transition_behaviors", {}) or {}))
    for key in _SECTION_FIELDS["advanced"]:
        if key in flat and not isinstance(flat[key], str):
            flat[key] = ", ".join(str(value) for value in flat[key])
    return {
        section: {key: flat[key] for key in keys if key in flat}
        for section, keys in _SECTION_FIELDS.items()
    }


def normalize_controller_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize controller flow input into v10 subentry data."""

    data = _flatten_sections(user_input)
    constraint_window = None
    if data.get("constraint_enabled", False):
        constraint_window = {
            "start": _schedule_point(data, "constraint_start"),
            "end": _schedule_point(data, "constraint_end"),
        }
    night_mode = None
    if data.get("night_mode_enabled", False):
        night_mode = {
            "start": _schedule_point(data, "night_start"),
            "end": _schedule_point(data, "night_end"),
            "delay_seconds": (
                float(data["night_delay_seconds"])
                if float(data.get("night_delay_seconds", 0)) > 0
                else None
            ),
            "service_data_on": dict(data.get("night_service_data_on") or {}),
            "service_data_off": dict(data.get("night_service_data_off") or {}),
        }
    transition_behaviors = {
        key: value.value for key, value in DEFAULT_TRANSITION_BEHAVIORS.items()
    }
    transition_behaviors.update({
        key: data[key]
        for key in (
            "on_enter_idle",
            "on_exit_idle",
            "on_enter_active",
            "on_exit_active",
            "on_enter_overridden",
            "on_exit_overridden",
            "on_enter_constrained",
            "on_exit_constrained",
            "on_enter_blocked",
            "on_exit_blocked",
        )
        if key in data
    })
    timeout = float(data.get("block_timeout_seconds", 0) or 0)
    return {
        "name": str(data["name"]),
        "icon": data.get("icon") or None,
        "trigger_entities": _as_tuple(data.get("trigger_entities")),
        "control_entities": _as_tuple(data.get("control_entities")),
        "state_entities": _as_tuple(data.get("state_entities")),
        "override_entities": _as_tuple(data.get("override_entities")),
        "interlock_entities": _as_tuple(data.get("interlock_entities")),
        "sensor_type": data.get("sensor_type", "event"),
        "sensor_resets_timer": bool(data.get("sensor_resets_timer", False)),
        "delay_seconds": float(data.get("delay_seconds", DEFAULT_DELAY_SECONDS)),
        "blocking_enabled": bool(data.get("blocking_enabled", True)),
        "block_timeout_seconds": timeout or None,
        "enabled_default": bool(data.get("enabled_default", True)),
        "stay_mode_default": bool(data.get("stay_mode_default", False)),
        "backoff_enabled": bool(data.get("backoff_enabled", False)),
        "backoff_factor": float(data.get("backoff_factor", 1.1)),
        "backoff_max_seconds": float(data.get("backoff_max_seconds", 300)),
        "constraint_window": constraint_window,
        "night_mode": night_mode,
        "service_data_on": dict(data.get("service_data_on") or {}),
        "service_data_off": dict(data.get("service_data_off") or {}),
        "transition_behaviors": transition_behaviors,
        "trigger_on_states": _state_tuple(data.get("trigger_on_states"), ("on",)),
        "trigger_off_states": _state_tuple(data.get("trigger_off_states"), ("off",)),
        "state_on_states": _state_tuple(data.get("state_on_states"), ("on",)),
        "state_off_states": _state_tuple(data.get("state_off_states"), ("off",)),
        "override_on_states": _state_tuple(
            data.get("override_on_states"), ("on",)
        ),
        "override_off_states": _state_tuple(
            data.get("override_off_states"), ("off",)
        ),
        "state_attributes_ignore": _as_tuple(data.get("state_attributes_ignore")),
    }


class EntityControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the root Entity Controller config flow."""

    VERSION = 10

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> config_entries.OptionsFlow:
        """Open a controller form from the integration settings action."""

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
                    schema, controller_form_values(dict(subentry.data))
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
    """Add a controller from the Entity Controller integration settings."""

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

"""Config entry flow for individual Entity Controller devices."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_DELAY_SECONDS, DOMAIN
from .entry_migration import fresh_controller_data
from .lifecycle import normalize_lifecycle_actions
from .model import DEFAULT_TRANSITION_BEHAVIORS, normalize_transition_behaviors


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
            "basic",
            "identity",
            "triggers",
            "targets",
            "timer",
            "monitoring",
            "blocking",
            "rules",
            "constraints",
            "night",
            "initial_state",
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


def _seconds(value: Any) -> float:
    """Accept native duration-selector data while storing seconds."""

    if isinstance(value, dict):
        return timedelta(
            days=int(value.get("days", 0)),
            hours=int(value.get("hours", 0)),
            minutes=int(value.get("minutes", 0)),
            seconds=int(value.get("seconds", 0)),
        ).total_seconds()
    return float(value)


def _duration(seconds: float) -> dict[str, int]:
    """Convert persisted seconds to native duration-selector data."""

    whole_seconds = max(0, round(seconds))
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return {"hours": hours, "minutes": minutes, "seconds": seconds}


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
    selector.SelectSelectorConfig(
        options=["fixed", "sunrise", "sunset"],
        translation_key="schedule_source",
    )
)
BEHAVIOR_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=["on", "off", "ignore", "custom", "restore"], translation_key="transition_behavior"
    )
)
SENSOR_TYPE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=["event", "duration"], translation_key="sensor_type"
    )
)
DURATION_SELECTOR = selector.DurationSelector(
    selector.DurationSelectorConfig(enable_day=False)
)


CONTROLLER_SCHEMA = vol.Schema(
    {
        vol.Required("basic"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Required("name"): selector.TextSelector(),
                    vol.Optional("icon"): selector.IconSelector(),
                    vol.Required("trigger_entities"): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional("presence_entities", default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Required("control_entities"): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(
                        "delay_seconds", default=_duration(DEFAULT_DELAY_SECONDS)
                    ): DURATION_SELECTOR,
                }
            )
        ),
        vol.Required("timer"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional("sensor_type", default="event"): SENSOR_TYPE_SELECTOR,
                    vol.Optional(
                        "sensor_resets_timer", default=False
                    ): selector.BooleanSelector(),
                    vol.Optional("backoff_enabled", default=False): selector.BooleanSelector(),
                    vol.Optional("backoff_factor", default=1.1): _number_selector(
                        1.1, minimum=1
                    ),
                    vol.Optional(
                        "backoff_max_seconds", default=_duration(300)
                    ): DURATION_SELECTOR,
                }
            ),
            {"collapsed": True},
        ),
        vol.Required("monitoring"): data_entry_flow.section(
            vol.Schema(
                {
                    vol.Optional("state_entities", default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(
                        "blocking_enabled", default=True
                    ): selector.BooleanSelector(),
                    vol.Optional("protect_manual_off", default=True): selector.BooleanSelector(),
                    vol.Optional("protect_manual_on", default=True): selector.BooleanSelector(),
                    vol.Optional(
                        "block_timeout_seconds", default=_duration(0)
                    ): DURATION_SELECTOR,
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
                    vol.Optional(
                        "night_delay_seconds", default=_duration(0)
                    ): DURATION_SELECTOR,
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
        vol.Required("initial_state"): data_entry_flow.section(
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
                    vol.Optional("lifecycle_actions", default={}): selector.ObjectSelector(),
                    vol.Optional("on_enter_idle", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_idle", default="ignore"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_enter_active", default="on"): BEHAVIOR_SELECTOR,
                    vol.Optional("on_exit_active", default="off"): BEHAVIOR_SELECTOR,
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
                    vol.Optional("presence_on_states", default="on"): selector.TextSelector(),
                    vol.Optional("presence_off_states", default="off"): selector.TextSelector(),
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
    "basic": (
        "name",
        "icon",
        "trigger_entities",
        "presence_entities",
        "control_entities",
        "delay_seconds",
    ),
    "timer": (
        "sensor_type",
        "sensor_resets_timer",
        "backoff_enabled",
        "backoff_factor",
        "backoff_max_seconds",
    ),
    "monitoring": (
        "state_entities",
        "blocking_enabled",
        "protect_manual_off",
        "protect_manual_on",
        "block_timeout_seconds",
    ),
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
    "initial_state": ("enabled_default", "stay_mode_default"),
    "actions": (
        "service_data_on",
        "service_data_off",
        "lifecycle_actions",
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
        "presence_on_states",
        "presence_off_states",
        "state_on_states",
        "state_off_states",
        "override_on_states",
        "override_off_states",
        "state_attributes_ignore",
    ),
}

_RECONFIGURE_SCHEMA_DATA = dict(CONTROLLER_SCHEMA.schema)
for _key in tuple(_RECONFIGURE_SCHEMA_DATA):
    if getattr(_key, "schema", _key) == "initial_state":
        del _RECONFIGURE_SCHEMA_DATA[_key]
CONTROLLER_RECONFIGURE_SCHEMA = vol.Schema(_RECONFIGURE_SCHEMA_DATA)


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

    flat.update({
        key: behavior.value
        for key, behavior in normalize_transition_behaviors(flat.pop("transition_behaviors", {})).items()
    })
    for key in (
        "delay_seconds",
        "backoff_max_seconds",
        "block_timeout_seconds",
        "night_delay_seconds",
    ):
        if key in flat:
            # HA's DurationSelector requires a mapping even when the stored
            # optional timeout is disabled (persisted as None).
            flat[key] = _duration(float(flat[key] or 0))
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
                _seconds(data["night_delay_seconds"])
                if _seconds(data.get("night_delay_seconds", 0)) > 0
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
    transition_behaviors = {
        key: behavior.value
        for key, behavior in normalize_transition_behaviors(transition_behaviors).items()
    }
    timeout = _seconds(data.get("block_timeout_seconds", 0) or 0)
    return {
        "name": str(data["name"]),
        "icon": data.get("icon") or None,
        "trigger_entities": _as_tuple(data.get("trigger_entities")),
        "presence_entities": _as_tuple(data.get("presence_entities")),
        "control_entities": _as_tuple(data.get("control_entities")),
        "state_entities": _as_tuple(data.get("state_entities")),
        "override_entities": _as_tuple(data.get("override_entities")),
        "interlock_entities": _as_tuple(data.get("interlock_entities")),
        "sensor_type": data.get("sensor_type", "event"),
        "sensor_resets_timer": bool(data.get("sensor_resets_timer", False)),
        "delay_seconds": _seconds(data.get("delay_seconds", DEFAULT_DELAY_SECONDS)),
        "blocking_enabled": bool(data.get("blocking_enabled", True)),
        "protect_manual_off": bool(data.get("protect_manual_off", True)),
        "protect_manual_on": bool(data.get("protect_manual_on", True)),
        "block_timeout_seconds": timeout or None,
        "enabled_default": bool(data.get("enabled_default", True)),
        "stay_mode_default": bool(data.get("stay_mode_default", False)),
        "backoff_enabled": bool(data.get("backoff_enabled", False)),
        "backoff_factor": float(data.get("backoff_factor", 1.1)),
        "backoff_max_seconds": _seconds(data.get("backoff_max_seconds", 300)),
        "constraint_window": constraint_window,
        "night_mode": night_mode,
        "service_data_on": dict(data.get("service_data_on") or {}),
        "service_data_off": dict(data.get("service_data_off") or {}),
        "lifecycle_actions": normalize_lifecycle_actions(data.get("lifecycle_actions") or {}),
        "transition_behaviors": transition_behaviors,
        "trigger_on_states": _state_tuple(data.get("trigger_on_states"), ("on",)),
        "trigger_off_states": _state_tuple(data.get("trigger_off_states"), ("off",)),
        "presence_on_states": _state_tuple(data.get("presence_on_states"), ("on",)),
        "presence_off_states": _state_tuple(data.get("presence_off_states"), ("off",)),
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
    """Create one controller device config entry per flow."""

    VERSION = 11

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> config_entries.OptionsFlow:
        """Open the options for this controller device."""

        return ControllerOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create one named controller entry directly from the integration page."""

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=CONTROLLER_SCHEMA,
                errors={},
            )
        controller_id = uuid4().hex
        data = fresh_controller_data(
            normalize_controller_user_input(user_input), controller_id=controller_id
        )
        return self.async_create_entry(title=data["name"], data=data)

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Import one controller from the legacy YAML configuration."""

        controller_id = import_config["controller_id"]
        await self.async_set_unique_id(f"legacy-yaml:{controller_id}")
        self._abort_if_unique_id_configured()
        data = fresh_controller_data(
            {key: value for key, value in import_config.items() if key != "controller_id"},
            controller_id=controller_id,
        )
        return self.async_create_entry(title=data["name"], data=data)


class ControllerOptionsFlow(config_entries.OptionsFlow):
    """Edit the controller represented by this config entry."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Show this controller's editable settings."""

        if user_input is None:
            schema = self.add_suggested_values_to_schema(
                CONTROLLER_RECONFIGURE_SCHEMA,
                controller_form_values(dict(self.config_entry.data)),
            )
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
                errors={},
            )
        data = normalize_controller_user_input(user_input)
        current_data = dict(self.config_entry.data)
        for key in ("enabled", "stay_mode", "_ec_controller_id", "_ec_entity_unique_id_prefix"):
            if key in current_data:
                data[key] = current_data[key]
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=data,
            title=data["name"],
        )
        return self.async_create_entry(title="", data={})

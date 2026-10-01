"""Legacy v9 YAML migration helpers for Entity Controller v10."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class ImportedController:
    """One migrated v9 controller as v10 config-entry data."""

    controller_id: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MigrationWarning:
    """A non-fatal legacy migration warning."""

    controller_id: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """Result of converting legacy YAML into v10 controller-entry data."""

    imported: list[ImportedController] = field(default_factory=list)
    warnings: list[MigrationWarning] = field(default_factory=list)
    skipped_existing: set[str] = field(default_factory=set)
    legacy_entity_map: dict[str, str] = field(default_factory=dict)
    external_helper_references: set[str] = field(default_factory=set)
    created_helper_entities: set[str] = field(default_factory=set)
    cleanup_guidance: tuple[str, ...] = ()


_KNOWN_FIELDS = {
    "sensor",
    "sensors",
    "entity",
    "entities",
    "state_entities",
    "override",
    "overrides",
    "interlock",
    "interlocks",
    "delay",
    "sensor_type",
    "sensor_type_duration",
    "sensor_states_on",
    "sensor_states_off",
    "state_states_on",
    "state_states_off",
    "override_states_on",
    "override_states_off",
    "state_strings_on",
    "state_strings_off",
    "state_attributes_ignore",
    "start_time",
    "end_time",
    "sensor_resets_timer",
    "block_timeout",
    "disable_block",
    "backoff",
    "backoff_factor",
    "backoff_max",
    "night_mode",
    "stay",
    "stay_mode",
    "behaviours",
    "behaviors",
    "service_data",
    "service_data_off",
}
_HELPER_PREFIXES = ("input_boolean.", "input_select.", "input_number.", "switch.")
_LEGACY_DEFAULT_ON = ("on", "playing", "home", "True")
_LEGACY_DEFAULT_OFF = ("off", "idle", "paused", "away", "False")
_SUN_PATTERN = re.compile(
    r"^(sunrise|sunset)(?:\s*([+-])\s*(\d{1,2}):(\d{2}):(\d{2}))?$",
    re.IGNORECASE,
)


def parse_legacy_yaml(content: str) -> dict[str, Any]:
    """Parse legacy EC YAML into a mapping."""

    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError as err:
        raise ValueError(f"Invalid YAML syntax: {err}") from err
    if not isinstance(parsed, dict):
        raise ValueError("Legacy Entity Controller YAML must be a mapping")
    return parsed


def migrate_legacy_yaml(
    legacy_config: dict[str, Any],
    *,
    existing_controller_ids: set[str] | None = None,
) -> MigrationReport:
    """Convert legacy v9 controller YAML into v10 controller-entry data."""

    existing = existing_controller_ids or set()
    imported: list[ImportedController] = []
    warnings: list[MigrationWarning] = []
    skipped_existing: set[str] = set()
    legacy_entity_map: dict[str, str] = {}
    external_helpers: set[str] = set()

    for controller_id, raw in legacy_config.items():
        if controller_id in existing:
            skipped_existing.add(controller_id)
            continue
        if not isinstance(raw, dict):
            warnings.append(
                MigrationWarning(controller_id, "<controller>", "Controller config is not a mapping")
            )
            continue

        try:
            unknown_fields = sorted(set(raw) - _KNOWN_FIELDS)
            override_entities = _entity_aliases(raw, "override", "overrides")
            interlock_entities = _entity_aliases(raw, "interlock", "interlocks")
            day_service_data_on = _service_data(raw.get("service_data"))
            day_service_data_off = _service_data(raw.get("service_data_off"))
            extra_on_states = _entities(raw.get("state_strings_on"))
            extra_off_states = _entities(raw.get("state_strings_off"))
            data: dict[str, Any] = {
                "name": _title_from_id(controller_id),
                "trigger_entities": _entity_aliases(raw, "sensor", "sensors"),
                "control_entities": _entity_aliases(raw, "entity", "entities"),
                "state_entities": _entities(raw.get("state_entities")),
                "override_entities": override_entities,
                "interlock_entities": interlock_entities,
                "sensor_type": raw.get(
                    "sensor_type",
                    "duration" if raw.get("sensor_type_duration", False) else "event",
                ),
                "delay_seconds": float(raw.get("delay", 180.0)),
                "sensor_resets_timer": bool(raw.get("sensor_resets_timer", False)),
                "block_timeout_seconds": _optional_float(raw.get("block_timeout")),
                "blocking_enabled": not bool(raw.get("disable_block", False)),
                "stay_mode_default": bool(raw.get("stay", raw.get("stay_mode", False))),
                "backoff_enabled": bool(raw.get("backoff", False)),
                "backoff_factor": float(raw.get("backoff_factor", 1.1)),
                "backoff_max_seconds": float(raw.get("backoff_max", 300.0)),
                "service_data_on": day_service_data_on,
                "service_data_off": day_service_data_off,
                "state_attributes_ignore": _entities(raw.get("state_attributes_ignore")),
                "trigger_on_states": _state_values(
                    raw.get("sensor_states_on", _LEGACY_DEFAULT_ON), extra_on_states
                ),
                "trigger_off_states": _state_values(
                    raw.get("sensor_states_off", _LEGACY_DEFAULT_OFF), extra_off_states
                ),
                "state_on_states": _state_values(
                    raw.get("state_states_on", _LEGACY_DEFAULT_ON), extra_on_states
                ),
                "state_off_states": _state_values(
                    raw.get("state_states_off", _LEGACY_DEFAULT_OFF), extra_off_states
                ),
                "override_on_states": _state_values(
                    raw.get("override_states_on", _LEGACY_DEFAULT_ON), extra_on_states
                ),
                "override_off_states": _state_values(
                    raw.get("override_states_off", _LEGACY_DEFAULT_OFF), extra_off_states
                ),
            }
            if "start_time" in raw or "end_time" in raw:
                if raw.get("start_time") is not None and raw.get("end_time") is not None:
                    data["constraint_window"] = {
                        "start": _convert_schedule_point(raw["start_time"]),
                        "end": _convert_schedule_point(raw["end_time"]),
                    }
                else:
                    unknown_fields.extend(
                        field_name
                        for field_name in ("start_time", "end_time")
                        if field_name in raw
                    )
            if raw.get("night_mode") is not None:
                data["night_mode"] = _convert_night_mode(
                    raw["night_mode"],
                    fallback_service_data_on=day_service_data_on,
                    fallback_service_data_off=day_service_data_off,
                )
            behaviours = raw.get("behaviours", raw.get("behaviors"))
            if behaviours:
                data["transition_behaviors"] = dict(behaviours)
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            warnings.append(
                MigrationWarning(
                    controller_id,
                    "<controller>",
                    f"Controller config is malformed: {err}",
                )
            )
            continue

        warnings.extend(
            MigrationWarning(controller_id, field_name, "Unsupported legacy field")
            for field_name in unknown_fields
        )
        for field_name in ("state_strings_on", "state_strings_off"):
            if field_name in raw:
                warnings.append(
                    MigrationWarning(
                        controller_id,
                        field_name,
                        "Partially unsupported: v10 has no control-state mapping.",
                    )
                )
        external_helpers.update(
            entity
            for entity in (*override_entities, *interlock_entities)
            if entity.startswith(_HELPER_PREFIXES)
        )
        imported.append(ImportedController(controller_id, data))
        legacy_entity_map[f"entity_controller.{controller_id}"] = (
            f"sensor.{controller_id}_state"
        )

    return MigrationReport(
        imported=imported,
        warnings=warnings,
        skipped_existing=skipped_existing,
        legacy_entity_map=legacy_entity_map,
        external_helper_references=external_helpers,
        created_helper_entities=set(),
        cleanup_guidance=(
            "After validating migrated controllers, remove the legacy entity_controller YAML include manually.",
        ),
    )


def _entities(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise TypeError("Entity values must be a string or a list of strings")
    if not all(isinstance(entity_id, str) for entity_id in value):
        raise TypeError("Entity values must contain only strings")
    return tuple(value)


def _entity_aliases(
    config: Mapping[str, Any], singular: str, plural: str
) -> tuple[str, ...]:
    """Merge v9 additive singular/plural entity fields in source order."""

    return tuple(
        dict.fromkeys((*_entities(config.get(singular)), *_entities(config.get(plural))))
    )


def _state_values(value: Any, extra_values: tuple[str, ...]) -> tuple[str, ...]:
    """Merge a legacy state list with additional global state strings."""

    return tuple(dict.fromkeys((*_entities(value), *extra_values)))


def _service_data(value: Any) -> dict[str, Any]:
    """Normalize an optional legacy service-data mapping."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("Service data must be a mapping")
    return dict(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _title_from_id(value: str) -> str:
    return value.replace("_", " ").title()


def _convert_night_mode(
    value: dict[str, Any],
    *,
    fallback_service_data_on: dict[str, Any],
    fallback_service_data_off: dict[str, Any],
) -> dict[str, Any]:
    """Convert the old night profile while retaining its fallback behavior."""

    return {
        "start": _convert_schedule_point(value["start_time"]),
        "end": _convert_schedule_point(value["end_time"]),
        "delay_seconds": _optional_float(value.get("delay")),
        "service_data_on": _service_data(
            value.get("service_data", fallback_service_data_on)
        ),
        "service_data_off": _service_data(
            value.get("service_data_off", fallback_service_data_off)
        ),
    }


def _convert_schedule_point(value: str) -> dict[str, Any]:
    normalized = value.strip().lower()
    match = _SUN_PATTERN.fullmatch(normalized)
    if match:
        source, sign, hours, minutes, seconds = match.groups()
        offset = 0
        if hours is not None:
            offset = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            if sign == "-":
                offset = -offset
        return {"source": source, "offset_seconds": offset}
    return {"source": "fixed", "time": normalized, "offset_seconds": 0}

"""Legacy v9 YAML migration helpers for Entity Controller v10."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class ImportedController:
    """One migrated v9 controller as v10 subentry data."""

    subentry_id: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MigrationWarning:
    """A non-fatal legacy migration warning."""

    controller_id: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """Result of converting legacy YAML into v10 subentry data."""

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
_SUN_PATTERN = re.compile(
    r"^(sunrise|sunset)(?:\s*([+-])\s*(\d{1,2}):(\d{2}):(\d{2}))?$",
    re.IGNORECASE,
)


def parse_legacy_yaml(content: str) -> dict[str, Any]:
    """Parse legacy EC YAML into a mapping."""

    parsed = yaml.safe_load(content) or {}
    if not isinstance(parsed, dict):
        raise ValueError("Legacy Entity Controller YAML must be a mapping")
    return parsed


def migrate_legacy_yaml(
    legacy_config: dict[str, Any],
    *,
    existing_subentry_ids: set[str] | None = None,
) -> MigrationReport:
    """Convert legacy v9 controller YAML into v10 subentry data."""

    existing = existing_subentry_ids or set()
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

        unknown_fields = sorted(set(raw) - _KNOWN_FIELDS)
        warnings.extend(
            MigrationWarning(controller_id, field_name, "Unsupported legacy field")
            for field_name in unknown_fields
        )

        override_entities = _entities(raw.get("override", raw.get("overrides")))
        interlock_entities = _entities(raw.get("interlock", raw.get("interlocks")))
        external_helpers.update(
            entity
            for entity in (*override_entities, *interlock_entities)
            if entity.startswith(_HELPER_PREFIXES)
        )

        data: dict[str, Any] = {
            "name": _title_from_id(controller_id),
            "trigger_entities": _entities(raw.get("sensor", raw.get("sensors"))),
            "control_entities": _entities(raw.get("entity", raw.get("entities"))),
            "state_entities": _entities(raw.get("state_entities")),
            "override_entities": override_entities,
            "interlock_entities": interlock_entities,
            "sensor_type": raw.get("sensor_type", "event"),
            "delay_seconds": float(raw.get("delay", 180.0)),
            "sensor_resets_timer": bool(raw.get("sensor_resets_timer", False)),
            "block_timeout_seconds": _optional_float(raw.get("block_timeout")),
            "blocking_enabled": not bool(raw.get("disable_block", False)),
            "stay_mode_default": bool(raw.get("stay", raw.get("stay_mode", False))),
            "backoff_enabled": bool(raw.get("backoff", False)),
            "backoff_factor": float(raw.get("backoff_factor", 1.1)),
            "backoff_max_seconds": float(raw.get("backoff_max", 300.0)),
        }

        if night_mode := raw.get("night_mode"):
            data["night_mode"] = _convert_night_mode(night_mode)
        if behaviours := raw.get("behaviours", raw.get("behaviors")):
            data["transition_behaviors"] = dict(behaviours)

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
    return tuple(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _title_from_id(value: str) -> str:
    return value.replace("_", " ").title()


def _convert_night_mode(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "start": _convert_schedule_point(value["start_time"]),
        "end": _convert_schedule_point(value["end_time"]),
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

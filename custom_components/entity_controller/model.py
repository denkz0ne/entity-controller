"""Typed runtime models for Entity Controller v10."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class ControllerState(StrEnum):
    """Runtime states exposed by the v10 controller FSM."""

    IDLE = "idle"
    ACTIVE_TIMER = "active_timer"
    ACTIVE_STAY_ON = "active_stay_on"
    BLOCKED = "blocked"
    OVERRIDDEN = "overridden"
    CONSTRAINED = "constrained"
    DISABLED = "disabled"


class SensorType(StrEnum):
    """How a trigger entity is interpreted."""

    EVENT = "event"
    DURATION = "duration"


class TransitionCause(StrEnum):
    """Reason recorded for a controller state transition."""

    SENSOR_TRIGGER = "sensor_trigger"
    SENSOR_RELEASE = "sensor_release"
    TIMER_EXPIRED = "timer_expired"
    MANUAL_CONTROL = "manual_control"
    OVERRIDE = "override"
    CONSTRAINT = "constraint"
    STAY_MODE = "stay_mode"
    SERVICE = "service"
    CONFIGURATION = "configuration"


class TransitionBehavior(StrEnum):
    """Simple action performed on a state transition."""

    ON = "on"
    OFF = "off"
    IGNORE = "ignore"
    CUSTOM = "custom"
    RESTORE = "restore"


class ReconcileReason(StrEnum):
    """Why runtime state is being reconciled without transition side effects."""

    STARTUP = "startup"
    RESTORE = "restore"
    MIGRATION = "migration"
    RECONFIGURE = "reconfigure"
    ENABLED = "enabled"
    CLEAR_BLOCK = "clear_block"


DEFAULT_TRANSITION_BEHAVIORS: Mapping[str, TransitionBehavior] = MappingProxyType(
    {
        "on_enter_idle": TransitionBehavior.IGNORE,
        "on_exit_idle": TransitionBehavior.IGNORE,
        "on_enter_active": TransitionBehavior.ON,
        "on_exit_active": TransitionBehavior.OFF,
        "on_enter_overridden": TransitionBehavior.IGNORE,
        "on_exit_overridden": TransitionBehavior.IGNORE,
        "on_enter_constrained": TransitionBehavior.IGNORE,
        "on_exit_constrained": TransitionBehavior.IGNORE,
        "on_enter_blocked": TransitionBehavior.IGNORE,
        "on_exit_blocked": TransitionBehavior.IGNORE,
    }
)


def normalize_transition_behaviors(
    values: Mapping[str, str | TransitionBehavior] | None = None,
) -> dict[str, TransitionBehavior]:
    """Move only the legacy default shutdown pair to the activity exit hook.

    Explicit advanced idle or active-exit policies keep their original meaning.
    The conversion is idempotent and never modifies the caller's stored mapping.
    """

    legacy = dict(values or {})
    result = dict(DEFAULT_TRANSITION_BEHAVIORS)
    result.update({key: TransitionBehavior(value) for key, value in legacy.items()})
    if (
        legacy.get("on_enter_idle", TransitionBehavior.OFF) == TransitionBehavior.OFF
        and legacy.get("on_exit_active", TransitionBehavior.IGNORE)
        == TransitionBehavior.IGNORE
    ):
        result["on_enter_idle"] = TransitionBehavior.IGNORE
        result["on_exit_active"] = TransitionBehavior.OFF
    return result


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Normalized configuration for one controller runtime."""

    subentry_id: str
    name: str
    entity_unique_id_prefix: str | None = None
    icon: str | None = None
    trigger_entities: tuple[str, ...] = ()
    presence_entities: tuple[str, ...] = ()
    control_entities: tuple[str, ...] = ()
    state_entities: tuple[str, ...] = ()
    override_entities: tuple[str, ...] = ()
    interlock_entities: tuple[str, ...] = ()
    sensor_type: SensorType = SensorType.EVENT
    delay_seconds: float = 180.0
    sensor_resets_timer: bool = False
    blocking_enabled: bool = True
    protect_manual_off: bool = True
    protect_manual_on: bool = True
    block_timeout_seconds: float | None = None
    enabled_default: bool = True
    stay_mode_default: bool = False
    backoff_enabled: bool = False
    backoff_factor: float = 1.1
    backoff_max_seconds: float = 300.0
    constraint_window: Mapping[str, object] | None = None
    night_mode: Mapping[str, object] | None = None
    service_data_on: Mapping[str, object] = field(default_factory=dict)
    service_data_off: Mapping[str, object] = field(default_factory=dict)
    lifecycle_actions: Mapping[str, list[dict[str, object]]] = field(default_factory=dict)
    trigger_on_states: tuple[str, ...] = ("on",)
    trigger_off_states: tuple[str, ...] = ("off",)
    presence_on_states: tuple[str, ...] = ("on",)
    presence_off_states: tuple[str, ...] = ("off",)
    state_on_states: tuple[str, ...] = ("on",)
    state_off_states: tuple[str, ...] = ("off",)
    override_on_states: tuple[str, ...] = ("on",)
    override_off_states: tuple[str, ...] = ("off",)
    state_attributes_ignore: tuple[str, ...] = ()
    transition_behaviors: Mapping[str, TransitionBehavior] = field(
        default_factory=lambda: MappingProxyType(dict(DEFAULT_TRANSITION_BEHAVIORS))
    )

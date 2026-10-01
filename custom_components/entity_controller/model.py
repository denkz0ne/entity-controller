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
        "on_enter_idle": TransitionBehavior.OFF,
        "on_exit_idle": TransitionBehavior.IGNORE,
        "on_enter_active": TransitionBehavior.ON,
        "on_exit_active": TransitionBehavior.IGNORE,
        "on_enter_overridden": TransitionBehavior.IGNORE,
        "on_exit_overridden": TransitionBehavior.IGNORE,
        "on_enter_constrained": TransitionBehavior.IGNORE,
        "on_exit_constrained": TransitionBehavior.IGNORE,
        "on_enter_blocked": TransitionBehavior.IGNORE,
        "on_exit_blocked": TransitionBehavior.IGNORE,
    }
)


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Normalized configuration for one controller runtime."""

    subentry_id: str
    name: str
    entity_unique_id_prefix: str | None = None
    icon: str | None = None
    trigger_entities: tuple[str, ...] = ()
    control_entities: tuple[str, ...] = ()
    state_entities: tuple[str, ...] = ()
    override_entities: tuple[str, ...] = ()
    interlock_entities: tuple[str, ...] = ()
    sensor_type: SensorType = SensorType.EVENT
    delay_seconds: float = 180.0
    sensor_resets_timer: bool = False
    blocking_enabled: bool = True
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
    trigger_on_states: tuple[str, ...] = ("on",)
    trigger_off_states: tuple[str, ...] = ("off",)
    state_on_states: tuple[str, ...] = ("on",)
    state_off_states: tuple[str, ...] = ("off",)
    override_on_states: tuple[str, ...] = ("on",)
    override_off_states: tuple[str, ...] = ("off",)
    state_attributes_ignore: tuple[str, ...] = ()
    transition_behaviors: Mapping[str, TransitionBehavior] = field(
        default_factory=lambda: MappingProxyType(dict(DEFAULT_TRANSITION_BEHAVIORS))
    )

"""Sensor platform for Entity Controller v10."""

from __future__ import annotations

from .controller import ControllerRuntime
from .entity import EntityControllerEntity


class EntityControllerStateSensor(EntityControllerEntity):
    """Expose the exact controller FSM state."""

    def __init__(
        self,
        runtime: ControllerRuntime,
        entry_id: str,
        *,
        diagnostic_key: str | None = None,
    ) -> None:
        super().__init__(
            runtime,
            entry_id,
            diagnostic_key or "state",
            enabled_default=diagnostic_key is None,
        )
        self.diagnostic_key = diagnostic_key

    @property
    def native_value(self) -> str:
        """Return the runtime FSM state value."""

        if self.diagnostic_key == "last_trigger":
            return "" if self.runtime.last_triggered_at is None else self.runtime.last_triggered_at.isoformat()
        return self.runtime.state.value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return useful runtime metadata without per-second countdown churn."""

        return {
            "last_transition": self.runtime.last_transition_at,
            "transition_cause": None
            if self.runtime.last_transition_cause is None
            else self.runtime.last_transition_cause.value,
            "last_triggered_by": self.runtime.last_triggered_by,
            "last_triggered_at": self.runtime.last_triggered_at,
            "effective_delay": self.runtime.effective_delay_seconds,
            "expires_at": self.runtime.expires_at,
            "blocked_by": self.runtime.blocked_by,
            "overridden_by": self.runtime.overridden_by,
        }


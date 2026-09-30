"""Binary sensor platform for Entity Controller v10."""

from __future__ import annotations

from .entity import EntityControllerEntity
from .model import ControllerState


class EntityControllerBlockedBinarySensor(EntityControllerEntity):
    """Expose whether the controller is currently blocked."""

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "blocked")

    @property
    def is_on(self) -> bool:
        """Return whether the controller is blocked."""

        return self.runtime.state is ControllerState.BLOCKED

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return blocked reason/source metadata."""

        return {
            "reason": None
            if self.runtime.last_transition_cause is None
            else self.runtime.last_transition_cause.value,
            "blocked_by": self.runtime.blocked_by,
            "block_expires_at": None,
        }


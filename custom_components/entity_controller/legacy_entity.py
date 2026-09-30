"""Temporary legacy entity compatibility mirror."""

from __future__ import annotations

from .controller import ControllerRuntime


class LegacyEntityMirror:
    """Mirror the old ``entity_controller.<object_id>`` state during migration."""

    def __init__(self, runtime: ControllerRuntime) -> None:
        self.runtime = runtime
        self.entity_id = f"entity_controller.{runtime.config.subentry_id}"

    @property
    def unique_id(self) -> str:
        """Return stable legacy mirror unique id."""

        return f"legacy_{self.runtime.config.subentry_id}"

    @property
    def state(self) -> str:
        """Return the current runtime state value."""

        return self.runtime.state.value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return migration guidance attributes."""

        subentry_id = self.runtime.config.subentry_id
        return {
            "replacement_entity_id": f"sensor.{subentry_id}_state",
            "migration_note": "Temporary v9 compatibility mirror",
        }

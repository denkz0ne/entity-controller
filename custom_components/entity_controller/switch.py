"""Switch platform for Entity Controller v10."""

from __future__ import annotations

from .entity import EntityControllerEntity
from .model import ControllerState, ReconcileReason


class EntityControllerEnabledSwitch(EntityControllerEntity):
    """Enable or disable EC decisions for one controller."""

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "enabled")

    @property
    def is_on(self) -> bool:
        """Return whether controller decision-making is enabled."""

        return self.runtime.enabled

    async def async_turn_off(self, **kwargs) -> None:
        """Disable EC decisions without turning controlled loads off."""

        self.runtime.enabled = False
        await self.runtime.async_reconcile(ReconcileReason.ENABLED)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable EC decisions and reconcile current reality."""

        self.runtime.enabled = True
        if self.runtime.state is ControllerState.DISABLED:
            await self.runtime.async_reconcile(ReconcileReason.ENABLED)


class EntityControllerStayModeSwitch(EntityControllerEntity):
    """Control runtime stay mode."""

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "stay_mode")

    @property
    def is_on(self) -> bool:
        """Return whether stay mode is active."""

        return self.runtime.stay_mode

    async def async_turn_on(self, **kwargs) -> None:
        """Enable stay mode."""

        self.runtime.stay_mode = True

    async def async_turn_off(self, **kwargs) -> None:
        """Disable stay mode."""

        self.runtime.stay_mode = False


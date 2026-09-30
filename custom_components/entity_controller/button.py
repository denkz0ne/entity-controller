"""Button platform for Entity Controller v10."""

from __future__ import annotations

from .actions import async_activate
from .entity import EntityControllerEntity


class EntityControllerActivateButton(EntityControllerEntity):
    """Activate a controller."""

    def __init__(self, runtime, entry_id: str) -> None:
        super().__init__(runtime, entry_id, "activate")

    async def async_press(self) -> None:
        """Activate the controller."""

        await async_activate(self.runtime)

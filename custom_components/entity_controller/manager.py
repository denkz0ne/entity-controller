"""Root runtime manager for Entity Controller v10."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


class EntityControllerManager:
    """Own controller runtimes for one Entity Controller config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
        self.hass = hass
        self.entry = entry
        self.controllers: dict[str, object] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return whether the manager lifecycle is active."""

        return self._loaded

    async def async_setup(self) -> None:
        """Initialize manager-owned runtime resources."""

        self._loaded = True

    async def async_unload(self) -> None:
        """Release manager-owned runtime resources."""

        self.controllers.clear()
        self._loaded = False

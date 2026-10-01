"""Base entity helpers for Entity Controller v10."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from .const import DOMAIN
from .controller import ControllerRuntime


class EntityControllerEntity(Entity):
    """Common data for one controller-owned Home Assistant entity."""

    entity_registry_enabled_default = True
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        runtime: ControllerRuntime,
        entry_id: str,
        key: str,
        *,
        enabled_default: bool = True,
    ) -> None:
        self.runtime = runtime
        self.entry_id = entry_id
        self.key = key
        self.entity_registry_enabled_default = enabled_default

    async def async_added_to_hass(self) -> None:
        """Update the entity whenever its controller runtime changes."""

        self.async_on_remove(
            self.runtime.add_update_listener(self.async_write_ha_state)
        )

    @property
    def unique_id(self) -> str:
        """Return a stable unique id scoped to the root entry and subentry."""

        return f"{self.entry_id}_{self.runtime.config.subentry_id}_{self.key}"

    @property
    def suggested_object_id(self) -> str:
        """Suggest the canonical ID only when Home Assistant first registers us.

        The entity registry keys existing entries by ``unique_id``, so a user
        rename remains intact and a later controller rename cannot overwrite it.
        """

        return f"ec_{slugify(self.runtime.config.name)}_{self.key}"

    @property
    def device_info(self) -> dict[str, object]:
        """Return current ConfigEntry/ConfigSubentry device ownership metadata."""

        subentry_id = self.runtime.config.subentry_id
        return {
            "identifiers": {(DOMAIN, subentry_id)},
            "name": self.runtime.config.name,
            "manufacturer": "Entity Controller",
            "model": "Entity Controller v10",
        }

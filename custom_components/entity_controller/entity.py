"""Base entity helpers for Entity Controller v10."""

from __future__ import annotations

from typing import Protocol

from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from .const import DOMAIN
from .controller import ControllerRuntime


class EntityRegistryLike(Protocol):
    """Small part of HA's entity registry used for prerelease migration."""

    def async_get(self, entity_id: str) -> object | None: ...

    def async_update_entity(self, entity_id: str, *, new_entity_id: str) -> object: ...


def controller_entity_add_kwargs(
    entry: object, controller_id: str
) -> dict[str, str | None]:
    """Associate entities with a ConfigSubentry only for the legacy model."""

    if controller_id in getattr(entry, "subentries", {}):
        return {"config_subentry_id": controller_id}
    # Explicit None clears the old subentry association when adopting a v10
    # prerelease entity into its new standalone controller config entry.
    return {"config_subentry_id": None}


def migrate_legacy_entity_id(
    registry: EntityRegistryLike,
    current_entity_id: str,
    unique_id: str,
    *,
    expected_legacy_entity_id: str,
    canonical_entity_id: str,
) -> bool:
    """Rename only a known generated prerelease ID when the target is free."""

    if current_entity_id != expected_legacy_entity_id:
        return False
    entry = registry.async_get(current_entity_id)
    if entry is None or getattr(entry, "unique_id", None) != unique_id:
        return False
    if registry.async_get(canonical_entity_id) is not None:
        return False
    registry.async_update_entity(current_entity_id, new_entity_id=canonical_entity_id)
    return True


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
        entity_domain: str,
        *,
        enabled_default: bool = True,
    ) -> None:
        self.runtime = runtime
        self.entry_id = entry_id
        self.key = key
        self.entity_registry_enabled_default = enabled_default
        self.entity_id = f"{entity_domain}.{self.suggested_object_id}"

    async def async_added_to_hass(self) -> None:
        """Update the entity whenever its controller runtime changes."""

        self.async_on_remove(
            self.runtime.add_update_listener(self.async_write_ha_state)
        )
        controller_slug = slugify(self.runtime.config.name)
        expected_old_id = (
            f"{self.entity_id.partition('.')[0]}."
            f"{controller_slug}_ec_{controller_slug}_{self.key}"
        )
        migrate_legacy_entity_id(
            entity_registry.async_get(self.hass),
            self.entity_id,
            self.unique_id,
            expected_legacy_entity_id=expected_old_id,
            canonical_entity_id=(
                f"{self.entity_id.partition('.')[0]}.{self.suggested_object_id}"
            ),
        )

    @property
    def unique_id(self) -> str:
        """Return a stable unique id scoped to the root entry and subentry."""

        prefix = self.runtime.config.entity_unique_id_prefix or (
            f"{self.entry_id}_{self.runtime.config.subentry_id}"
        )
        return f"{prefix}_{self.key}"

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

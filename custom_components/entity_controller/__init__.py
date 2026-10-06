"""Entity Controller integration."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entry_migration import migrated_controller_data, migrated_entry_unique_id
from .manager import EntityControllerManager
from .migration import ImportedController, migrate_legacy_yaml, parse_legacy_yaml
from .panel import async_setup_panel, async_unsetup_panel
from .services import async_setup_services, async_unload_services

PLATFORMS: list[str] = ["sensor", "binary_sensor", "switch", "button"]
_LOGGER = logging.getLogger(__name__)


type EntityControllerConfigEntry = ConfigEntry[EntityControllerManager]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Import controllers from legacy YAML during the one-time migration."""

    if not isinstance(config, Mapping):
        _LOGGER.error("Legacy YAML configuration must be a mapping")
        return True

    legacy_config = config.get(DOMAIN)
    if not legacy_config:
        # A standalone /config/entitycontroller.yaml is not loaded by Home
        # Assistant unless configuration.yaml includes it. Read this one
        # conventional file as a migration fallback so reinstalling v10 can
        # still import the original data without restoring the old integration.
        try:
            legacy_path = Path(hass.config.path("entitycontroller.yaml"))
            content = await hass.async_add_executor_job(
                lambda: legacy_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return True
        except OSError:
            _LOGGER.exception("Unable to read /config/entitycontroller.yaml")
            return True
        try:
            legacy_config = parse_legacy_yaml(content)
        except (AttributeError, KeyError, TypeError, ValueError):
            _LOGGER.exception("Unable to parse /config/entitycontroller.yaml")
            return True
        if not legacy_config:
            return True
    if not isinstance(legacy_config, Mapping):
        _LOGGER.error("Legacy YAML configuration must be a mapping")
        return True

    existing_controller_ids = {
        controller_id
        for entry in hass.config_entries.async_entries(DOMAIN)
        if isinstance(
            (controller_id := entry.data.get("_ec_controller_id")), str
        )
    }
    try:
        report = migrate_legacy_yaml(
            dict(legacy_config), existing_controller_ids=existing_controller_ids
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        _LOGGER.exception("Unable to parse legacy YAML configuration")
        return True

    for warning in report.warnings:
        _LOGGER.warning(
            "Skipping or partially migrating legacy controller %s field %s: %s",
            warning.controller_id,
            warning.field,
            warning.message,
        )

    hass.async_create_task(_async_import_legacy_controllers(hass, report.imported))
    return True


async def _async_import_legacy_controllers(
    hass: HomeAssistant, controllers: list[ImportedController]
) -> None:
    """Run import flows after integration setup has returned."""

    imported_count = 0
    for controller in controllers:
        try:
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={"controller_id": controller.controller_id, **controller.data},
            )
        except Exception:
            _LOGGER.exception(
                "Unable to import legacy controller %s", controller.controller_id
            )
            continue

        if result["type"] == "create_entry":
            imported_count += 1
        elif not (
            result["type"] == "abort"
            and result.get("reason") == "already_configured"
        ):
            _LOGGER.warning(
                "Legacy controller %s import did not create an entry: %s",
                controller.controller_id,
                result.get("reason", result["type"]),
            )

    if imported_count:
        _LOGGER.info("Imported %d legacy Svetlo v tme controller(s)", imported_count)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Replace the v10 root/subentry tree with one config entry per controller."""

    if entry.version >= 11:
        return True
    if entry.version != 10:
        return False

    subentries = tuple(
        subentry
        for subentry in getattr(entry, "subentries", {}).values()
        if getattr(subentry, "subentry_type", "controller") == "controller"
    )
    if not subentries:
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
        return False

    # Reuse the old root entry ID for the first controller. This keeps the
    # migration inside Home Assistant's entry-setup lifecycle (removing the
    # entry from inside its migration callback would deadlock on setup_lock).
    for subentry in subentries[1:]:
        unique_id = migrated_entry_unique_id(entry.entry_id, subentry.subentry_id)
        target = hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, unique_id
        )
        if target is None:
            entry_kwargs = {}
            if "subentries_data" in inspect.signature(ConfigEntry).parameters:
                entry_kwargs["subentries_data"] = MappingProxyType({})
            target = ConfigEntry(
                domain=DOMAIN,
                title=subentry.title,
                data=MappingProxyType(
                    migrated_controller_data(
                        entry.entry_id,
                        subentry.subentry_id,
                        subentry.data,
                    )
                ),
                options=MappingProxyType({}),
                source=entry.source,
                unique_id=unique_id,
                discovery_keys=MappingProxyType({}),
                version=11,
                minor_version=1,
                **entry_kwargs,
            )
            await hass.config_entries.async_add(target)
        elif target.state is not ConfigEntryState.LOADED:
            await hass.config_entries.async_reload(target.entry_id)
        if target.state is not ConfigEntryState.LOADED:
            return False

    # Secondary entries are now loaded and have adopted their stable entity
    # unique IDs and device identifiers. Clear the old subentry association;
    # the first controller will be attached directly to this root entry below.
    for subentry in subentries:
        hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
    first = subentries[0]
    hass.config_entries.async_update_entry(
        entry,
        data=MappingProxyType(
            migrated_controller_data(entry.entry_id, first.subentry_id, first.data)
        ),
        title=first.title,
        version=11,
        minor_version=1,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> bool:
    """Set up Entity Controller from a config entry."""

    manager = EntityControllerManager(hass, entry)
    await manager.async_setup()
    entry.runtime_data = manager
    if hasattr(hass, "data") and hasattr(hass, "services"):
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
        async_setup_services(hass)
        await async_setup_panel(hass)
    if hasattr(entry, "add_update_listener"):
        remove_listener = entry.add_update_listener(_async_entry_updated)
        if hasattr(entry, "async_on_unload"):
            entry.async_on_unload(remove_listener)
    if hasattr(hass, "config_entries") and hasattr(
        hass.config_entries, "async_forward_entry_setups"
    ):
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> bool:
    """Unload an Entity Controller config entry."""

    unload_ok = True
    if hasattr(hass, "config_entries") and hasattr(
        hass.config_entries, "async_unload_platforms"
    ):
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.async_unload()
    if hasattr(hass, "data") and hasattr(hass, "services"):
        hass.data.setdefault(DOMAIN, {}).pop(entry.entry_id, None)
        async_unload_services(hass)
        remaining_managers = [
            manager
            for key, manager in hass.data.get(DOMAIN, {}).items()
            if not key.startswith("_") and hasattr(manager, "controllers")
        ]
        if not remaining_managers:
            async_unsetup_panel(hass)
    return unload_ok


async def _async_entry_updated(
    hass: HomeAssistant,
    entry: EntityControllerConfigEntry,
) -> None:
    """Apply config-subentry changes without reloading sibling controllers."""

    await entry.runtime_data.async_sync_subentries()

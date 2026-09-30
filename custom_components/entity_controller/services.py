"""Home Assistant action registration for Entity Controller v10."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from .actions import (
    async_activate,
    async_clear_block,
    async_disable_stay_mode,
    async_enable_block,
    async_enable_stay_mode,
    async_set_night_mode,
)
from .const import (
    DOMAIN,
    SERVICE_ACTIVATE,
    SERVICE_CLEAR_BLOCK,
    SERVICE_DISABLE_STAY_MODE,
    SERVICE_ENABLE_BLOCK,
    SERVICE_ENABLE_STAY_MODE,
    SERVICE_SET_NIGHT_MODE,
)
from .manager import EntityControllerManager

CONF_CONTROLLER_ID = "controller_id"
CONF_ENTITY_ID = "entity_id"
CONF_START_TIME = "start_time"
CONF_END_TIME = "end_time"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONTROLLER_ID): vol.Any(str, [str]),
        vol.Optional(CONF_ENTITY_ID): vol.Any(str, [str]),
        vol.Optional(CONF_START_TIME): str,
        vol.Optional(CONF_END_TIME): str,
    }
)

_ACTIONS = {
    SERVICE_ACTIVATE: async_activate,
    SERVICE_CLEAR_BLOCK: async_clear_block,
    SERVICE_ENABLE_BLOCK: async_enable_block,
    SERVICE_ENABLE_STAY_MODE: async_enable_stay_mode,
    SERVICE_DISABLE_STAY_MODE: async_disable_stay_mode,
}


def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain actions once."""

    if hass.services.has_service(DOMAIN, SERVICE_ACTIVATE):
        return

    async def _handle(call: ServiceCall) -> None:
        await async_dispatch_service(
            hass.data.get(DOMAIN, {}), call.service, dict(call.data)
        )

    for service in (*_ACTIONS, SERVICE_SET_NIGHT_MODE):
        hass.services.async_register(DOMAIN, service, _handle, schema=SERVICE_SCHEMA)


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove actions after the final Entity Controller entry unloads."""

    if hass.data.get(DOMAIN):
        return
    for service in (*_ACTIONS, SERVICE_SET_NIGHT_MODE):
        hass.services.async_remove(DOMAIN, service)


async def async_dispatch_service(
    managers: Mapping[str, EntityControllerManager],
    service: str,
    data: Mapping[str, Any],
) -> None:
    """Dispatch one action to selected controller runtimes."""

    selected = _selected_ids(data)
    for manager in managers.values():
        for subentry_id, runtime in manager.controllers.items():
            if selected is not None and subentry_id not in selected:
                continue
            if service == SERVICE_SET_NIGHT_MODE:
                await async_set_night_mode(
                    runtime,
                    start_time=data.get(CONF_START_TIME),
                    end_time=data.get(CONF_END_TIME),
                )
            elif action := _ACTIONS.get(service):
                await action(runtime)


def _selected_ids(data: Mapping[str, Any]) -> set[str] | None:
    values = data.get(CONF_CONTROLLER_ID, data.get(CONF_ENTITY_ID))
    if values is None:
        return None
    if isinstance(values, str):
        values = [values]
    return {str(value).rsplit(".", 1)[-1] for value in values}

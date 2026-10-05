"""Native Home Assistant sidebar panel for Entity Controller."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.helpers import entity_registry
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .schedule import resolve_schedule_point, schedule_point_from_data

PANEL_URL = "entity-controller"
PANEL_JS = "/entity_controller/entity-controller-panel.js"
PANEL_JS_VERSION = "10.4.2"
_PANEL_DATA_KEY = "entity_controller_panel"
_PANEL_SAVE_SCHEMA = {
    vol.Required("type"): "entity_controller/panel/save",
    vol.Required("entry_id"): str,
    vol.Required("controller_id"): str,
    vol.Required("form"): dict,
}


def _registered_entity_id(hass: Any, domain: str, unique_id: str) -> str | None:
    """Resolve an entity ID without assuming the user kept the suggested ID."""

    return entity_registry.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)


def _resolved_schedule(hass: Any, data: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Resolve configured schedule endpoints against Home Assistant's local sun data."""

    from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
    from homeassistant.helpers.sun import get_astral_event_date

    from .schedule import resolve_schedule_point, schedule_point_from_data

    now = dt_util.now()
    result: dict[str, dict[str, int]] = {}
    for name, window in (
        ("constraint", data.get("constraint_window")),
        ("night", data.get("night_mode")),
    ):
        if not window:
            continue
        points = {side: schedule_point_from_data(dict(window[side])) for side in ("start", "end")}
        events: dict[str, datetime | None] = {"sunrise": None, "sunset": None}
        for source, event in (("sunrise", SUN_EVENT_SUNRISE), ("sunset", SUN_EVENT_SUNSET)):
            if any(point.source.value == source for point in points.values()):
                try:
                    events[source] = get_astral_event_date(hass, event, now.date())
                except (ValueError, TypeError):
                    pass
        resolved: dict[str, int] = {}
        for side, point in points.items():
            try:
                at = resolve_schedule_point(
                    point, now, sunrise=events["sunrise"], sunset=events["sunset"]
                )
            except (ValueError, TypeError):
                continue
            resolved[side] = (at.hour * 60 + at.minute) % 1440
        if resolved:
            result[name] = resolved
    return result


def _next_schedule_change(hass: Any, runtime: Any) -> tuple[datetime, str] | None:
    """Find the next configured constraint or night-profile boundary."""

    now = dt_util.now()
    candidates: list[tuple[datetime, str]] = []

    for key, active, start_label, end_label, ends_when_active in (
        (
            "constraint_window",
            getattr(runtime, "constrained", False),
            "Otvorenie časového okna",
            "Zatvorenie časového okna",
            False,
        ),
        (
            "night_mode",
            getattr(runtime, "night_active", False),
            "Začiatok nočného profilu",
            "Koniec nočného profilu",
            True,
        ),
    ):
        window = getattr(runtime.config, key, None)
        if not window:
            continue
        start_point = schedule_point_from_data(dict(window["start"]))
        end_point = schedule_point_from_data(dict(window["end"]))
        sources = {start_point.source.value, end_point.source.value}
        for day_offset in range(-1, 4):
            day = (now + timedelta(days=day_offset)).date()
            sunrise = sunset = None
            if sources.intersection({"sunrise", "sunset"}):
                from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
                from homeassistant.helpers.sun import get_astral_event_date

                try:
                    if "sunrise" in sources:
                        sunrise = get_astral_event_date(hass, SUN_EVENT_SUNRISE, day)
                    if "sunset" in sources:
                        sunset = get_astral_event_date(hass, SUN_EVENT_SUNSET, day)
                except (ValueError, TypeError):
                    continue
            reference = datetime.combine(day, now.timetz())
            try:
                start_at = resolve_schedule_point(
                    start_point, reference, sunrise=sunrise, sunset=sunset
                )
                end_at = resolve_schedule_point(
                    end_point, reference, sunrise=sunrise, sunset=sunset
                )
            except ValueError:
                continue
            if end_at <= start_at:
                end_at += timedelta(days=1)
            use_end = active == ends_when_active
            boundary = end_at if use_end else start_at
            if boundary > now:
                candidates.append(
                    (boundary, end_label if use_end else start_label)
                )

    return min(candidates, default=None, key=lambda item: item[0])


def _next_automatic_change(runtime: Any, hass: Any) -> tuple[datetime, str] | None:
    """Return the closest deadline that can change the runtime automatically."""

    candidates: list[tuple[datetime, str]] = []
    if getattr(runtime, "expires_at", None) is not None:
        candidates.append((runtime.expires_at, "Koniec času aktivity"))
    if getattr(runtime, "block_expires_at", None) is not None:
        candidates.append((runtime.block_expires_at, "Automatické odblokovanie"))
    if schedule_change := _next_schedule_change(hass, runtime):
        candidates.append(schedule_change)
    now = dt_util.now()
    future = [item for item in candidates if item[0] > now]
    return min(future, default=None, key=lambda item: item[0])


def serialize_controllers(hass: Any) -> list[dict[str, Any]]:
    """Build a JSON-safe, dynamic view of all loaded controller runtimes."""

    result: list[dict[str, Any]] = []
    from .config_flow import controller_form_values

    for entry_id, manager in hass.data.get(DOMAIN, {}).items():
        if entry_id.startswith("_") or not hasattr(manager, "controllers"):
            continue
        for controller_id, runtime in manager.controllers.items():
            config = runtime.config
            entry = getattr(manager, "entry", None)
            entry_data = dict(getattr(entry, "data", {}) or {})
            subentry = getattr(entry, "subentries", {}).get(controller_id)
            if subentry is not None:
                entry_data = dict(subentry.data)
            form = controller_form_values(entry_data)
            form.setdefault("basic", {}).setdefault("icon", config.icon or "")
            unique_prefix = config.entity_unique_id_prefix or f"{entry_id}_{controller_id}"
            state = getattr(runtime.state, "value", str(runtime.state))
            result.append(
                {
                    "id": controller_id,
                    "entry_id": entry_id,
                    "form": form,
                    "resolved_schedule": _resolved_schedule(hass, entry_data),
                    "name": config.name,
                    "icon": config.icon,
                    "state": state,
                    "enabled": runtime.enabled,
                    "stay_mode": runtime.stay_mode,
                    "state_entity_id": _registered_entity_id(
                        hass, "sensor", f"{unique_prefix}_state"
                    ),
                    "enabled_entity_id": _registered_entity_id(
                        hass, "switch", f"{unique_prefix}_enabled"
                    ),
                    "inputs": list(dict.fromkeys((
                        *config.trigger_entities,
                        *config.state_entities,
                        *config.override_entities,
                        *config.interlock_entities,
                    ))),
                    "triggers": list(config.trigger_entities),
                    "outputs": list(config.control_entities),
                    "overrides": list(config.override_entities),
                    "interlocks": list(config.interlock_entities),
                    "constraints": list(
                        (*config.state_entities, *config.override_entities, *config.interlock_entities)
                    ),
                    "last_transition_at": getattr(runtime, "last_transition_at", None),
                    "last_transition_cause": getattr(
                        getattr(runtime, "last_transition_cause", None), "value", None
                    ),
                    "last_triggered_at": getattr(runtime, "last_triggered_at", None),
                    "effective_delay_seconds": getattr(runtime, "effective_delay_seconds", None),
                    "expires_at": getattr(runtime, "expires_at", None),
                    "block_expires_at": getattr(runtime, "block_expires_at", None),
                    "next_transition_at": (
                        next_change[0] if (next_change := _next_automatic_change(runtime, hass)) else None
                    ),
                    "next_transition_label": (
                        next_change[1] if next_change else None
                    ),
                    "blocked_by": list(getattr(runtime, "blocked_by", ()) or ()),
                    "block_reason": getattr(runtime, "block_reason", None),
                    "active_triggers": list(getattr(runtime, "active_triggers", ()) or ()),
                    "active_state_entities": list(
                        getattr(runtime, "active_state_entities", ()) or ()
                    ),
                    "active_overrides": list(getattr(runtime, "active_overrides", ()) or ()),
                    "active_interlocks": list(getattr(runtime, "active_interlocks", ()) or ()),
                }
            )
    return result


@websocket_api.websocket_command({"type": "entity_controller/panel"})
@websocket_api.async_response
async def websocket_get_panel_data(hass, connection, msg) -> None:
    """Return current controller data to an authenticated HA frontend."""

    connection.send_result(msg["id"], {"controllers": serialize_controllers(hass)})


@websocket_api.websocket_command(_PANEL_SAVE_SCHEMA)
@websocket_api.async_response
async def websocket_save_controller(hass, connection, msg) -> None:
    """Persist an inline controller edit and hot-reconfigure its runtime."""

    if not getattr(getattr(connection, "user", None), "is_admin", False):
        connection.send_error(msg["id"], "unauthorized", "Administrator access is required")
        return

    controller_id = msg["controller_id"]
    entry_id = msg["entry_id"]
    manager = hass.data.get(DOMAIN, {}).get(entry_id)
    runtime = getattr(manager, "controllers", {}).get(controller_id)
    if runtime is None:
        connection.send_error(msg["id"], "not_found", "Controller was not found")
        return

    entry = manager.entry
    from .config_flow import CONTROLLER_SCHEMA, normalize_controller_user_input
    from .entry_migration import CONTROLLER_ID_KEY

    current = dict(entry.data)
    subentry = None
    if not current.get(CONTROLLER_ID_KEY):
        subentry = getattr(entry, "subentries", {}).get(controller_id)
        if subentry is None:
            connection.send_error(msg["id"], "not_found", "Controller configuration was not found")
            return
        current = dict(subentry.data)

    try:
        form = dict(msg["form"])
        basic = dict(form.get("basic", {}))
        if not basic.get("icon"):
            basic.pop("icon", None)
            form["basic"] = basic
        validated_form = CONTROLLER_SCHEMA(form)
        normalized = normalize_controller_user_input(validated_form)
        updated = {**current, **normalized}
        if subentry is None:
            hass.config_entries.async_update_entry(
                entry, data=updated, title=updated.get("name", entry.title)
            )
        else:
            hass.config_entries.async_update_subentry(
                entry,
                subentry,
                data=updated,
                title=updated.get("name", subentry.title),
            )
    except (KeyError, TypeError, ValueError, vol.Invalid) as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return

    from .config_flow import controller_form_values

    saved_form = controller_form_values(updated)
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "form": saved_form,
            "name": updated.get("name", ""),
            "icon": updated.get("icon", ""),
            "resolved_schedule": _resolved_schedule(hass, updated),
        },
    )


def _register_websocket(hass: Any) -> None:
    """Register the read-only panel data command once per HA instance."""

    marker = hass.data.setdefault(_PANEL_DATA_KEY, {})
    if marker.get("websocket"):
        return
    websocket_api.async_register_command(hass, websocket_get_panel_data)
    websocket_api.async_register_command(hass, websocket_save_controller)
    marker["websocket"] = True


async def async_setup_panel(hass: Any) -> None:
    """Register panel assets and sidebar item once controllers are loaded."""

    if not hasattr(hass, "http"):
        return
    data = hass.data.setdefault(_PANEL_DATA_KEY, {})
    lock = data.setdefault("lock", asyncio.Lock())
    async with lock:
        if data.get("registered"):
            return
        _register_websocket(hass)
        if not data.get("static_registered"):
            static_path = Path(__file__).parent / "www" / "entity-controller-panel.js"
            if hasattr(hass.http, "async_register_static_paths"):
                from homeassistant.components.http import StaticPathConfig

                await hass.http.async_register_static_paths(
                    [StaticPathConfig(PANEL_JS, str(static_path), cache_headers=False)]
                )
            else:  # Compatibility with older HA versions used by the test environment.
                hass.http.register_static_path(PANEL_JS, str(static_path), cache_headers=False)
            # HTTP routes live for the HA process lifetime, even if the final
            # integration entry unloads. Keep this marker across panel reloads.
            data["static_registered"] = True
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Entity Controller",
            sidebar_icon="mdi:home-automation",
            frontend_url_path=PANEL_URL,
            config={
                "_panel_custom": {
                    "name": "entity-controller-panel",
                    "js_url": f"{PANEL_JS}?v={PANEL_JS_VERSION}",
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
            require_admin=False,
            update=True,
        )
        data["registered"] = True


def async_unsetup_panel(hass: Any) -> None:
    """Remove the sidebar panel after the last integration entry unloads."""

    data = hass.data.get(_PANEL_DATA_KEY)
    if not data or not data.pop("registered", False):
        return
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)


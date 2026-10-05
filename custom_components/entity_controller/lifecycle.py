"""Validate and execute native Home Assistant lifecycle action sequences."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.script import (
    DATA_SCRIPTS,
    Script,
    async_validate_actions_config,
)

from .const import DOMAIN
from .model import DEFAULT_TRANSITION_BEHAVIORS


def normalize_lifecycle_actions(value: Any) -> dict[str, list[dict[str, Any]]]:
    """Validate action structure while keeping Config Entry data JSON-safe.

    HA's script schema compiles templates and durations. Validate a copy, but
    persist the original JSON data and compile only when a hook executes.
    """

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise vol.Invalid("Lifecycle actions must be a mapping of hooks to sequences")
    result: dict[str, list[dict[str, Any]]] = {}
    for hook, sequence in value.items():
        if hook not in DEFAULT_TRANSITION_BEHAVIORS:
            raise vol.Invalid(f"Unknown lifecycle action hook: {hook}")
        if not isinstance(sequence, list) or any(
            not isinstance(action, dict) for action in sequence
        ):
            raise vol.Invalid(f"Lifecycle hook {hook} must contain an action list")
        cv.SCRIPT_SCHEMA(deepcopy(sequence))
        result[hook] = deepcopy(sequence)
    return result


async def async_execute_sequence(
    hass: HomeAssistant,
    sequence: Sequence[dict[str, Any]],
    *,
    name: str,
    context: Context,
    variables: Mapping[str, Any] | None = None,
) -> None:
    """Run a native HA script, preserving EC ownership and propagating errors.

    Awaiting completion lets the manager report failures and cancel delayed
    actions after a manual takeover. Never call this from reconcile paths.
    """

    if not sequence:
        return
    compiled = cv.SCRIPT_SCHEMA(deepcopy(list(sequence)))
    validated = await async_validate_actions_config(hass, compiled)
    script = Script(hass, validated, name, DOMAIN)
    try:
        await script.async_run(dict(variables or {}), context=context)
    finally:
        # Each invocation owns its Script. New HA versions expose full unload;
        # older supported versions require removing the stopped registry entry.
        unload = getattr(script, "async_unload", None)
        if unload is not None:
            await unload()
        else:
            await script.async_stop()
            registry = hass.data.get(DATA_SCRIPTS)
            if isinstance(registry, list):
                registry[:] = [
                    item for item in registry if item["instance"] is not script
                ]
            elif isinstance(registry, dict):
                registry.pop(id(script), None)

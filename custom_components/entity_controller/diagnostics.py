"""Diagnostics support for Entity Controller v10."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .manager import EntityControllerManager

_REDACT_KEYS = ("password", "secret", "token")


async def async_get_config_entry_diagnostics(
    hass: Any,
    config_entry: Any,
) -> dict[str, Any]:
    """Return stable, redacted diagnostics for one EC config entry."""

    manager = getattr(config_entry, "runtime_data", None)
    if not isinstance(manager, EntityControllerManager):
        manager = None

    controllers = []
    if manager is not None:
        for subentry_id in sorted(manager.controllers):
            runtime = manager.controllers[subentry_id]
            controllers.append(
                {
                    "subentry_id": subentry_id,
                    "name": runtime.config.name,
                    "state": runtime.state.value,
                    "enabled": runtime.enabled,
                    "stay_mode": runtime.stay_mode,
                    "expires_at": runtime.expires_at.isoformat()
                    if runtime.expires_at is not None
                    else None,
                    "last_triggered_by": runtime.last_triggered_by,
                    "last_reconcile_reason": runtime.last_reconcile_reason.value
                    if runtime.last_reconcile_reason is not None
                    else None,
                }
            )

    return {
        "entry": {
            "entry_id": getattr(config_entry, "entry_id", None),
            "data": _redact(getattr(config_entry, "data", {})),
        },
        "controllers": controllers,
        "controller_errors": dict(
            sorted((manager.controller_errors if manager is not None else {}).items())
        ),
    }


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "**REDACTED**" if _is_sensitive_key(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(marker in normalized for marker in _REDACT_KEYS)

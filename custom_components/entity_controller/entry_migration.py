"""Helpers for moving v10 controller subentries into flat config entries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import normalize_transition_behaviors

CONTROLLER_ID_KEY = "_ec_controller_id"
ENTITY_UNIQUE_ID_PREFIX_KEY = "_ec_entity_unique_id_prefix"


def migrated_entry_unique_id(root_entry_id: str, subentry_id: str) -> str:
    """Return the deterministic entry ID used to make migration retryable."""

    return f"ec-migrated:{root_entry_id}:{subentry_id}"


def migrated_controller_data(
    root_entry_id: str,
    subentry_id: str,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy one v10 subentry while retaining its device and entity identity."""

    return {
        **dict(data),
        "transition_behaviors": {
            key: behavior.value
            for key, behavior in normalize_transition_behaviors(data.get("transition_behaviors")).items()
        },
        CONTROLLER_ID_KEY: subentry_id,
        ENTITY_UNIQUE_ID_PREFIX_KEY: f"{root_entry_id}_{subentry_id}",
    }


def fresh_controller_data(
    data: Mapping[str, Any], *, controller_id: str
) -> dict[str, Any]:
    """Attach stable controller identity metadata to a new controller entry."""

    return {
        **dict(data),
        CONTROLLER_ID_KEY: controller_id,
        ENTITY_UNIQUE_ID_PREFIX_KEY: controller_id,
    }

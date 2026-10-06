from __future__ import annotations

from custom_components.entity_controller.entry_migration import (
    migrated_controller_data,
    migrated_entry_unique_id,
)


def test_v10_subentry_migration_preserves_controller_and_entity_identity() -> None:
    old_data = {
        "name": "WC",
        "trigger_entities": ["binary_sensor.wc_motion"],
        "enabled": False,
        "stay_mode": True,
    }

    result = migrated_controller_data("old-root", "wc-subentry", old_data)

    assert result["name"] == "WC"
    assert result["trigger_entities"] == ["binary_sensor.wc_motion"]
    assert result["enabled"] is False
    assert result["stay_mode"] is True
    assert result["_ec_controller_id"] == "wc-subentry"
    assert result["_ec_entity_unique_id_prefix"] == "old-root_wc-subentry"
    assert migrated_entry_unique_id("old-root", "wc-subentry") == (
        "ec-migrated:old-root:wc-subentry"
    )


def test_fresh_controller_identity_is_stable_and_name_independent() -> None:
    from custom_components.entity_controller.entry_migration import (
        fresh_controller_data,
    )

    result = fresh_controller_data(
        {
            "name": "Obývačka",
            "trigger_entities": ["binary_sensor.motion"],
        },
        controller_id="controller-id",
    )

    assert result["name"] == "Obývačka"
    assert result["_ec_controller_id"] == "controller-id"
    assert result["_ec_entity_unique_id_prefix"] == "controller-id"


def test_flat_entry_association_explicitly_clears_old_subentry_ownership() -> None:
    from custom_components.entity_controller.entity import controller_entity_add_kwargs

    legacy_entry = type("Entry", (), {"subentries": {"controller-a": object()}})()
    flat_entry = type("Entry", (), {"subentries": {}})()

    assert controller_entity_add_kwargs(legacy_entry, "controller-a") == {
        "config_subentry_id": "controller-a"
    }
    assert controller_entity_add_kwargs(flat_entry, "controller-a") == {
        "config_subentry_id": None
    }


def test_flattening_migrates_only_the_legacy_default_shutdown_pair() -> None:
    legacy = {"name": "Room", "transition_behaviors": {
        "on_enter_idle": "off", "on_exit_active": "ignore", "on_enter_overridden": "on",
    }}
    result = migrated_controller_data("root", "room", legacy)
    assert result["transition_behaviors"]["on_enter_idle"] == "ignore"
    assert result["transition_behaviors"]["on_exit_active"] == "off"
    assert result["transition_behaviors"]["on_enter_overridden"] == "on"
    assert legacy["transition_behaviors"]["on_enter_idle"] == "off"
    assert migrated_controller_data("root", "room", result) == result


def test_flattening_preserves_an_explicit_custom_active_exit_policy() -> None:
    result = migrated_controller_data("root", "room", {"name": "Room", "transition_behaviors": {
        "on_enter_idle": "off", "on_exit_active": "custom",
    }})
    assert result["transition_behaviors"]["on_enter_idle"] == "off"
    assert result["transition_behaviors"]["on_exit_active"] == "custom"

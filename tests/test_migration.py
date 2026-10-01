from __future__ import annotations

from pathlib import Path

from custom_components.entity_controller.migration import (
    migrate_legacy_yaml,
    parse_legacy_yaml,
)

FIXTURE = Path("tests/fixtures/legacy_ec.yaml")


def test_parse_legacy_yaml_imports_one_controller_per_entry() -> None:
    legacy = parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8"))

    report = migrate_legacy_yaml(legacy)

    assert [item.controller_id for item in report.imported] == [
        "ec01_izba_pohyb",
        "ec02_chodba",
        "ec04_vchod",
    ]
    assert report.imported[0].data["trigger_entities"] == (
        "binary_sensor.izba_pohyb",
        "binary_sensor.izba_dvere",
    )
    assert report.imported[0].data["control_entities"] == ("light.izba",)
    assert report.imported[0].data["state_entities"] == ("light.izba",)
    assert report.imported[0].data["sensor_type"] == "duration"
    assert report.imported[0].data["delay_seconds"] == 90.0
    assert report.imported[0].data["sensor_resets_timer"] is True
    assert report.imported[0].data["block_timeout_seconds"] == 1800.0
    assert report.imported[0].data["backoff_enabled"] is True
    assert report.imported[0].data["backoff_factor"] == 1.5
    assert report.imported[0].data["backoff_max_seconds"] == 600.0


def test_external_helpers_are_preserved_as_references_only() -> None:
    report = migrate_legacy_yaml(parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8")))
    by_id = {item.controller_id: item.data for item in report.imported}

    assert by_id["ec01_izba_pohyb"]["override_entities"] == (
        "input_boolean.navsteva_block",
    )
    assert by_id["ec02_chodba"]["override_entities"] == (
        "input_boolean.navsteva_block",
    )
    assert by_id["ec02_chodba"]["interlock_entities"] == (
        "input_boolean.izba_block",
    )
    assert report.external_helper_references == {
        "input_boolean.navsteva_block",
        "input_boolean.izba_block",
    }
    assert report.created_helper_entities == set()


def test_migration_is_idempotent_when_existing_controller_ids_are_supplied() -> None:
    legacy = parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8"))
    first = migrate_legacy_yaml(legacy)

    second = migrate_legacy_yaml(
        legacy,
        existing_controller_ids={item.controller_id for item in first.imported},
    )

    assert second.imported == []
    assert second.skipped_existing == {
        "ec01_izba_pohyb",
        "ec02_chodba",
        "ec04_vchod",
    }


def test_unknown_fields_are_reported_not_silently_dropped() -> None:
    report = migrate_legacy_yaml(parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8")))

    assert any(
        warning.controller_id == "ec01_izba_pohyb"
        and warning.field == "unknown_future_field"
        for warning in report.warnings
    )


def test_structured_schedule_conversion_and_legacy_entity_map() -> None:
    report = migrate_legacy_yaml(parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8")))
    first = report.imported[0].data

    assert first["night_mode"]["start"]["source"] == "sunset"
    assert first["night_mode"]["start"]["offset_seconds"] == -1800
    assert first["night_mode"]["end"]["source"] == "sunrise"
    assert first["night_mode"]["end"]["offset_seconds"] == 900
    assert report.legacy_entity_map["entity_controller.ec01_izba_pohyb"] == (
        "sensor.ec01_izba_pohyb_state"
    )


def test_malformed_controller_does_not_block_valid_sibling() -> None:
    report = migrate_legacy_yaml(
        {
            "broken": {"entity": [42]},
            "valid": {"sensor": "binary_sensor.motion", "entity": "light.room"},
        }
    )

    assert [item.controller_id for item in report.imported] == ["valid"]
    assert any(
        warning.controller_id == "broken" and warning.field == "<controller>"
        for warning in report.warnings
    )


def test_supported_v9_settings_are_preserved_and_unsupported_values_warn() -> None:
    report = migrate_legacy_yaml(
        {
            "obyvacka": {
                "sensor": "binary_sensor.obyvacka_pohyb",
                "entity": "light.obyvacka",
                "service_data": {"brightness_pct": 80},
                "service_data_off": {"transition": 2},
                "state_attributes_ignore": ["brightness", "color_mode"],
                "sensor_states_on": ["motion"],
                "sensor_states_off": ["clear"],
                "state_states_on": ["open"],
                "state_states_off": ["closed"],
                "override_states_on": ["armed"],
                "override_states_off": ["disarmed"],
                "state_strings_on": ["custom_on"],
                "state_strings_off": ["custom_off"],
                "sensor_type_duration": True,
                "start_time": "sunset - 00:30:00",
                "end_time": "sunrise + 00:15:00",
                "night_mode": {
                    "start_time": "20:00:00",
                    "end_time": "06:00:00",
                    "delay": 30,
                    "service_data": {"brightness_pct": 15},
                    "service_data_off": {"transition": 4},
                },
                "control_states_on": ["not_supported_by_v10"],
            }
        }
    )

    data = report.imported[0].data
    assert data["service_data_on"] == {"brightness_pct": 80}
    assert data["service_data_off"] == {"transition": 2}
    assert data["state_attributes_ignore"] == ("brightness", "color_mode")
    assert data["sensor_type"] == "duration"
    assert data["trigger_on_states"] == ("motion", "custom_on")
    assert data["trigger_off_states"] == ("clear", "custom_off")
    assert data["state_on_states"] == ("open", "custom_on")
    assert data["state_off_states"] == ("closed", "custom_off")
    assert data["override_on_states"] == ("armed", "custom_on")
    assert data["override_off_states"] == ("disarmed", "custom_off")
    assert data["constraint_window"] == {
        "start": {"source": "sunset", "offset_seconds": -1800},
        "end": {"source": "sunrise", "offset_seconds": 900},
    }
    assert data["night_mode"] == {
        "start": {"source": "fixed", "time": "20:00:00", "offset_seconds": 0},
        "end": {"source": "fixed", "time": "06:00:00", "offset_seconds": 0},
        "delay_seconds": 30.0,
        "service_data_on": {"brightness_pct": 15},
        "service_data_off": {"transition": 4},
    }
    assert any(
        warning.controller_id == "obyvacka"
        and warning.field == "control_states_on"
        for warning in report.warnings
    )


def test_additive_v9_singular_and_plural_entity_fields_are_merged() -> None:
    report = migrate_legacy_yaml(
        {
            "obyvacka": {
                "sensor": "binary_sensor.motion_primary",
                "sensors": [
                    "binary_sensor.motion_primary",
                    "binary_sensor.motion_secondary",
                ],
                "entity": "light.primary",
                "entities": ["light.primary", "switch.secondary"],
                "override": "input_boolean.guest",
                "overrides": ["input_boolean.guest", "input_boolean.vacation"],
                "interlock": "input_boolean.locked",
                "interlocks": ["input_boolean.locked", "input_boolean.alarm"],
            }
        }
    )

    data = report.imported[0].data
    assert data["trigger_entities"] == (
        "binary_sensor.motion_primary",
        "binary_sensor.motion_secondary",
    )
    assert data["control_entities"] == ("light.primary", "switch.secondary")
    assert data["override_entities"] == (
        "input_boolean.guest",
        "input_boolean.vacation",
    )
    assert data["interlock_entities"] == (
        "input_boolean.locked",
        "input_boolean.alarm",
    )

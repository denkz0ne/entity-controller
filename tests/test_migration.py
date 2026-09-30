from __future__ import annotations

from pathlib import Path

from custom_components.entity_controller.migration import (
    migrate_legacy_yaml,
    parse_legacy_yaml,
)

FIXTURE = Path("tests/fixtures/legacy_ec.yaml")


def test_parse_legacy_yaml_imports_one_subentry_per_controller() -> None:
    legacy = parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8"))

    report = migrate_legacy_yaml(legacy)

    assert [item.subentry_id for item in report.imported] == [
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
    by_id = {item.subentry_id: item.data for item in report.imported}

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


def test_migration_is_idempotent_when_existing_subentries_are_supplied() -> None:
    legacy = parse_legacy_yaml(FIXTURE.read_text(encoding="utf-8"))
    first = migrate_legacy_yaml(legacy)

    second = migrate_legacy_yaml(
        legacy,
        existing_subentry_ids={item.subentry_id for item in first.imported},
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

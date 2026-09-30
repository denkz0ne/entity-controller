from __future__ import annotations

from custom_components.entity_controller.migration import MigrationReport, MigrationWarning
from custom_components.entity_controller.repairs import build_migration_repair_issues


def test_legacy_yaml_repair_is_idempotent_guidance_only() -> None:
    report = MigrationReport(
        warnings=[
            MigrationWarning(
                "hall",
                "legacy_field",
                "Unsupported legacy field",
            )
        ],
        cleanup_guidance=(
            "After validating migrated controllers, remove the legacy entity_controller YAML include manually.",
        ),
        external_helper_references={"input_boolean.navsteva_block"},
    )

    first = build_migration_repair_issues(report)
    second = build_migration_repair_issues(
        report,
        already_reported_issue_ids={issue.issue_id for issue in first},
    )

    assert [issue.issue_id for issue in first] == [
        "legacy_yaml_cleanup",
        "legacy_yaml_warning_hall_legacy_field",
    ]
    assert first[0].is_fixable is False
    assert first[0].translation_key == "legacy_yaml_cleanup"
    assert first[0].data["external_helper_references"] == [
        "input_boolean.navsteva_block"
    ]
    assert first[0].data["delete_yaml"] is False
    assert first[0].data["delete_helpers"] is False
    assert second == []

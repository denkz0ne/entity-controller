"""Repair issue builders for Entity Controller v10 migration support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .migration import MigrationReport


@dataclass(frozen=True, slots=True)
class MigrationRepairIssue:
    """A guide-only repair issue to raise through Home Assistant Repairs."""

    issue_id: str
    translation_key: str
    data: dict[str, Any]
    is_fixable: bool = False


def build_migration_repair_issues(
    report: MigrationReport,
    *,
    already_reported_issue_ids: set[str] | None = None,
) -> list[MigrationRepairIssue]:
    """Build idempotent guide-only repair issues for a migration report."""

    reported = already_reported_issue_ids or set()
    issues: list[MigrationRepairIssue] = []

    if report.cleanup_guidance:
        _append_if_new(
            issues,
            reported,
            MigrationRepairIssue(
                issue_id="legacy_yaml_cleanup",
                translation_key="legacy_yaml_cleanup",
                data={
                    "cleanup_guidance": list(report.cleanup_guidance),
                    "external_helper_references": sorted(
                        report.external_helper_references
                    ),
                    "delete_yaml": False,
                    "delete_helpers": False,
                },
            ),
        )

    for warning in report.warnings:
        field = _issue_part(warning.field)
        issue_id = f"legacy_yaml_warning_{_issue_part(warning.controller_id)}_{field}"
        _append_if_new(
            issues,
            reported,
            MigrationRepairIssue(
                issue_id=issue_id,
                translation_key="legacy_yaml_warning",
                data={
                    "controller_id": warning.controller_id,
                    "field": warning.field,
                    "message": warning.message,
                    "delete_yaml": False,
                    "delete_helpers": False,
                },
            ),
        )

    return issues


def _append_if_new(
    issues: list[MigrationRepairIssue],
    reported: set[str],
    issue: MigrationRepairIssue,
) -> None:
    if issue.issue_id in reported:
        return
    issues.append(issue)


def _issue_part(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)

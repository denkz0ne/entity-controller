from __future__ import annotations

import json
from pathlib import Path


def test_stable_manifest_version_is_published() -> None:
    manifest = json.loads(
        Path("custom_components/entity_controller/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["version"] == "10.6.0"


def test_release_checklist_covers_migration_smoke_and_validation_gates() -> None:
    checklist = Path("docs/release-checklist.md").read_text(encoding="utf-8")

    for required in (
        "v9.7.6 -> v10",
        "legacy YAML still present",
        "no duplicate controller entries",
        "remove YAML",
        "EC01",
        "EC10",
        "Enabled",
        "Blocked",
        "Stay",
        "Activate",
        "external helper rules",
        "legacy state mirror",
        "Ruff",
        "HACS",
        "Hassfest",
        "known limitations",
    ):
        assert required in checklist


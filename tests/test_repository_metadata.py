from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml


def test_hacs_metadata_tracks_v10_home_assistant_floor() -> None:
    hacs = json.loads(Path("hacs.json").read_text(encoding="utf-8"))

    assert hacs["name"] == "Entity Controller"
    assert hacs["homeassistant"] == "2026.9.0"
    assert hacs["render_readme"] is True


def test_legacy_node_release_workflow_is_removed() -> None:
    assert not Path(".github/workflows/master.yml").exists()


def test_v10_ci_runs_pytest_ruff_and_repository_validation() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/v10-modernization.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["tests"]["steps"]
    step_names = [step["name"] for step in steps if "name" in step]

    assert "Run Ruff" in step_names
    assert "Validate repository metadata" in step_names
    assert "Run v10 tests" in step_names


def test_pyproject_defines_modern_ruff_and_pytest_settings() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["ruff"]["lint"]["select"] == ["E", "F", "I", "UP", "B"]
    assert pyproject["tool"]["pytest"]["ini_options"]["asyncio_mode"] == "strict"


def test_user_docs_link_core_v10_topics() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    for link in (
        "docs/configuration.md",
        "docs/actions.md",
        "docs/behavior.md",
        "docs/migration-v9-to-v10.md",
        "docs/troubleshooting.md",
    ):
        assert link in readme

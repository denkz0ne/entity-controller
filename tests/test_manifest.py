import json
from pathlib import Path


def test_manifest_is_v10_controller_device_without_transitions_dependency() -> None:
    manifest = json.loads(
        Path("custom_components/entity_controller/manifest.json").read_text()
    )

    assert manifest["domain"] == "entity_controller"
    assert manifest["version"] == "10.0.1"
    assert manifest["integration_type"] == "device"
    assert "single_config_entry" not in manifest
    assert manifest["iot_class"] == "calculated"
    assert manifest["requirements"] == []
    assert manifest["documentation"].startswith(
        "https://github.com/denkz0ne/entity-controller"
    )
    assert manifest["issue_tracker"] == (
        "https://github.com/denkz0ne/entity-controller/issues"
    )
    assert manifest["codeowners"] == ["@denkz0ne"]
    assert "homeassistant" not in manifest
    assert manifest["config_flow"] is True

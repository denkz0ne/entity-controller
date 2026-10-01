from __future__ import annotations

import json
from pathlib import Path


def test_flat_controller_config_flow_has_clear_localized_add_and_edit_labels() -> None:
    expected = {
        "strings.json": ("Add controller", "Edit controller"),
        "en.json": ("Add controller", "Edit controller"),
        "sk.json": ("Pridať controller", "Upraviť controller"),
    }
    for filename, (add_label, edit_label) in expected.items():
        path = (
            Path("custom_components/entity_controller")
            / ("translations" if filename != "strings.json" else "")
            / filename
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["config"]["step"]["user"]["title"] == add_label
        assert data["options"]["step"]["init"]["title"] == edit_label
        assert "config_subentries" not in data

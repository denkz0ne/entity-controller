from __future__ import annotations

import json
from pathlib import Path


def test_flat_controller_config_flow_has_clear_localized_add_and_edit_labels() -> None:
    expected = {
        "strings.json": ("Add controller", "Edit controller"),
        "en.json": ("Add controller", "Edit controller"),
        "sk.json": ("Pridať ovládač", "Upraviť ovládač"),
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


def test_presence_configuration_has_labels_and_hold_semantics_in_all_locales() -> None:
    root = Path("custom_components/entity_controller")
    for path in (root / "strings.json", root / "translations/en.json", root / "translations/sk.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for category, step in (("config", "user"), ("options", "init")):
            sections = data[category]["step"][step]["sections"]
            assert sections["basic"]["data"]["presence_entities"]
            assert sections["basic"]["data_description"]["presence_entities"]
            assert sections["advanced"]["data"]["presence_on_states"]
            assert sections["advanced"]["data"]["presence_off_states"]

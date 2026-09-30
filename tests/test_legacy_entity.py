from __future__ import annotations

from custom_components.entity_controller.controller import ControllerRuntime
from custom_components.entity_controller.legacy_entity import LegacyEntityMirror
from custom_components.entity_controller.model import ControllerConfig, ControllerState


def test_legacy_entity_mirror_preserves_old_entity_id_and_runtime_state() -> None:
    runtime = ControllerRuntime(
        ControllerConfig(subentry_id="ec01_izba_pohyb", name="EC01 Izba pohyb")
    )
    runtime.state = ControllerState.BLOCKED

    mirror = LegacyEntityMirror(runtime)

    assert mirror.entity_id == "entity_controller.ec01_izba_pohyb"
    assert mirror.unique_id == "legacy_ec01_izba_pohyb"
    assert mirror.state == "blocked"
    assert mirror.extra_state_attributes["replacement_entity_id"] == (
        "sensor.ec01_izba_pohyb_state"
    )

from custom_components.entity_controller.model import (
    ControllerConfig,
    ControllerState,
    SensorType,
    TransitionBehavior,
)


def test_controller_state_values() -> None:
    assert {state.value for state in ControllerState} == {
        "idle",
        "active_timer",
        "active_stay_on",
        "blocked",
        "overridden",
        "constrained",
        "disabled",
    }


def test_pending_state_is_removed() -> None:
    assert "pending" not in {state.value for state in ControllerState}


def test_controller_config_defaults_match_v10_baseline() -> None:
    config = ControllerConfig(subentry_id="abc123", name="Hall")

    assert config.subentry_id == "abc123"
    assert config.name == "Hall"
    assert config.sensor_type is SensorType.EVENT
    assert config.delay_seconds == 180.0
    assert config.constraint_window is None
    assert config.night_mode is None
    assert config.service_data_on == {}
    assert config.service_data_off == {}
    assert config.trigger_on_states == ("on",)
    assert config.state_attributes_ignore == ()
    assert config.blocking_enabled is True
    assert config.transition_behaviors["on_enter_idle"] is TransitionBehavior.OFF
    assert config.transition_behaviors["on_enter_active"] is TransitionBehavior.ON

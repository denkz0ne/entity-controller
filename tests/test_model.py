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
    assert config.presence_entities == ()
    assert config.presence_on_states == ("on",)
    assert config.presence_off_states == ("off",)
    assert config.state_attributes_ignore == ()
    assert config.blocking_enabled is True
    assert config.protect_manual_off is True
    assert config.protect_manual_on is True
    assert config.transition_behaviors["on_enter_idle"] is TransitionBehavior.IGNORE
    assert config.transition_behaviors["on_enter_active"] is TransitionBehavior.ON
    assert config.transition_behaviors["on_exit_active"] is TransitionBehavior.OFF


def test_legacy_default_shutdown_migration_is_idempotent_and_preserves_other_hooks() -> None:
    from custom_components.entity_controller.model import normalize_transition_behaviors

    old = {"on_enter_idle": "off", "on_exit_active": "ignore", "on_enter_blocked": "custom"}
    migrated = normalize_transition_behaviors(old)
    assert old["on_enter_idle"] == "off"
    assert migrated["on_enter_idle"] is TransitionBehavior.IGNORE
    assert migrated["on_exit_active"] is TransitionBehavior.OFF
    assert migrated["on_enter_blocked"] is TransitionBehavior.CUSTOM
    assert normalize_transition_behaviors(migrated) == migrated


def test_lifecycle_migration_preserves_explicit_advanced_exit_and_idle_policies() -> None:
    from custom_components.entity_controller.model import normalize_transition_behaviors

    for idle, exit_policy in (("off", "custom"), ("on", "ignore"), ("ignore", "ignore"), ("off", "off")):
        result = normalize_transition_behaviors({"on_enter_idle": idle, "on_exit_active": exit_policy})
        assert result["on_enter_idle"].value == idle
        assert result["on_exit_active"].value == exit_policy

# Entity Controller v10 development

Entity Controller v10 targets Home Assistant 2026.9+ and uses one typed `ConfigEntry.runtime_data` manager per controller device, backed by an explicit async state machine.

## Current milestone: 10.0.0-rc.8

`10.0.0-rc.8` replaces the root/subentry tree with one config entry per
controller, organizes the controller form around the common motion-light
setup, and exposes localized native controller entities with runtime
diagnostics and a redacted config-entry diagnostics file.
Runtime diagnostics retain transition provenance separately from reconcile
reasons and do not add per-second countdown updates.

The RC configuration and runtime also cover time constraints, sunrise/sunset
offsets, night profiles, service data, timer backoff, block timeout, transition
behaviors, and custom state mappings.

Persistence is intentionally limited to Entity Controller-owned state: Enabled, Stay Mode, valid active timer expiry, and runtime timestamps. External Helper state stays owned by Home Assistant's Helper integrations.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

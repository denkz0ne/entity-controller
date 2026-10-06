# Svetlo v tme v10 development

Svetlo v tme v10 targets Home Assistant 2026.9+ and uses one typed `ConfigEntry.runtime_data` manager per controller device, backed by an explicit async state machine.

## Current stable release: 10.7.0

The v10 line uses one config entry per controller, localized native controller
entities, runtime diagnostics, and a redacted config-entry diagnostics file.
Runtime diagnostics retain transition provenance separately from reconcile
reasons and do not add per-second countdown updates.

The configuration and runtime also cover time constraints, sunrise/sunset
offsets, night profiles, service data, timer backoff, block timeout, transition
behaviors, and custom state mappings.

Persistence is intentionally limited to Svetlo v tme-owned state: Enabled, Stay Mode, valid active timer expiry, and runtime timestamps. External Helper state stays owned by Home Assistant's Helper integrations.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

# Entity Controller v10 development

Entity Controller v10 targets Home Assistant 2026.9+ and is being rebuilt around Config Entries, Config Subentries, typed `ConfigEntry.runtime_data`, and an explicit async state machine.

## Current milestone: 10.0.0-beta.1

`10.0.0-beta.1` contains the typed integration skeleton, standalone async FSM core, structured schedule parsing/window evaluation, bounded HA Context tracking, cancellable timer/backoff logic, controller manager lifecycle, live listener routing, startup/reconfigure reconcile, hot per-controller reconfiguration, initial native controller entities/actions, root Config Entry plus controller Config Subentry flow surface with EN/SK strings, controlled v9 YAML migration importer/legacy mirror, controller-owned restore state helpers, diagnostics, and guide-only migration Repairs.

Persistence is intentionally limited to Entity Controller-owned state: Enabled, Stay Mode, valid active timer expiry, and runtime timestamps. External Helper state stays owned by Home Assistant's Helper integrations.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

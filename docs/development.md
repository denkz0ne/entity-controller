# Entity Controller v10 development

Entity Controller v10 targets Home Assistant 2026.9+ and is being rebuilt around Config Entries, Config Subentries, typed `ConfigEntry.runtime_data`, and an explicit async state machine.

## Current milestone: 10.0.0-rc.2

`10.0.0-rc.2` connects the previously isolated v10 building blocks to Home Assistant: subentries load as live controllers, platforms register native entities, transitions call Home Assistant services with owned contexts, timers use the HA event loop, runtime switches persist, and the Helpers settings action opens a valid add-controller flow.

Persistence is intentionally limited to Entity Controller-owned state: Enabled, Stay Mode, valid active timer expiry, and runtime timestamps. External Helper state stays owned by Home Assistant's Helper integrations.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

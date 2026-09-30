# Entity Controller v10 development

Entity Controller v10 targets Home Assistant 2026.9+ and is being rebuilt around Config Entries, Config Subentries, typed `ConfigEntry.runtime_data`, and an explicit async state machine.

## Alpha 1 scope

`10.0.0-alpha.1` introduces the typed integration skeleton only. It is not migration-ready and does not yet expose the configuration UI. The legacy `transitions` dependency is removed from the new runtime architecture.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

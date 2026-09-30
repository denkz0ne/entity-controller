# Entity Controller v10 development

Entity Controller v10 targets Home Assistant 2026.9+ and is being rebuilt around Config Entries, Config Subentries, typed `ConfigEntry.runtime_data`, and an explicit async state machine.

## Current milestone: 10.0.0-alpha.2

`10.0.0-alpha.2` contains the typed integration skeleton plus the standalone async FSM core, structured schedule parsing/window evaluation, bounded HA Context tracking, and cancellable timer/backoff logic. Live entity listeners, UI configuration, native controller entities, and migration are intentionally later milestones.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

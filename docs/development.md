# Entity Controller v10 development

Entity Controller v10 targets Home Assistant 2026.9+ and is being rebuilt around Config Entries, Config Subentries, typed `ConfigEntry.runtime_data`, and an explicit async state machine.

## Current milestone: 10.0.0-rc.5

`10.0.0-rc.5` keeps the native single root and reorganizes the controller
form around the common motion-light setup. The advanced behavior remains
available in collapsed sections with selector translations and Slovak hints.

The RC configuration and runtime also cover time constraints, sunrise/sunset
offsets, night profiles, service data, timer backoff, block timeout, transition
behaviors, and custom state mappings.

Persistence is intentionally limited to Entity Controller-owned state: Enabled, Stay Mode, valid active timer expiry, and runtime timestamps. External Helper state stays owned by Home Assistant's Helper integrations.

The v10 work is developed on the `v10-modernization` branch. Release milestones, migration requirements, and behavioral compatibility rules are defined in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

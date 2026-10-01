# Entity Controller v10 release checklist

## Migration rehearsal

- Rehearse v9.7.6 -> v10 with a legacy YAML fixture.
- Import legacy YAML into one config entry per controller.
- Restart once with legacy YAML still present and confirm no duplicate controller entries or devices.
- Validate migrated controllers, then remove YAML manually.
- Restart again and confirm each controller Config Entry remains authoritative.

## EC01-EC11 smoke matrix

- EC01: state/history sensor exposes the exact FSM state.
- EC02: native Enabled switch disables decisions without turning controlled loads off.
- EC03: native Blocked sensor exposes reason and source.
- EC04: native Stay switch persists stay state.
- EC05: Activate button moves the controller into active behavior.
- EC06: multi-trigger controllers route every trigger to the same runtime.
- EC07: external helper rules update assigned controllers immediately.
- EC08: override/interlock Helpers remain ordinary Home Assistant entities.
- EC09: legacy state mirror preserves old `entity_controller.<object_id>` compatibility.
- EC10: migrated config restarts without duplicate callbacks or stale timers.
- EC11: the native sidebar lists every configured controller, controls its native Enabled switch, updates live, and renders the recorded 24-hour state timeline.

## Validation gates

- Ruff passes on the maintained v10 runtime and test surface.
- Pytest passes for the maintained v10 suite from a clean config fixture.
- Pytest passes for the maintained v10 suite from a migrated config fixture.
- HACS metadata advertises the Home Assistant 2026.9 floor.
- HACS marketplace validation remains required before stable release.
- Hassfest validation remains required in a real Home Assistant 2026.9 integration environment.

## known limitations

- GitHub Actions do not pin Home Assistant to the 2026.9 minimum, so the release still needs a smoke test on that supported version.
- Migration Repairs are guide-only; Entity Controller never deletes Helpers or rewrites/removes YAML.
- The legacy state mirror is transitional compatibility and should remain documented until stable migration feedback is clean.

# Entity Controller v10 release checklist

## Migration rehearsal

- Rehearse v9.7.6 -> v10 with a legacy YAML fixture.
- Import legacy YAML into controller subentry data.
- Restart once with legacy YAML still present and confirm no duplicate controller subentries.
- Validate migrated controllers, then remove YAML manually.
- Restart again and confirm the Config Entry remains authoritative.

## EC01-EC10 smoke matrix

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

## Validation gates

- Ruff passes on the maintained v10 runtime and test surface.
- Pytest passes for the maintained v10 suite from a clean config fixture.
- Pytest passes for the maintained v10 suite from a migrated config fixture.
- HACS metadata advertises the Home Assistant 2026.9 floor.
- HACS marketplace validation remains required before stable release.
- Hassfest validation remains required in a real Home Assistant 2026.9 integration environment.

## known limitations

- Current GitHub Actions install Home Assistant 2025.1.4, so Config Subentry behavior still needs real Home Assistant 2026.9 smoke validation.
- Migration Repairs are guide-only; Entity Controller never deletes Helpers or rewrites/removes YAML.
- The legacy state mirror is transitional compatibility and should remain documented until stable migration feedback is clean.
- Old v9 tests remain in the repository for reference but are not part of the maintained v10 CI surface.

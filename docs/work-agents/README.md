# Entity Controller v10 RC polish — work-agent roadmap

These tasks are intentionally split so a Work/Codex agent can implement, test, and review one concern at a time. Do not collapse them into one broad “UI polish” change.

Source baseline when the roadmap was created: `10.0.0-rc.3`, commit `86893e7`. User-facing source-derived references are in:

- `docs/configuration.md`
- `docs/behavior.md`
- `docs/entities.md`

## Recommended execution order

1. [#1 — Single-root integration UX and Add Controller flow](https://github.com/denkz0ne/entity-controller/issues/1) — [task brief](01-single-root-and-add-controller.md)
2. [#2 — Configurator information architecture, Slovak copy, and hints](https://github.com/denkz0ne/entity-controller/issues/2) — [task brief](02-configurator-ui-and-slovak-copy.md)
3. [#3 — Native entity IDs, localized names, and per-function icons](https://github.com/denkz0ne/entity-controller/issues/3) — [task brief](03-entity-naming-localization-icons.md)
4. [#4 — Runtime diagnostics and rich entity attributes](https://github.com/denkz0ne/entity-controller/issues/4) — [task brief](04-runtime-diagnostics-attributes.md)
5. [#5 — Interlock / blocked semantics and source tracking](https://github.com/denkz0ne/entity-controller/issues/5) — [task brief](05-interlock-blocked-semantics.md)
6. [#6 — Explicit ON/OFF state mappings](https://github.com/denkz0ne/entity-controller/issues/6) — [task brief](06-explicit-state-mappings.md)
7. [#7 — FSM edge cases: constraints, Activate, and Stay Mode](https://github.com/denkz0ne/entity-controller/issues/7) — [task brief](07-fsm-edge-cases.md)
8. [#8 — Integration branding and icon assets](https://github.com/denkz0ne/entity-controller/issues/8) — [task brief](08-branding-icon.md)

Tasks 1–4 are mostly UX/observability work. Tasks 5–7 change runtime behavior and require focused regression tests. Task 8 is independent except that its final asset location should match the release/distribution method selected for the custom integration.

## Working rules

- Work on `v10-modernization` or a short-lived branch based on it.
- One task = one focused PR/commit series when practical.
- Read current source before changing behavior; the docs explicitly call out known RC.3 gaps.
- Add tests before/with every behavior fix.
- Do not replace native Home Assistant UI with a custom frontend solely to change labels/layout.
- Keep one root Config Entry and controller Config Subentries.
- External Helpers stay ordinary Home Assistant entities. EC only references them per controller; it does not own global guest/holiday/manual-block helpers.
- Reconfiguration must not replay ON/OFF actions merely because config was rebuilt.
- Update `CHANGELOG.md` and relevant docs with every RC that changes behavior or UI.

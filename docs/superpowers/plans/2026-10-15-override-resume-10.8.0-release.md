# Override Resume + 10.8.0 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement issue #37 so Override always suppresses EC-controlled outputs and resumes from current live conditions, then ship the currently unreleased v10 branch changes as Svetlo v tme 10.8.0.

**Architecture:** Keep `ControllerRuntime` as the FSM owner and `EntityControllerManager` as the Home Assistant state/service adapter. Add a dedicated Override enter/resume path: Override entry bypasses generic Active-exit restore semantics and forces EC outputs OFF; last-Override release evaluates a fresh `ReconcileSnapshot` and performs the required live transition, including immediate reactivation when current trigger/presence state warrants it. Persistent startup/reconfigure reconcile remains side-effect-free.

**Tech Stack:** Python 3.14, Home Assistant 2026.9+, pytest/pytest-asyncio, Ruff, Home Assistant WebSocket/frontend assets, GitHub Actions.

**Spec:** GitHub issue #37 — https://github.com/denkz0ne/entity-controller/issues/37

## Global Constraints

- Override suppression is fixed behavior for every controller; do not add a per-controller disable option.
- Any active Override keeps EC-controlled outputs suppressed.
- Only clearing the final active Override may resume controller output.
- Resume uses current enabled/constraint/interlock/manual/trigger/presence/profile state, never a stale output snapshot.
- Startup, migration, and hot reconfigure remain side-effect-free.
- Generic lifecycle Restore/Leave-unchanged behavior must never defeat Override suppression.
- Existing entity IDs, unique IDs, ConfigEntry/Subentry storage, and migration identity remain stable.
- Release version is `10.8.0`.
- Include the nine commits already present on `v10-modernization` after `v10.7.0` (timeline Recorder decoding and restart/session restoration) in the release validation and notes.

## Review Focus

- Active controller using Restore-on-exit enters Override: no temporary restore may leave the controlled light ON; final result must be OFF.
- Two Override inputs overlap: clearing one must not resume while the other remains ON.
- Last Override clears while PIR is still ON or a previously active room is held by Presence: EC resumes without a fresh PIR edge.
- Last Override clears while constrained/interlocked/manual-takeover is active: EC remains suppressed in the correct higher-priority state.
- HA startup/reconfigure with Override already ON: no service-call oscillation; a later real Override-OFF event performs normal live resume.

---

### Task 1: Lock Override semantics with failing regression tests

**Files:**
- Modify: `tests/test_controller_fsm.py`
- Modify: `tests/test_manager.py`
- Modify: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: existing `ControllerRuntime.async_handle_override_change(...)`, `ReconcileSnapshot`, manager Override listener and service-call recorder.
- Produces: tests defining the invariant before runtime code changes.

- [ ] **Step 1: Add FSM tests for entering Override from ACTIVE**

Add tests asserting:
- ACTIVE -> Override returns `OVERRIDDEN`.
- Override entry never runs the generic Active-exit Restore/Leave policy as the final output policy.
- repeated Override-ON while already `OVERRIDDEN` is idempotent.

- [ ] **Step 2: Add manager/service tests for forced suppression**

Add a test with `light.night` controlled and `light.ceiling` as Override:
1. motion activates `light.night`;
2. Override ON;
3. latest EC service action for `light.night` is `turn_off`.

Add mixed/multiple controlled-output coverage so all configured outputs are suppressed.

- [ ] **Step 3: Add overlapping Override tests**

With two Override entities:
- first ON enters Override;
- second ON leaves state unchanged;
- first OFF while second remains ON does not run activation;
- final OFF is the only edge allowed to resume.

- [ ] **Step 4: Add live-resume tests**

Cover last Override OFF when:
- PIR is currently ON -> immediate ACTIVE + `turn_on` without a new PIR edge;
- no trigger/presence is active -> IDLE/OFF;
- constraint is active -> CONSTRAINED/OFF;
- interlock is active -> BLOCKED/OFF;
- manual takeover is pending -> BLOCKED/OFF;
- presence is active and the room was active before Override -> resume active session without a new PIR edge.

- [ ] **Step 5: Add startup/reconfigure safety regression**

Assert startup/reconfigure reconcile into `OVERRIDDEN` executes no output service call, but a later real last-Override-OFF event can perform live resume.

- [ ] **Step 6: Run focused tests and confirm current code fails the new assertions**

Run:
```bash
pytest -q tests/test_controller_fsm.py tests/test_manager.py tests/test_lifecycle.py
```
Expected: new Override suppression/resume assertions fail before implementation.

- [ ] **Step 7: Commit tests**

Commit message:
```
test: define override suppression and live resume semantics
```

### Task 2: Implement dedicated Override enter/resume behavior

**Files:**
- Modify: `custom_components/entity_controller/controller.py`
- Modify: `custom_components/entity_controller/manager.py`

**Interfaces:**
- Consumes: `ReconcileSnapshot`, `TransitionCause.OVERRIDE`, existing behavior executor, lifecycle session callbacks, manager `_snapshot(...)`.
- Produces:
  - `ControllerRuntime.async_resume_after_override(snapshot: ReconcileSnapshot, *, source_entity_id: str | None = None) -> ControllerState`
  - deterministic Override suppression on real Override-ON transitions.

- [ ] **Step 1: Add Override runtime bookkeeping**

Add runtime fields with stable meanings:
- `override_started_at: datetime | None`
- `last_override_cleared_at: datetime | None`
- `override_resume_reason: str | None`
- `override_suspended_active: bool` (or equivalent private/session flag) to remember whether Presence may resume a room that was active before Override.

Do not use this flag to restore stale output state; it only preserves activity-session eligibility for Presence semantics.

- [ ] **Step 2: Special-case real Override entry**

When a real Override-ON edge transitions into `OVERRIDDEN`:
- remember whether the source state was active;
- cancel active timers as today;
- discard/close EC-owned output snapshots without performing generic Active-exit Restore that could re-enable the suppressed output;
- allow any configured advanced Override hook to run if supported;
- finally force all normal EC-controlled outputs OFF through the existing behavior/service adapter;
- set Override provenance/timestamps.

Do not repeat forced OFF on every additional Override-ON event while already `OVERRIDDEN`.

- [ ] **Step 3: Implement `async_resume_after_override(...)`**

Exact signature:
```python
async def async_resume_after_override(
    self,
    snapshot: ReconcileSnapshot,
    *,
    source_entity_id: str | None = None,
) -> ControllerState:
```

Behavior:
- apply the fresh snapshot;
- determine target with normal priority ordering;
- permit Presence to resume ACTIVE only when the room had an active session before Override;
- if target is ACTIVE, use a real transition so enter-active behavior runs and outputs turn ON;
- otherwise transition/reconcile to the correct disabled/constrained/blocked/idle state without inventing activation;
- clear `overridden_by` after successful release;
- set `last_override_cleared_at` and a deterministic `override_resume_reason`.

- [ ] **Step 4: Route manager Override listener through fresh snapshots**

In `EntityControllerManager._override_listener`:
- keep current ANY-active calculation and `active_overrides`;
- Override ON -> normal runtime enter path;
- clearing one of several overrides -> remain overridden with no resume call;
- final Override OFF -> create a fresh `_snapshot(runtime.config, enabled=runtime.enabled)` after the HA state change and call `async_resume_after_override(...)`.

Do not infer resume from stale `state_entities_on` alone.

- [ ] **Step 5: Run focused regression suite**

Run:
```bash
pytest -q tests/test_controller_fsm.py tests/test_manager.py tests/test_lifecycle.py
```
Expected: PASS.

- [ ] **Step 6: Commit runtime implementation**

Commit message:
```
feat: suppress outputs during override and resume live conditions
```

### Task 3: Expose Override diagnostics without UI noise

**Files:**
- Modify: `custom_components/entity_controller/sensor.py`
- Modify: `custom_components/entity_controller/diagnostics.py`
- Modify: `custom_components/entity_controller/panel.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_panel.py`

**Interfaces:**
- Consumes: runtime fields from Task 2.
- Produces diagnostic attributes/serialized panel fields:
  - `override_started_at`
  - `last_override_cleared_at`
  - `override_resume_reason`
  - existing `active_overrides` remains authoritative.

- [ ] **Step 1: Add diagnostics tests**

Assert the new fields are present and JSON-safe in config-entry diagnostics and controller State attributes.

- [ ] **Step 2: Add panel serialization regression**

Assert serialized controller data exposes active overrides plus the three new diagnostic fields without changing the normal row structure.

- [ ] **Step 3: Implement diagnostic exposure**

Add the new values to State sensor attributes, diagnostics output, and panel controller serialization. Keep them read-only and avoid new entities.

- [ ] **Step 4: Run diagnostics/panel tests**

Run:
```bash
pytest -q tests/test_diagnostics.py tests/test_entities.py tests/test_panel.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message:
```
feat: expose override suppression and resume diagnostics
```

### Task 4: Document behavior and prepare 10.8.0

**Files:**
- Modify: `docs/behavior.md`
- Modify: `docs/configuration.md` if Override help text is documented there
- Modify: `CHANGELOG.md`
- Modify: `custom_components/entity_controller/manifest.json`
- Modify: `custom_components/entity_controller/panel.py`
- Modify: `tests/test_release_gate.py`
- Modify: `tests/test_panel.py` if panel asset version is asserted

**Interfaces:**
- Consumes: completed behavior from Tasks 1–3.
- Produces release metadata for `10.8.0`.

- [ ] **Step 1: Document fixed Override semantics**

Document:
- any Override ON suppresses EC outputs;
- multiple Override inputs use ANY-active semantics;
- final OFF re-evaluates live conditions;
- no fresh trigger edge is required when current PIR/presence already warrants activation;
- Override differs from Interlock and Manual takeover;
- startup/reconfigure remain side-effect-free.

- [ ] **Step 2: Add 10.8.0 changelog entry**

Include:
- Override suppression/live resume (#37);
- Recorder compressed-history/timeline fix already ahead of v10.7.0;
- restart/session restoration fix already ahead of v10.7.0.

- [ ] **Step 3: Bump release metadata**

Set:
- manifest `version` -> `10.8.0`;
- panel asset/cache version -> a `10.8.0-...` value;
- release-gate test expected version -> `10.8.0`.

- [ ] **Step 4: Run release metadata tests**

Run:
```bash
pytest -q tests/test_manifest.py tests/test_release_gate.py tests/test_repository_metadata.py tests/test_panel.py
```
Expected: PASS.

- [ ] **Step 5: Commit release preparation**

Commit message:
```
chore: prepare Svetlo v tme 10.8.0
```

### Task 5: Full validation, PR, issue closure, and release

**Files:**
- No product files unless validation finds a regression.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: merged release-ready branch, closed #37, tag/release `v10.8.0`.

- [ ] **Step 1: Run full local validation**

Run project-standard commands from the workflow, including:
```bash
pytest -q
ruff check .
```
and the browser/panel suite command used by `.github/workflows/v10-modernization.yml`.

Expected: all tests and lint pass.

- [ ] **Step 2: Compare release range**

Verify `v10.7.0...HEAD` contains only intended unreleased changes plus #37/release-prep changes. Confirm no unexpected version/name regression.

- [ ] **Step 3: Open PR against `v10-modernization`**

PR title:
```
10.8.0: deterministic Override suppression and live resume
```

PR body must summarize #37, the two previously unreleased fixes, tests, and release version.

- [ ] **Step 4: Wait for GitHub Actions and inspect failures**

Require all configured backend/browser/repository jobs green. If a job fails, diagnose the actual failure, fix it, rerun focused tests, and push the correction before merge.

- [ ] **Step 5: Merge PR only after green CI**

Use normal repository merge method. Record final merge SHA.

- [ ] **Step 6: Close #37**

Close only after the merged SHA contains the tested implementation. Add a closing comment with:
- behavior summary;
- PR number;
- final SHA;
- validation result;
- release target `v10.8.0`.

- [ ] **Step 7: Create stable release `v10.8.0`**

Release name:
`Svetlo v tme 10.8.0`

Release notes should highlight:
- large/override light immediately suppresses the EC-controlled night light;
- when the last Override clears, current PIR/presence/rules are re-evaluated immediately and the EC light resumes if still required;
- fixes for 24h Recorder timeline decoding;
- restart/session restoration without false manual blocking;
- no configuration migration required.

- [ ] **Step 8: Post-release verification**

Verify:
- release/tag points to the merged 10.8.0 SHA;
- manifest at the tag reports `10.8.0`;
- #37 is closed;
- repository has no remaining open implementation issue intended for this release;
- HACS-visible release metadata is structurally consistent with prior stable releases.

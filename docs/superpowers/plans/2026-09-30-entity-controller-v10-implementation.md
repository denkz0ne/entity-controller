# Entity Controller v10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite Entity Controller as a modern Home Assistant 2026.9+ integration with Config Entries/Subentries, native controller entities, hot reconfiguration, preserved FSM behavior, and safe migration from v9 YAML.

**Architecture:** One root `ConfigEntry[EntityControllerManager]` owns multiple controller `ConfigSubentry` objects. Each subentry owns one `ControllerRuntime` and one virtual device. FSM, schedules, context handling, persistence, entities, config flow, migration, diagnostics and Repairs live in focused modules. External Helpers remain normal Home Assistant entities selected per controller rule; EC never globally registers or owns them.

**Tech Stack:** Python 3, Home Assistant Core 2026.9+ APIs, Config Entries + Config Subentries, typed `ConfigEntry.runtime_data`, HA async event/time helpers, pytest, Ruff, Hassfest/HACS validation, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-entity-controller-v10-modernization-design.md`

## Global Constraints

- Product/domain stay `Entity Controller` / `entity_controller` for v10.
- Minimum Home Assistant: 2026.9+.
- Use current Config Entry/Subentry APIs and typed `ConfigEntry.runtime_data`.
- Device ownership uses `config_entry_id` + `config_subentry_id`; no deprecated multi-entry registry properties.
- Reconfigure uses `async_update_and_abort()` semantics; do not combine update listeners with reload helpers.
- No `threading.Timer`, `asyncio.run_coroutine_threadsafe`, or `transitions` dependency.
- Startup, restore, migration and reconfigure use reconcile; they must not execute ON/OFF transition behavior just because runtime/configuration was rebuilt.
- External entities such as `input_boolean.navsteva_block` and `input_boolean.izba_block` remain ordinary HA entities selected per controller as override/interlock/rule inputs. No EC-owned global interlock layer and no native persistent Manual Block switch.
- Migration from v9 YAML is required before stable v10.
- EC never deletes Helpers or rewrites `ec.yaml`; migration reports and Repairs guide cleanup.
- Every prerelease/stable version updates manifest version, `CHANGELOG.md`, affected docs, migration notes when needed, tests, and gets its own meaningful commit.
- English and Slovak UI translations ship with v10.

## Review Focus

1. Restart with controlled light already ON must not trigger `on_enter_idle=off`.
2. Missing/unavailable configured entity must affect only its controller, not unload all EC.
3. Shortening delay/block timeout past current expiry must evaluate once, without stale callback duplication.
4. Legacy YAML left in place after import must not create duplicate controller subentries on restart.
5. External helper changes must affect assigned controllers immediately while EC never creates, converts, renames or deletes that helper.

---

## Version map

- `10.0.0-alpha.1` — modern integration skeleton + typed model.
- `10.0.0-alpha.2` — explicit FSM, schedules, async timers, backoff, contexts.
- `10.0.0-alpha.3` — manager/listeners, reconcile, hot reconfigure.
- `10.0.0-alpha.4` — native controller devices/entities + actions.
- `10.0.0-alpha.5` — Config Entry/Subentry UI + EN/SK.
- `10.0.0-alpha.6` — v9 YAML migration + compatibility mirror + migration report/Repairs; first controlled migration build.
- `10.0.0-beta.1` — persistence, diagnostics, full parity/regression suite.
- `10.0.0-beta.2` — CI/HACS/repository/docs modernization.
- `10.0.0-rc.1` — real migration/smoke stabilization.
- `10.0.0` — stable only after RC has no migration blocker.

---

### Task 1: Modern integration skeleton — `10.0.0-alpha.1`

**Files:**
- Modify: `custom_components/entity_controller/manifest.json`
- Modify: `custom_components/entity_controller/const.py`
- Rewrite: `custom_components/entity_controller/__init__.py`
- Create: `custom_components/entity_controller/model.py`
- Create: `custom_components/entity_controller/manager.py`
- Create: `tests/test_init.py`
- Create: `tests/test_model.py`
- Modify: `CHANGELOG.md`
- Create: `docs/development.md`

**Interfaces:**
- `type EntityControllerConfigEntry = ConfigEntry[EntityControllerManager]`
- enums: `ControllerState`, `SensorType`, `TransitionCause`, `TransitionBehavior`, `ReconcileReason`
- typed `ControllerConfig`
- `EntityControllerManager(hass: HomeAssistant, entry: EntityControllerConfigEntry)`

- [ ] **Step 1: Write failing setup/model tests**

```python
def test_controller_state_values():
    assert {s.value for s in ControllerState} == {
        "idle", "active_timer", "active_stay_on",
        "blocked", "overridden", "constrained", "disabled",
    }

async def test_setup_entry_stores_manager(hass, config_entry):
    assert await async_setup_entry(hass, config_entry)
    assert isinstance(config_entry.runtime_data, EntityControllerManager)
```

Also assert `pending` is gone and `transitions` is no longer a runtime requirement.

- [ ] **Step 2: Run** `pytest tests/test_model.py tests/test_init.py -v` and confirm FAIL.
- [ ] **Step 3: Implement typed skeleton, root setup/unload, manifest `10.0.0-alpha.1`, HA floor `2026.9.0`, remove `transitions==0.8.8`.
- [ ] **Step 4: Re-run targeted tests; expect PASS.**
- [ ] **Step 5: Update changelog/development doc and commit** `feat: start Entity Controller v10 architecture`.

---

### Task 2: Explicit FSM core — `10.0.0-alpha.2` part A

**Files:**
- Create: `custom_components/entity_controller/controller.py`
- Modify: `custom_components/entity_controller/model.py`
- Create: `tests/test_controller_fsm.py`
- Port behavioral assertions from current `tests/test_lightingsm*.py` / AppDaemon-era tests.

**Interfaces:**
- `ControllerRuntime.async_transition(target: ControllerState, cause: TransitionCause, *, source_entity_id: str | None = None) -> bool`
- `ControllerRuntime.async_reconcile(reason: ReconcileReason) -> ControllerState`

- [ ] **Step 1: Write failing tests** for idle→active timer, retrigger reset, duration sensor ON/OFF, manual state change→blocked, override enter/leave, stay mode, invalid transition, and reconcile-without-enter-action.
- [ ] **Step 2: Run** `pytest tests/test_controller_fsm.py -v`; expect FAIL.
- [ ] **Step 3: Implement one explicit typed transition path; separate state calculation from action side effects.**
- [ ] **Step 4: Re-run; expect PASS.**
- [ ] **Step 5: Commit** `feat: add explicit v10 controller state machine`.

---

### Task 3: Async timers, schedule, backoff, context — `10.0.0-alpha.2` part B

**Files:**
- Create: `custom_components/entity_controller/schedule.py`
- Create: `custom_components/entity_controller/context.py`
- Modify: `controller.py`, `model.py`
- Create: `tests/test_schedule.py`, `tests/test_timer_backoff.py`, `tests/test_context.py`
- Modify: `CHANGELOG.md`, manifest version.

**Interfaces:**
- typed `SchedulePoint` for fixed time/sunrise/sunset + offset
- schedule window evaluation and cancellable boundary callbacks
- controller-owned context tracker: create context + identify own EC actions

- [ ] **Step 1: Write failing tests** for midnight crossing, sunset offset conversion, backoff factor/max, duration sensor ignoring expiry while ON, stale/cancelled timer callbacks, own-context recognition.
- [ ] **Step 2: Run targeted tests; expect FAIL.**
- [ ] **Step 3: Implement using current HA async event/time helpers only; legacy free-form schedule parser exists only for migration conversion.**
- [ ] **Step 4: Re-run; expect PASS.**
- [ ] **Step 5: Set `10.0.0-alpha.2`, update changelog, commit** `feat: complete async v10 runtime core`.

---

### Task 4: Manager, listeners and reconcile — `10.0.0-alpha.3` part A

**Files:**
- Modify: `manager.py`, `controller.py`, `__init__.py`
- Create: `tests/test_manager.py`, `tests/test_reconcile.py`

**Interfaces:**
- `EntityControllerManager.async_add_controller(subentry) -> ControllerRuntime`
- `EntityControllerManager.async_remove_controller(subentry_id: str) -> None`
- `EntityControllerManager.async_update_controller(subentry) -> None`
- `ControllerRuntime.async_start()` / `async_stop()`

- [ ] **Step 1: Write failing tests** for restart with controlled entity ON (no forced OFF), multiple triggers, external helper update, unavailable trigger isolation, complete callback cleanup.
- [ ] **Step 2: Run** `pytest tests/test_manager.py tests/test_reconcile.py -v`; expect FAIL.
- [ ] **Step 3: Implement listener lifecycle, ignored attributes/context filtering, isolated controller errors.**
- [ ] **Step 4: Re-run; expect PASS.**
- [ ] **Step 5: Commit** `feat: add controller manager and reconcile lifecycle`.

---

### Task 5: Hot reconfiguration — `10.0.0-alpha.3` part B

**Files:**
- Modify: `manager.py`, `controller.py`
- Create: `tests/test_reconfigure.py`
- Modify: manifest version, changelog.

**Interface:**
- `ControllerRuntime.async_apply_config(new_config: ControllerConfig) -> None`

- [ ] **Step 1: Write failing tests** for shortening active delay, new expiry already elapsed, block timeout already elapsed, add/remove trigger, helper newly selected while currently ON, changed constraint, and no reconfigure-induced idle OFF action.
- [ ] **Step 2: Run** `pytest tests/test_reconfigure.py -v`; expect FAIL.
- [ ] **Step 3: Implement diff-based update.** Recalculate from original timestamps; cancel old callbacks before replacement and reject stale callbacks via generation/token guard.
- [ ] **Step 4: Re-run; expect PASS.**
- [ ] **Step 5: Set `10.0.0-alpha.3`, document hot update, commit** `feat: hot reconfigure individual controllers`.

---

### Task 6: Native controller entities and actions — `10.0.0-alpha.4`

**Files:**
- Create: `entity.py`, `sensor.py`, `binary_sensor.py`, `switch.py`, `button.py`, `actions.py`
- Rewrite/remove old `entity_services.py` only after replacement tests pass
- Rewrite: `services.yaml`
- Modify: `__init__.py`
- Create: `tests/test_entities.py`, `tests/test_services.py`
- Create: `docs/entities.md`
- Modify: changelog/version.

**Primary controller entities:**
- state enum sensor
- Enabled switch
- Stay Mode switch
- Blocked binary sensor
- Activate button

**Optional/disabled-by-default:** timer expiry, last trigger, last transition, Clear Block button where meaningful.

**Explicit non-entity:** there is no persistent native `manual_block` switch. User-created Helpers remain external rule inputs.

- [ ] **Step 1: Write failing tests** for correct device/subentry ownership, stable unique IDs, exact FSM states, Enabled OFF not turning loads off, Stay persistence hook, Blocked sensor reason/source, Activate button, disabled-by-default diagnostics.
- [ ] **Step 2: Add service tests** for `activate`, `clear_block`, `enable_block`, `enable_stay_mode`, `disable_stay_mode`, `set_night_mode` compatibility where meaningful.
- [ ] **Step 3: Run targeted tests; expect FAIL.**
- [ ] **Step 4: Implement current HA entity/device APIs; never read deprecated `DeviceEntry.config_entries*` properties.**
- [ ] **Step 5: Re-run; expect PASS.**
- [ ] **Step 6: Set `10.0.0-alpha.4`, update entity docs/changelog, commit** `feat: expose native Entity Controller devices and entities`.

---

### Task 7: Config Entry/Subentry UI — `10.0.0-alpha.5`

**Files:**
- Create: `config_flow.py`, `strings.json`, `translations/en.json`, `translations/sk.json`
- Modify: `manifest.json`
- Create: `tests/test_config_flow.py`, `tests/test_subentry_flow.py`
- Create: `docs/configuration.md`
- Modify: changelog.

**Interfaces:**
- one root EC Config Entry
- `controller` Config Subentry flow for add + reconfigure
- reconfigure persists with `async_update_and_abort()` and runtime listener; no flow reload helper

**UI sections:** identity, triggers, control/state entities, timer, blocking behavior, external override/interlock/rule inputs, constraints, day/night profile, stay, transition actions, advanced mappings.

- [ ] **Step 1: Write failing tests** for single root entry, adding basic motion controller, reconfigure without root reload, external Helper selection, and basic flow without advanced fields.
- [ ] **Step 2: Run** `pytest tests/test_config_flow.py tests/test_subentry_flow.py -v`; expect FAIL.
- [ ] **Step 3: Implement native selectors/sections and action selector support; do not depend on deprecated Advanced Mode gating.**
- [ ] **Step 4: Validate EN/SK flow strings and tests; expect PASS.**
- [ ] **Step 5: Set `10.0.0-alpha.5`, update docs/changelog, commit** `feat: add native Entity Controller configuration UI`.

---

### Task 8: v9 YAML migration + compatibility bridge — `10.0.0-alpha.6`

**Files:**
- Create: `migration.py`
- Modify: `config_flow.py`, `__init__.py`
- Create: `legacy_entity.py` if isolating the old-domain state mirror simplifies lifecycle
- Create: `tests/fixtures/legacy_ec.yaml`, `tests/test_migration.py`, `tests/test_legacy_entity.py`
- Create: `docs/migration-v9-to-v10.md`
- Modify: changelog/version.

**Interfaces:**
- typed `MigrationReport`: imported controllers, warnings, legacy→new entity map, cleanup guidance
- one v9 controller → one `controller` Config Subentry
- imported controllers keep transitional `entity_controller.<legacy_object_id>` state compatibility mirror
- configured external Helper/entity references are preserved unchanged

- [ ] **Step 1: Build failing migration fixture** covering multiple controllers, multi-trigger, event+duration, state entities, override/helper inputs, night mode, constraints, backoff, state maps and behaviors.
- [ ] **Step 2: Assert** one subentry/controller, idempotent restart with YAML still present, structured schedule conversion, no control side effects, unknown-field warning, legacy state mirror.
- [ ] **Step 3: Assert external Helpers are references only:** `input_boolean.navsteva_block`/`izba_block` are not converted, duplicated, renamed or deleted and no global EC interlock object exists.
- [ ] **Step 4: Run migration tests; expect FAIL.**
- [ ] **Step 5: Implement importer + compatibility mirror + migration report.** Map every legacy key named in the spec; unsupported values report explicitly.
- [ ] **Step 6: Add EC01–EC10 dashboard-derived fixture assertions**, including Vchod motion+door and the same external helper assigned to multiple controllers.
- [ ] **Step 7: Run migration + FSM/reconcile regression suite; expect PASS.**
- [ ] **Step 8: Set `10.0.0-alpha.6`, mark as controlled migration-test build, update docs/changelog, commit** `feat: migrate legacy Entity Controller YAML to v10`.

---

### Task 9: Persistence, diagnostics and Repairs — `10.0.0-beta.1`

**Files:**
- Create: `storage.py` only if entity restore/config-entry state is insufficient
- Create: `diagnostics.py`, `repairs.py`
- Modify: `controller.py`
- Create: `tests/test_persistence.py`, `tests/test_diagnostics.py`, `tests/test_repairs.py`
- Create: `docs/troubleshooting.md`
- Modify: changelog/version.

**Persistence:** controller-owned Enabled + Stay Mode states and semantically valid runtime timestamps only. External Helper state belongs to the Helper integration, not EC.

- [ ] **Step 1: Write failing tests** for restart with active timer, Enabled/Stay restore, unavailable entity recovery, legacy-YAML Repair idempotency, migration warnings, diagnostics redaction/stability.
- [ ] **Step 2: Run targeted tests; expect FAIL.**
- [ ] **Step 3: Implement persistence without replaying old transition side effects; Repairs guide only and never delete Helpers/YAML.**
- [ ] **Step 4: Run complete maintained v10 suite and ported behavior assertions; expect PASS.**
- [ ] **Step 5: Set `10.0.0-beta.1`, update docs/changelog, commit** `feat: add persistence diagnostics and migration repairs`.

---

### Task 10: Repository/CI/HACS/docs modernization — `10.0.0-beta.2`

**Files:**
- Modify: `hacs.json`, `.github/workflows/*`, `README.md`, changelog/version
- Create/modify one modern lint/test config (`pyproject.toml` if suitable)
- Create: `docs/behavior.md`, `docs/actions.md`
- Remove obsolete release/test tooling only after equivalent checks exist.

- [ ] **Step 1: Add CI checks** for pytest, Ruff, manifest/Hassfest-compatible validation, HACS validation.
- [ ] **Step 2: Modernize repository metadata** (fork docs URL, issue tracker, codeowners, HA floor); remove old Node 12 release workflow.
- [ ] **Step 3: Finish user docs** linking configuration, entities, FSM behavior, actions, migration, troubleshooting. Explicitly document helper composition: any automation may drive a normal HA Helper that is selected in one or more EC rules.
- [ ] **Step 4: Run exactly the local commands CI runs; all green.**
- [ ] **Step 5: Set `10.0.0-beta.2`, update changelog, commit** `chore: modernize Entity Controller v10 repository`.

---

### Task 11: RC migration/smoke gate — `10.0.0-rc.1`

**Files:**
- Create: `docs/release-checklist.md`
- Modify code/tests/docs only for RC findings
- Modify manifest/changelog.

- [ ] **Step 1: Rehearse v9.7.6 → v10 upgrade:** legacy YAML → import → verify subentries/entities → restart with YAML still present (no duplicates) → remove YAML → restart (Config Entry remains authoritative).
- [ ] **Step 2: Rehearse EC01–EC10 use cases:** state/history, native Enabled/Blocked/Stay/Activate, multi-trigger, external helper rules, legacy state mirror.
- [ ] **Step 3: Run suite from clean config and migrated config; no flaky timers/duplicate callbacks.**
- [ ] **Step 4: Run CI/HACS/Hassfest validations; all green.**
- [ ] **Step 5: Set `10.0.0-rc.1`, publish exact migration notes/known limitations, commit** `release: prepare Entity Controller 10.0.0-rc.1`.

---

### Task 12: Stable release gate — `10.0.0`

- [ ] **Step 1: Confirm there are no unresolved migration/data-loss blockers.** Any RC bugfix gets its own regression test.
- [ ] **Step 2: Run full pytest + Ruff + HACS/Hassfest + migration fixtures.**
- [ ] **Step 3: Finalize README/changelog/migration docs; legacy state mirror remains clearly transitional.**
- [ ] **Step 4: Set stable version `10.0.0` and commit** `release: Entity Controller 10.0.0`.
- [ ] **Step 5: Tag/create release only from the exact green verified commit.**

---

## Plan self-review result

- Every design-spec area maps to an implementation task.
- The plan now matches the approved Helper model: there is **no** EC-owned global interlock subsystem and **no** persistent native Manual Block switch. Helpers remain normal HA entities selected per controller rule.
- Startup/reconcile/reconfigure tests explicitly pin no unintended controlled-entity actions.
- Migration is idempotent, preserves external entity references, never deletes Helpers/YAML, and retains a transitional legacy state mirror.
- Current HA direction is pinned: Config Subentries, typed `runtime_data`, `async_update_and_abort()`, single-entry/subentry device ownership; deprecated Configurator/device-registry patterns are excluded.
- Every prerelease/stable milestone requires version, changelog, docs, tests and a commit.

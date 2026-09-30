# Entity Controller v10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite Entity Controller as a modern Home Assistant 2026.9+ integration with Config Entries/Subentries, native controller entities, hot reconfiguration, preserved FSM behavior, and safe migration from v9 YAML.

**Architecture:** One root `ConfigEntry[EntityControllerManager]` owns multiple controller `ConfigSubentry` objects. Each subentry owns one `ControllerRuntime` and one virtual device; the FSM, schedule, context handling, persistence, entity platforms, config flow, migration, diagnostics and repairs are separated into focused modules. Migration keeps legacy `entity_controller.*` state compatibility for imported controllers while the new UI/native entities become the preferred interface.

**Tech Stack:** Python 3 / Home Assistant Core 2026.9+ APIs, Config Entries + Config Subentries, typed `ConfigEntry.runtime_data`, HA async event/time helpers, pytest, Ruff, Hassfest/HACS validation, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-entity-controller-v10-modernization-design.md`

## Global Constraints

- Product/domain remain `Entity Controller` / `entity_controller` for v10.
- Minimum supported Home Assistant is 2026.9+.
- Use current Config Entry/Subentry APIs; do not use the deprecated Configurator integration.
- Store runtime manager in typed `ConfigEntry.runtime_data`.
- Device ownership uses `config_entry_id` and `config_subentry_id`; do not read deprecated multi-entry registry compatibility properties.
- Reconfigure uses `async_update_and_abort()` semantics and must not combine update listeners with flow reload helpers.
- No `threading.Timer`, `asyncio.run_coroutine_threadsafe`, or `transitions` dependency in v10 runtime.
- Startup, restore, migration, and reconfigure use reconcile and must not execute transition ON/OFF behavior merely because configuration/runtime was rebuilt.
- External helpers such as `input_boolean.navsteva_block` remain ordinary Home Assistant entities selected as controller inputs; no hardcoded/shared EC interlock subsystem.
- Existing v9 YAML migration is required before stable v10.
- Entity Controller must not delete user helpers or rewrite `ec.yaml`; migration reports and Repairs guide cleanup.
- Every prerelease/stable version updates manifest version, changelog, user-visible docs, migration notes when needed, and tests.
- English and Slovak UI translations ship with v10.

## Review Focus

1. **Restart while a light is ON:** setup/reconcile must not invoke `on_enter_idle=off` and unexpectedly switch it off. Covered by Task 4 and Task 8 tests.
2. **A configured entity is unavailable or removed:** one controller degrades/report-errors without unloading unrelated controllers. Covered by Task 4 and Task 9 tests.
3. **A delay or block timeout is shortened past its current expiry:** reconfigure immediately evaluates expiry once, with no duplicate timer callback. Covered by Task 5 tests.
4. **Legacy YAML remains after successful import:** restart must be idempotent and must not duplicate subentries. Covered by Task 8 tests.
5. **External helper used as override/interlock changes while EC runs:** controller must react immediately but never take ownership of/delete/convert the helper. Covered by Task 5 and Task 8 tests.

---

## Version / milestone map

- `10.0.0-alpha.1` — modern repository/runtime skeleton, typed models, no legacy dependency.
- `10.0.0-alpha.2` — standalone FSM + schedule/context/timer core with compatibility tests.
- `10.0.0-alpha.3` — manager/runtime listeners, reconcile and hot reconfiguration.
- `10.0.0-alpha.4` — native devices/entities and modern actions/services.
- `10.0.0-alpha.5` — full Config Entry/Subentry UI with EN/SK translations.
- `10.0.0-alpha.6` — v9 YAML import/migration, compatibility state mirror, migration report and Repairs; first migration-test candidate.
- `10.0.0-beta.1` — diagnostics, persistence, full v9 behavioral parity suite and current dashboard migration fixture.
- `10.0.0-beta.2` — repository/CI/HACS modernization and complete user documentation.
- `10.0.0-rc.1` — upgrade/smoke regression pass against realistic v9 installations.
- `10.0.0` — stable release after RC findings are resolved with no migration blockers.

---

### Task 1: Modern integration skeleton and typed data model — `10.0.0-alpha.1`

**Files:**
- Modify: `custom_components/entity_controller/manifest.json`
- Modify: `custom_components/entity_controller/const.py`
- Rewrite: `custom_components/entity_controller/__init__.py`
- Create: `custom_components/entity_controller/model.py`
- Create: `custom_components/entity_controller/manager.py`
- Create: `tests/test_init.py`
- Create: `tests/test_model.py`
- Modify: `CHANGELOG.md`
- Create/Modify: `docs/development.md`

**Interfaces:**
- Produces: `EntityControllerConfigEntry = ConfigEntry[EntityControllerManager]`
- Produces enums: `ControllerState`, `SensorType`, `TransitionCause`, `TransitionBehavior`, `ReconcileReason`.
- Produces immutable/typed `ControllerConfig` with stable `subentry_id`, `name`, trigger/control/state/override/interlock fields and runtime behavior settings.
- Produces `EntityControllerManager(hass, entry)` with async lifecycle stubs used by later tasks.

- [ ] **Step 1: Write failing model/setup tests**

Add tests asserting:

```python
def test_controller_state_values():
    assert {state.value for state in ControllerState} == {
        "idle", "active_timer", "active_stay_on",
        "blocked", "overridden", "constrained", "disabled",
    }

async def test_setup_entry_stores_typed_manager(hass, config_entry):
    assert await async_setup_entry(hass, config_entry)
    assert isinstance(config_entry.runtime_data, EntityControllerManager)
```

Also assert `pending` is absent and setup does not register/use the `transitions` package.

- [ ] **Step 2: Run targeted tests and confirm failure**

Run: `pytest tests/test_model.py tests/test_init.py -v`

Expected: FAIL because v10 model/manager and Config Entry setup do not exist.

- [ ] **Step 3: Implement minimal typed skeleton**

Implement `model.py`, typed config entry alias, root setup/unload in `__init__.py`, and manager lifecycle shell. Update manifest to `10.0.0-alpha.1`, minimum HA `2026.9.0`, current repository/docs metadata, config-flow capability, and remove `transitions==0.8.8`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_model.py tests/test_init.py -v`

Expected: PASS.

- [ ] **Step 5: Update release traceability and commit**

Add `10.0.0-alpha.1` changelog entry explaining skeleton/API break and no migration readiness yet. Commit:

```bash
git add custom_components/entity_controller tests CHANGELOG.md docs/development.md
git commit -m "feat: start Entity Controller v10 architecture"
```

---

### Task 2: Explicit FSM core and transition behavior — `10.0.0-alpha.2` part A

**Files:**
- Create: `custom_components/entity_controller/controller.py`
- Modify: `custom_components/entity_controller/model.py`
- Create: `tests/test_controller_fsm.py`
- Port relevant assertions from: `tests/test_lightingsm.py`, `tests/test_lighting_sm_appdaemon.py`, `tests/test_lightingsm_async.py`

**Interfaces:**
- Consumes: `ControllerConfig`, `ControllerState`, `TransitionCause`, `TransitionBehavior`.
- Produces: `ControllerRuntime.async_transition(target: ControllerState, cause: TransitionCause, *, source_entity_id: str | None = None) -> bool`.
- Produces: `ControllerRuntime.async_reconcile(reason: ReconcileReason) -> ControllerState`.
- Produces callback boundary methods for enter/exit behavior; side-effect execution is injected/testable rather than hardwired into state calculation.

- [ ] **Step 1: Write failing FSM compatibility tests**

Pin at minimum:

```python
async def test_event_sensor_idle_to_active_timer(): ...
async def test_event_sensor_retrigger_keeps_active_and_resets_timer(): ...
async def test_duration_sensor_must_be_off_before_expiry_returns_idle(): ...
async def test_state_entity_manual_change_enters_blocked(): ...
async def test_override_enter_and_leave_reconciles(): ...
async def test_stay_mode_enters_active_stay_on(): ...
async def test_invalid_transition_is_rejected_without_side_effect(): ...
async def test_reconcile_to_idle_does_not_run_enter_idle_action(): ...
```

- [ ] **Step 2: Run FSM tests and confirm failure**

Run: `pytest tests/test_controller_fsm.py -v`

Expected: FAIL because explicit v10 FSM is not implemented.

- [ ] **Step 3: Implement central transition/reconcile engine**

Implement one auditable transition path with explicit transition validation. Keep state computation separate from action execution. Do not reproduce known v9 duplicate constraint callbacks or startup-delay behavior.

- [ ] **Step 4: Run FSM suite**

Run: `pytest tests/test_controller_fsm.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/entity_controller/controller.py custom_components/entity_controller/model.py tests/test_controller_fsm.py
git commit -m "feat: add explicit v10 controller state machine"
```

---

### Task 3: Async timers, schedules, backoff and context tracking — `10.0.0-alpha.2` part B

**Files:**
- Create: `custom_components/entity_controller/schedule.py`
- Create: `custom_components/entity_controller/context.py`
- Modify: `custom_components/entity_controller/controller.py`
- Modify: `custom_components/entity_controller/model.py`
- Create: `tests/test_schedule.py`
- Create: `tests/test_timer_backoff.py`
- Create: `tests/test_context.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `SchedulePoint` structured fixed-time/sunrise/sunset + offset representation.
- Produces: `async_is_window_active(hass, start, end, now=None) -> bool` and boundary scheduling helpers.
- Produces context tracker methods `new_action_context(parent: Context | None) -> Context` and `is_own_context(context: Context) -> bool`.
- `ControllerRuntime` owns cancellable HA timer handles only; no Python threads.

- [ ] **Step 1: Write failing schedule/timer/context tests**

Include:

```python
def test_fixed_window_crossing_midnight(): ...
def test_legacy_sunset_offset_converts_to_schedule_point(): ...
async def test_backoff_uses_factor_and_caps_at_maximum(): ...
async def test_duration_sensor_on_ignores_timer_expiry(): ...
async def test_cancelled_timer_callback_does_not_transition(): ...
def test_controller_context_is_recognized_as_own_action(): ...
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_schedule.py tests/test_timer_backoff.py tests/test_context.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement with Home Assistant async helpers**

Use current HA time/event helpers with stored unsubscribe/cancel callbacks. Keep legacy free-form schedule parser only as a conversion utility for migration, not primary runtime configuration.

- [ ] **Step 4: Run tests**

Expected: all targeted tests PASS.

- [ ] **Step 5: Tag milestone changes in docs/changelog and commit**

Set manifest version `10.0.0-alpha.2`, add changelog summary for FSM/timers/schedule/context.

```bash
git add custom_components/entity_controller tests CHANGELOG.md
git commit -m "feat: complete async v10 runtime core"
```

---

### Task 4: Manager, entity listeners and side-effect-free reconcile — `10.0.0-alpha.3` part A

**Files:**
- Modify: `custom_components/entity_controller/manager.py`
- Modify: `custom_components/entity_controller/controller.py`
- Modify: `custom_components/entity_controller/__init__.py`
- Create: `tests/test_manager.py`
- Create: `tests/test_reconcile.py`

**Interfaces:**
- Produces: `EntityControllerManager.async_add_controller(subentry) -> ControllerRuntime`.
- Produces: `EntityControllerManager.async_remove_controller(subentry_id: str) -> None`.
- Produces: `EntityControllerManager.async_update_controller(subentry) -> None`.
- `ControllerRuntime.async_start()` installs entity/state/schedule listeners.
- `ControllerRuntime.async_stop()` cancels every listener/timer idempotently.

- [ ] **Step 1: Write failing listener/reconcile tests**

Include:

```python
async def test_restart_with_control_entity_on_does_not_turn_it_off(): ...
async def test_multiple_triggers_are_subscribed(): ...
async def test_external_override_helper_change_reconciles_immediately(): ...
async def test_unavailable_trigger_does_not_break_other_controller(): ...
async def test_remove_controller_cleans_all_callbacks(): ...
```

The external-helper test must use an ordinary `input_boolean.*`/binary entity and assert EC neither creates nor mutates that helper.

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_manager.py tests/test_reconcile.py -v`

- [ ] **Step 3: Implement manager/listener lifecycle**

Route entity state changes through the runtime, preserving state-attribute-ignore and context filtering behavior. A controller-specific listener error must not unload the manager or neighboring controllers.

- [ ] **Step 4: Run targeted tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/entity_controller tests
git commit -m "feat: add controller manager and reconcile lifecycle"
```

---

### Task 5: Hot reconfiguration semantics — `10.0.0-alpha.3` part B

**Files:**
- Modify: `custom_components/entity_controller/manager.py`
- Modify: `custom_components/entity_controller/controller.py`
- Create: `tests/test_reconfigure.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `ControllerRuntime.async_apply_config(new_config: ControllerConfig) -> None`.
- Config diff handles listener, timer, schedule, override/interlock and behavior changes without reconstructing unrelated controllers.

- [ ] **Step 1: Write failing hot-update tests**

Pin exact semantics:

```python
async def test_shorten_active_delay_reschedules_from_last_trigger(): ...
async def test_shorten_delay_past_expiry_evaluates_once_immediately(): ...
async def test_change_block_timeout_past_expiry_evaluates_once(): ...
async def test_add_and_remove_trigger_rebuilds_only_trigger_listeners(): ...
async def test_change_override_to_currently_on_helper_enters_overridden(): ...
async def test_change_constraint_evaluates_current_window_immediately(): ...
async def test_reconfigure_never_fires_idle_off_just_for_config_change(): ...
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_reconfigure.py -v`

- [ ] **Step 3: Implement config-diff application**

Use original `last_triggered_at` / `blocked_at` for recalculation. Cancel old callbacks before scheduling replacements; guard callbacks with generation/token semantics so stale callbacks cannot fire after reconfigure.

- [ ] **Step 4: Run tests**

Expected: PASS.

- [ ] **Step 5: Version/changelog and commit**

Set manifest `10.0.0-alpha.3`, document that runtime changes apply without HA restart/root reload.

```bash
git add custom_components/entity_controller tests CHANGELOG.md
git commit -m "feat: hot reconfigure individual controllers"
```

---

### Task 6: Native controller device/entities and modern actions — `10.0.0-alpha.4`

**Files:**
- Create: `custom_components/entity_controller/entity.py`
- Create: `custom_components/entity_controller/sensor.py`
- Create: `custom_components/entity_controller/binary_sensor.py`
- Create: `custom_components/entity_controller/switch.py`
- Create: `custom_components/entity_controller/button.py`
- Rewrite: `custom_components/entity_controller/entity_services.py` or replace with `custom_components/entity_controller/actions.py`
- Rewrite: `custom_components/entity_controller/services.yaml`
- Modify: `custom_components/entity_controller/__init__.py`
- Create: `tests/test_entities.py`
- Create: `tests/test_services.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Primary entities per controller: state enum sensor, Enabled switch, Stay Mode switch, Manual Block switch, Blocked binary sensor, Activate button.
- Diagnostic timestamps are disabled by default.
- Legacy action names remain callable: `activate`, `clear_block`, `enable_block`, `enable_stay_mode`, `disable_stay_mode`, `set_night_mode` where meaningful.

- [ ] **Step 1: Write failing entity/device tests**

Assert one controller device is registered under the root config entry + correct `config_subentry_id`, unique IDs are stable, state sensor exposes exact FSM raw states, Enabled OFF does not turn controlled entities off, Blocked binary sensor mirrors runtime blocking reason, Manual Block affects only its controller, and diagnostics are disabled by default.

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_entities.py tests/test_services.py -v`

- [ ] **Step 3: Implement native platforms and service dispatch**

Use `DeviceInfo`/entity registry APIs valid for HA 2026.9+. Do not inspect deprecated `DeviceEntry.config_entries`/`config_entries_subentries` properties.

- [ ] **Step 4: Run tests**

Expected: PASS.

- [ ] **Step 5: Version/changelog/docs and commit**

Set `10.0.0-alpha.4`; add entity reference draft.

```bash
git add custom_components/entity_controller tests CHANGELOG.md docs
git commit -m "feat: expose native Entity Controller devices and entities"
```

---

### Task 7: Config Entry/Subentry UI and translations — `10.0.0-alpha.5`

**Files:**
- Create: `custom_components/entity_controller/config_flow.py`
- Create: `custom_components/entity_controller/strings.json`
- Create: `custom_components/entity_controller/translations/en.json`
- Create: `custom_components/entity_controller/translations/sk.json`
- Modify: `custom_components/entity_controller/manifest.json`
- Create: `tests/test_config_flow.py`
- Create: `tests/test_subentry_flow.py`
- Create: `docs/configuration.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Root config flow creates the single Entity Controller entry.
- `controller` `ConfigSubentryFlow` supports create and reconfigure.
- Reconfigure persists via `async_update_and_abort()` and runtime update listener; no reload helper.
- UI sections: identity, triggers, controlled/state entities, timer, blocking, override/interlock entities, constraints, day/night, stay, transition actions, advanced mappings.

- [ ] **Step 1: Write failing flow tests**

Include:

```python
async def test_only_one_root_entry_can_be_created(): ...
async def test_add_basic_motion_controller_subentry(): ...
async def test_reconfigure_subentry_updates_data_without_reload(): ...
async def test_external_helper_can_be_selected_as_override_or_interlock(): ...
async def test_basic_flow_does_not_require_advanced_fields(): ...
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_config_flow.py tests/test_subentry_flow.py -v`

- [ ] **Step 3: Implement flows/selectors/translations**

Use current Home Assistant selectors for entities, durations, times, booleans/selects and native action configuration. Keep optional/advanced sections structured rather than depending on deprecated Advanced Mode flow visibility.

- [ ] **Step 4: Run flow tests plus translation validation**

Run: `pytest tests/test_config_flow.py tests/test_subentry_flow.py -v`

Expected: PASS.

- [ ] **Step 5: Version/docs/changelog and commit**

Set `10.0.0-alpha.5`.

```bash
git add custom_components/entity_controller tests docs/configuration.md CHANGELOG.md
git commit -m "feat: add native Entity Controller configuration UI"
```

---

### Task 8: v9 YAML migration and compatibility bridge — `10.0.0-alpha.6`

**Files:**
- Create: `custom_components/entity_controller/migration.py`
- Modify: `custom_components/entity_controller/config_flow.py`
- Modify: `custom_components/entity_controller/__init__.py`
- Create: `custom_components/entity_controller/legacy_entity.py` if required for old-domain mirror isolation
- Create: `tests/fixtures/legacy_ec.yaml`
- Create: `tests/test_migration.py`
- Create: `tests/test_legacy_entity.py`
- Create: `docs/migration-v9-to-v10.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces typed `MigrationReport` with controllers imported, warnings, legacy-to-new entity map and cleanup guidance.
- Legacy YAML import converts each controller to one `controller` subentry.
- Imported controllers optionally expose `entity_controller.<legacy_object_id>` state mirror for compatibility during v10.
- External helpers referenced by v9 config remain external references; migration does not convert/delete them.

- [ ] **Step 1: Build failing migration fixture tests**

The fixture must include multiple controllers, multi-trigger entry, event + duration modes, state entities, override helper, external block/interlock helper, night mode, constraints with sunrise/sunset offset, backoff, custom state maps and transition behaviors.

Assert:

```python
async def test_yaml_import_creates_one_subentry_per_controller(): ...
async def test_import_is_idempotent_when_yaml_remains_on_restart(): ...
async def test_external_helper_reference_is_preserved_not_converted(): ...
async def test_legacy_schedule_strings_convert_to_structured_data(): ...
async def test_import_does_not_turn_existing_control_entity_off(): ...
async def test_unknown_legacy_field_is_reported_not_dropped_silently(): ...
async def test_migrated_controller_exposes_legacy_state_mirror(): ...
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_migration.py tests/test_legacy_entity.py -v`

- [ ] **Step 3: Implement importer and compatibility mirror**

Map every legacy key listed in the design spec. Legacy helpers are never deleted and arbitrary helper naming is not guessed into native EC state. If helper state is not explicitly part of legacy EC config, migration leaves it alone.

- [ ] **Step 4: Add current-installation migration fixture assertions**

Add test data representing the EC01–EC10 patterns from the dashboard requirements, including Vchod multi-trigger and the shared `navsteva_block` helper as an external selected entity. Assert no hardcoded global EC interlock object is created.

- [ ] **Step 5: Run migration and regression tests**

Run: `pytest tests/test_migration.py tests/test_legacy_entity.py tests/test_controller_fsm.py tests/test_reconcile.py -v`

Expected: PASS.

- [ ] **Step 6: Version/docs/changelog and commit**

Set `10.0.0-alpha.6`; mark this as first build intended for controlled migration testing, not stable production.

```bash
git add custom_components/entity_controller tests docs/migration-v9-to-v10.md CHANGELOG.md
git commit -m "feat: migrate legacy Entity Controller YAML to v10"
```

---

### Task 9: Persistence, diagnostics and Repairs — `10.0.0-beta.1`

**Files:**
- Create: `custom_components/entity_controller/storage.py` if runtime persistence cannot be cleanly expressed through entity restore alone
- Create: `custom_components/entity_controller/diagnostics.py`
- Create: `custom_components/entity_controller/repairs.py`
- Modify: `custom_components/entity_controller/controller.py`
- Create: `tests/test_persistence.py`
- Create: `tests/test_diagnostics.py`
- Create: `tests/test_repairs.py`
- Create: `docs/troubleshooting.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Persist controller-owned Enabled, Stay Mode and Manual Block state.
- Restore timestamps only when semantically valid; never replay old enter/exit side effects.
- Diagnostics return sanitized controller/runtime/migration data.
- Repairs cover legacy YAML still present, unsupported migrated fields, missing referenced entities and incomplete cleanup.

- [ ] **Step 1: Write failing persistence/diagnostic/repair tests**

Include restart with active timer, restart with manual block, unavailable entity recovery, legacy YAML Repair idempotency, migration warning rendering, and diagnostics redaction/stability.

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_persistence.py tests/test_diagnostics.py tests/test_repairs.py -v`

- [ ] **Step 3: Implement persistence, diagnostics and Repairs**

Repairs must guide; they do not delete helpers/YAML. A missing entity problem belongs to the affected controller and must not fail the whole root entry.

- [ ] **Step 4: Run full v10 suite and selected ported v9 behavior tests**

Run: `pytest tests/test_* -v`

Expected: PASS for the maintained v10 suite; clearly mark obsolete v9 implementation-specific tests for replacement/removal rather than silently skipping behavioral coverage.

- [ ] **Step 5: Version/changelog/docs and commit**

Set `10.0.0-beta.1`.

```bash
git add custom_components/entity_controller tests docs CHANGELOG.md
git commit -m "feat: add persistence diagnostics and migration repairs"
```

---

### Task 10: Repository, CI and HACS modernization — `10.0.0-beta.2`

**Files:**
- Modify: `hacs.json`
- Replace/update: `.github/workflows/*`
- Create/modify: `pyproject.toml` or the chosen single modern lint/test config
- Modify/remove obsolete legacy test/release tooling only after equivalent v10 checks exist
- Modify: `README.md`
- Create: `docs/entities.md`
- Create: `docs/behavior.md`
- Create: `docs/actions.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- CI runs pytest, Ruff, Hassfest-compatible validation where applicable, and HACS validation.
- Release process uses supported GitHub Actions; no Node 12-era workflow.

- [ ] **Step 1: Add validation configuration and make CI fail on current issues**

Add exact workflow checks for test/lint/manifest/HACS. Verify the old repository state does not falsely pass missing v10 validation.

- [ ] **Step 2: Modernize metadata/tooling**

Update repository/docs/codeowners/issue tracker/homeassistant floor/version metadata. Remove stale upstream URLs owned by the old project where the fork now needs its own references.

- [ ] **Step 3: Finish user documentation**

README links to configuration, entities, FSM behavior, actions, migration and troubleshooting. Document external helper inputs explicitly: users may create arbitrary HA automations/helpers and select those entities in any relevant EC controller rule.

- [ ] **Step 4: Run full local validation**

Run the exact commands used by CI. Expected: all green.

- [ ] **Step 5: Version and commit**

Set `10.0.0-beta.2`.

```bash
git add .github hacs.json pyproject.toml README.md docs custom_components/entity_controller CHANGELOG.md
git commit -m "chore: modernize Entity Controller v10 repository"
```

---

### Task 11: RC migration/smoke gate — `10.0.0-rc.1`

**Files:**
- Modify tests/docs/code only for findings from real migration rehearsal
- Create: `docs/release-checklist.md`
- Modify: `CHANGELOG.md`
- Modify: `custom_components/entity_controller/manifest.json`

**Interfaces:**
- No new architecture. RC is stabilization only.

- [ ] **Step 1: Rehearse upgrade path from v9.7.6 fixture**

Test sequence: start legacy YAML installation -> upgrade component -> import -> verify all controller subentries/entities -> leave YAML in place and restart -> confirm no duplicates -> remove YAML -> restart -> confirm Config Entry source remains valid.

- [ ] **Step 2: Rehearse current EC01–EC10 dashboard use cases**

Verify state history entity, native Enabled, Blocked indicator, multiple trigger display sources, external helper override/block inputs and legacy mirror compatibility.

- [ ] **Step 3: Run full regression suite repeatedly around restart/reconfigure**

At minimum run entire suite once from clean config and once from migrated config state. No flaky timers or duplicate callbacks allowed.

- [ ] **Step 4: Run CI/HACS/Hassfest validation**

Expected: all green.

- [ ] **Step 5: Version, RC notes and commit**

Set `10.0.0-rc.1`; changelog must call out migration instructions and known limitations if any.

```bash
git add .
git commit -m "release: prepare Entity Controller 10.0.0-rc.1"
```

---

### Task 12: Stable v10 release gate — `10.0.0`

**Files:**
- Modify only release/version/docs files plus any RC bugfix with its own test.

**Interfaces:**
- Stable behavior/config schema is the RC-proven one.

- [ ] **Step 1: Confirm no unresolved migration blockers or known data-loss issues**

Every known RC defect must either be fixed with a regression test or explicitly block stable release.

- [ ] **Step 2: Run complete verification matrix**

Run full pytest + Ruff + HACS/Hassfest validation + migration fixtures.

- [ ] **Step 3: Finalize docs/changelog**

Remove prerelease warnings where appropriate, keep migration cleanup/Repair instructions prominent, and document legacy state mirror as transitional compatibility.

- [ ] **Step 4: Set stable version and commit**

Set manifest and HACS/release metadata to `10.0.0`.

```bash
git add .
git commit -m "release: Entity Controller 10.0.0"
```

- [ ] **Step 5: Create/tag release only after repository CI is green**

Release artifact must correspond exactly to the verified stable commit.

---

## Plan self-review result

- **Spec coverage:** architecture, FSM, async timers, context, constraints/night/backoff, hot updates, entities, services, UI, migration, legacy mirror, persistence, diagnostics, Repairs, docs and repository modernization all map to explicit tasks.
- **Migration ownership:** corrected to preserve arbitrary external helpers as referenced HA entities; there is no shared EC interlock subsystem or automatic conversion of `navsteva_block`-style helpers.
- **Side-effect safety:** startup/reconcile/reconfigure tests explicitly pin no unintended ON/OFF behavior.
- **Current HA API direction:** plan uses Config Subentries, `runtime_data`, `async_update_and_abort`, and single config-entry/subentry device ownership and avoids already-deprecated device/configurator patterns.
- **Release traceability:** every milestone has version/changelog/docs/test/commit requirements; alpha.6 is the first migration-test candidate and RC is stabilization only.

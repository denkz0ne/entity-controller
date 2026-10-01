# One-time Legacy YAML Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import each controller from HA's already-loaded legacy `entity_controller` YAML into one flat config entry exactly once, leaving the source file untouched.

**Architecture:** `async_setup(hass, config)` reads only Home Assistant's parsed integration mapping, converts controllers with `migration.py`, and starts a `SOURCE_IMPORT` flow for each valid controller. The import flow assigns a deterministic unique ID and uses the existing flat-entry identity helper; Home Assistant's unique-ID guard makes retries harmless.

**Tech Stack:** Python 3.12, Home Assistant config entries and config flows, pytest, pytest-asyncio, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-01-legacy-yaml-one-time-import-design.md`

## Global Constraints

- Home Assistant supplies the integration's parsed YAML mapping to `async_setup`; the integration must not open an arbitrary filesystem path such as `/config/entitycontroller.yaml` itself.
- Create one config entry per controller through the integration's `SOURCE_IMPORT` config flow.
- Keep the source YAML file unchanged.
- Do not add an import button, options flow, persistent import switch, or repeated import behavior.
- Existing v10-to-v11 config-entry migration remains independent and unchanged.
- A malformed individual controller is skipped; valid controllers continue importing.
- Unsupported legacy fields produce warnings. They are not silently treated as migrated settings.
- Existing external helper references remain references; this migration does not create helper entities.

## Review Focus

- YAML is absent or empty: setup succeeds and starts no flow; test in Task 2.
- A malformed controller is mixed with valid entries: skip only the malformed one; test in Task 1 and startup coverage in Task 2.
- A controller ID collides with an already imported entry: abort that flow without overwriting user-edited data; test in Task 2.
- One import flow raises/fails among several controllers: log it and continue; test in Task 2.
- YAML reaches setup in an unexpected non-mapping shape: log and return setup success without creating entries; test in Task 2.

---

### Task 1: Make the converter's runtime contract controller-oriented

**Files:**
- Modify: `custom_components/entity_controller/migration.py`
- Test: `tests/test_migration.py`

**Interfaces:**
- Consumes: `parse_legacy_yaml(content: str) -> dict[str, Any]` and existing legacy conversion rules.
- Produces: `migrate_legacy_yaml(legacy_config: dict[str, Any], *, existing_controller_ids: set[str] | None = None) -> MigrationReport`; each `ImportedController` exposes `controller_id: str` and converted `data`.

- [ ] **Step 1: Write failing converter tests**

Rename the existing-subentry idempotency test to controller IDs and assert that preexisting controller IDs appear in `skipped_existing`. Add a malformed-controller case beside a valid fixture entry; assert that only the valid controller is imported and the malformed one has a `<controller>` warning. Keep the unknown-field warning assertion and external-helper preservation assertions.

- [ ] **Step 2: Run converter tests to verify the new contract fails**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_migration.py`
Expected: FAIL because the controller-oriented argument/result interface and malformed-entry behavior are not implemented yet.

- [ ] **Step 3: Implement controller-oriented converter results**

In `migration.py`, rename `ImportedController.subentry_id` to `controller_id`, change `existing_subentry_ids` to `existing_controller_ids`, and use these names consistently in report assembly. Preserve the current conversions, warnings, stable legacy IDs, and cleanup guidance. Catch per-controller conversion errors (including malformed nested values such as invalid entity lists or incomplete night-mode mappings), add a `<controller>` warning for that record, and continue converting valid siblings.

- [ ] **Step 4: Run converter tests**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_migration.py`
Expected: PASS, including malformed sibling, idempotency, unknown-field, and helper-reference coverage.

- [ ] **Step 5: Commit converter contract**

```bash
git add custom_components/entity_controller/migration.py tests/test_migration.py
git commit -m "refactor: expose legacy controller migration contract"
```

### Task 2: Add the `SOURCE_IMPORT` config-flow path

**Files:**
- Modify: `custom_components/entity_controller/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: one `controller_id` and converted flat data from Task 1.
- Produces: `EntityControllerConfigFlow.async_step_import(import_config: dict[str, Any])`, which creates a flat version-11 config entry with `_ec_controller_id` and `_ec_entity_unique_id_prefix` set to the stable legacy controller ID.

- [ ] **Step 1: Write failing import-flow tests**

Test a valid legacy payload: the result is `create_entry`, title is the converted name, entry data retains all converted values, both internal identity fields equal the legacy controller ID, version is 11, and the entry unique ID is `legacy-yaml:<controller_id>`. Test duplicate unique ID aborts without creating or updating an entry.

- [ ] **Step 2: Run import-flow tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_config_flow.py -k import`
Expected: FAIL because `async_step_import` is not implemented.

- [ ] **Step 3: Implement `async_step_import`**

Add an import step that calls Home Assistant's unique-ID setup/duplicate guard with `legacy-yaml:<controller_id>`, wraps converted data using `fresh_controller_data(..., controller_id=controller_id)`, then creates the entry with the normalized name. Do not reuse the interactive form normalizer; legacy conversion has already produced normalized data.

- [ ] **Step 4: Run import-flow tests**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_config_flow.py -k import`
Expected: PASS; duplicate import aborts and leaves an existing entry unchanged.

- [ ] **Step 5: Commit import flow**

```bash
git add custom_components/entity_controller/config_flow.py tests/test_config_flow.py
git commit -m "feat: add legacy YAML import flow"
```

### Task 3: Trigger a retry-safe import from integration setup

**Files:**
- Modify: `custom_components/entity_controller/__init__.py`
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: Home Assistant's parsed `config[DOMAIN]` mapping, Task 1's `MigrationReport`, and Task 2's `async_step_import` flow.
- Produces: `async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool` that starts one flow per valid, not-yet-imported controller and always returns setup success for per-controller migration errors.

- [ ] **Step 1: Write failing setup-import tests**

Add fake Home Assistant config-entry flow coverage for absent/empty YAML, one controller, multiple controllers, repeated startup with existing `legacy-yaml:<id>` entries, malformed top-level input, malformed one-of-many controller data, and one raised flow error among successful siblings. Assert one attempted flow per valid new controller, stable `SOURCE_IMPORT` context/data, no flow for existing IDs, continued attempts after an individual failure, and `True` setup result.

- [ ] **Step 2: Run setup-import tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_init.py -k yaml_import`
Expected: FAIL because `async_setup` is not implemented.

- [ ] **Step 3: Implement `async_setup`**

Read only `config.get(DOMAIN)`. If missing/empty, return `True`. If the value is not a mapping, log an error and return `True`. Gather existing unique IDs for this domain, convert with `migrate_legacy_yaml`, log converter warnings, and sequentially call `hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={"controller_id": ..., **data})` for each new item. Catch and log an individual flow exception so later controllers are still attempted. Never access the filesystem.

- [ ] **Step 4: Run setup-import tests and existing entry-migration tests**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_init.py tests/test_entry_migration.py tests/test_migration.py`
Expected: PASS; existing v10-to-v11 migration tests remain unchanged and pass.

- [ ] **Step 5: Commit startup import**

```bash
git add custom_components/entity_controller/__init__.py tests/test_init.py
git commit -m "feat: import legacy YAML controllers on setup"
```

### Task 4: Preserve additional supported settings from the real v9 schema

**Files:**
- Modify: `custom_components/entity_controller/migration.py`
- Test: `tests/test_migration.py`
- Update: `tests/test_init.py` expected import payload for preserved legacy defaults

**Interfaces:**
- Consumes: Task 1's controller-oriented conversion result and the v9 schema in `hass-demo/custom_components/entity_controller/__init__.py`.
- Produces: converted current-model fields for service data, state lists, ignored attributes, schedules, and duration aliases; legacy fields with no current equivalent remain warnings.

- [ ] **Step 1: Write failing preservation tests**

Add a literal v9 input containing day and night `service_data`/`service_data_off`, `state_attributes_ignore`, sensor/state/override on/off states, global `state_strings_on/off`, `sensor_type_duration`, and top-level start/end times. Assert current-model output values, including fixed/sun schedule points and current day/night service-data keys. Add an unsupported field assertion proving unsupported fields still produce warnings.

- [ ] **Step 2: Run converter tests to verify preservation fails**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_migration.py`
Expected: FAIL because supported v9 values are currently absent or incorrectly defaulted in converted data.

- [ ] **Step 3: Map supported v9 fields and warn on unsupported fields**

Use the actual v9 schema as the field inventory. Map day/night service payloads, sensor/state/override state lists, `state_attributes_ignore`, duration alias, and a complete top-level `start_time`/`end_time` pair into their current-model counterparts. Apply legacy default on/off state values when old overrides are absent, and append legacy `state_strings_on/off` to supported state lists. Do not whitelist a field that has no current-model equivalent; it must remain in `MigrationReport.warnings`. Keep malformed-value handling per controller from Task 1.

- [ ] **Step 4: Run converter tests**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_migration.py`
Expected: PASS; day/night service data, state mappings, timing, and unsupported-field warnings are all asserted.

- [ ] **Step 5: Commit additional field preservation**

```bash
git add custom_components/entity_controller/migration.py tests/test_migration.py tests/test_init.py
git commit -m "fix: preserve supported v9 controller settings"
```

### Task 5: Document one-time behavior and run the maintained CI checks

**Files:**
- Modify: `docs/migration-v9-to-v10.md`
- Modify: `CHANGELOG.md`
- Test: existing v10 modernization CI suite

**Interfaces:**
- Consumes: shipped setup and flow behavior from Tasks 1–4.
- Produces: user guidance that the active YAML include is imported at startup, the source file is not changed, and it should be removed manually only after EC01–EC10 validation.

- [ ] **Step 1: Update migration guide and changelog**

Document that import only runs when Home Assistant has loaded the old integration YAML; no arbitrary path is scanned. State that valid controllers become separate entries, unsupported fields are logged, helpers are not created, supported day/night service data and state mappings are converted, and the YAML include/file should remain until EC01–EC10 pass, then be removed manually.

- [ ] **Step 2: Run the maintained CI Ruff file list**

Run: extract and execute the Ruff file list from `.github/workflows/v10-modernization.yml`.
Expected: `All checks passed!`.

- [ ] **Step 3: Run the maintained v10 test suite**

Run: `PYTHONPATH=. .venv/bin/pytest -q` with the test file list from `.github/workflows/v10-modernization.yml`.
Expected: all maintained v10 tests pass, including the new import tests.

- [ ] **Step 4: Check the final diff and commit documentation**

Run: `git diff --check`.
Expected: no whitespace errors; the local HAOS configuration and legacy source YAML remain untouched.

```bash
git add docs/migration-v9-to-v10.md CHANGELOG.md
git commit -m "docs: explain one-time legacy YAML import"
```

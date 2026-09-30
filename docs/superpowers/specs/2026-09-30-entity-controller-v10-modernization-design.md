# Entity Controller v10 — modernization design

**Status:** design approved in chat; written specification awaiting final review  
**Date:** 2026-09-30  
**Target Home Assistant:** 2026.9+  
**Product version:** 10.0.0 development line  
**Repository:** `denkz0ne/entity-controller`  
**Domain:** `entity_controller`

## 1. Purpose

Entity Controller v10 modernizes the existing `danobot/entity-controller` integration instead of replacing it with a different automation concept.

The goal is to preserve the useful Entity Controller state-machine behavior while replacing the YAML-first implementation and obsolete Home Assistant patterns with a native Config Entry / Config Subentry UI, async runtime, native entities, diagnostics, Repairs, safe migration, and current repository tooling.

Primary goals:

1. Controllers are created and edited in the Home Assistant UI instead of `ec.yaml`.
2. Changes apply to the affected controller immediately, without Home Assistant restart and without reloading unrelated controllers.
3. Controller-owned runtime controls/status become native EC entities instead of generic Helpers.
4. Existing v9 YAML and dashboard references have a safe migration path.
5. Arbitrary Home Assistant Helpers and entities remain reusable as external EC rule inputs; EC does not own or globally register them.
6. Legacy runtime patterns such as the 70-second startup delay, `threading.Timer`, `asyncio.run_coroutine_threadsafe`, and the `transitions` dependency are removed.

The name **Entity Controller** and domain `entity_controller` remain unchanged for v10.

---

## 2. Compatibility source of truth

The behavior baseline is upstream v9.7.6 source code, not only its older documentation.

The existing v9 behavior documentation in `denkz0ne/hassos-stuff` remains the compatibility reference. v10 preserves intended behavior unless this specification explicitly changes it.

Known implementation quirks are not compatibility requirements, including the startup delay, duplicated state-list extension, stale service names, duplicate constraint callbacks, and thread-based timers.

---

## 3. Home Assistant architecture

### 3.1 Selected model

Entity Controller creates one root Config Entry. Each controller is one Config Subentry of type `controller`.

```text
Entity Controller
├── EC01 Izba pohyb
├── EC02 Chodba pohyb
├── EC03 Chalúpka pohyb
├── EC04 Vchod pohyb
└── ...
```

Each controller subentry owns one runtime controller and one Home Assistant device.

```text
ConfigEntry[EntityControllerManager]
└── EntityControllerManager
    ├── ControllerRuntime(subentry A)
    ├── ControllerRuntime(subentry B)
    └── ControllerRuntime(subentry C)
```

The manager is stored in `entry.runtime_data`.

A controller maps to the registry model as:

```text
root ConfigEntry
    └── controller ConfigSubentry
          └── controller Device
                ├── state/status entities
                ├── control entities
                └── diagnostics
```

Devices use current single-config-entry / single-subentry ownership APIs.

### 3.2 Alternatives rejected

**One Config Entry per controller** was rejected because it clutters the Integrations page and makes shared migration and diagnostics less coherent.

**One Config Entry containing an array of all controllers** was rejected because it recreates a large YAML-like monolith and gives poor independent lifecycle and reconfiguration.

---

## 4. Controller state machine

### 4.1 Runtime states

v10 states:

- `idle`
- `active_timer`
- `active_stay_on`
- `blocked`
- `overridden`
- `constrained`
- `disabled`

The old `pending` state is removed. Startup is lifecycle, not a user-visible controller state.

### 4.2 Explicit async FSM

The `transitions` dependency is removed. State changes go through one typed async transition path, conceptually:

```python
await controller.async_transition(
    ControllerState.BLOCKED,
    cause=TransitionCause.MANUAL_CONTROL,
)
```

The transition path owns validation, exit behavior, state change, enter behavior, timer consequences, context tracking, event/logbook data, entity updates, and diagnostics metadata.

### 4.3 Reconcile is not a transition

Startup, restore, migration, and reconfiguration use **reconcile** rather than simulating normal enter/exit events.

Reconcile observes current reality:

- constraint state;
- configured external override/interlock inputs;
- control/state entities;
- event/duration sensors;
- persisted controller-owned runtime state when relevant.

It computes the correct FSM state without blindly executing transition ON/OFF actions because Home Assistant restarted or settings were edited.

---

## 5. Native entities per controller

Configuration values stay in configuration. Only values useful to observe or control during runtime become entities.

### 5.1 State sensor

Example:

```text
sensor.ec01_izba_pohyb_state
```

States:

```text
idle
active_timer
active_stay_on
blocked
overridden
constrained
disabled
```

Useful attributes include:

```yaml
last_transition: 2026-09-30T14:18:04+02:00
transition_cause: sensor_trigger
last_triggered_by: binary_sensor.zb38pohyb
last_triggered_at: 2026-09-30T14:18:04+02:00
profile: night
effective_delay: 90
expires_at: 2026-09-30T14:19:34+02:00
blocked_by: null
block_reason: null
overridden_by: null
active_rule_inputs: []
```

No once-per-second countdown is generated.

### 5.2 Enabled switch

Example:

```text
switch.ec01_izba_pohyb_enabled
```

Semantics:

- OFF stops EC decision-making for that controller.
- OFF does not turn controlled entities off.
- ON reconciles against current reality.
- state survives restart.

This replaces the current per-controller `input_boolean.<controller>_enabled` dashboard-helper use case.

### 5.3 Stay mode switch

Example:

```text
switch.ec01_izba_pohyb_stay_mode
```

This gives stay mode a normal native runtime control while preserving compatible actions/services.

### 5.4 Blocked binary sensor

Example:

```text
binary_sensor.ec01_izba_pohyb_blocked
```

This is intentionally exposed even though the state sensor can also equal `blocked` because dashboard logic commonly needs blocking as an independent boolean.

Attributes:

```yaml
reason: manual_control
blocked_by: light.pracovna_stol
blocked_at: 2026-09-30T14:21:00+02:00
block_expires_at: 2026-09-30T14:51:00+02:00
active_rule_inputs: []
```

This replaces helper/template patterns such as `binary_sensor.<controller>_blokovanie`.

### 5.5 Activate button

Example:

```text
button.ec01_izba_pohyb_activate
```

Equivalent to the existing `activate` action semantics.

### 5.6 Optional diagnostics/buttons

Disabled by default where appropriate:

- timer-expiry timestamp sensor;
- last-trigger timestamp sensor;
- last-transition timestamp sensor;
- last-transition-cause sensor if useful beyond attributes;
- `Clear block` button for clearable automatic/latched blocks.

v10 does **not** create a dedicated persistent `manual_block` switch. Persistent external gating is represented by ordinary Home Assistant entities selected in controller rules.

---

## 6. External rule inputs — Helpers remain normal Home Assistant entities

This is a core design rule.

Entity Controller does not create special global objects such as `navsteva_block`, party mode, holiday mode, sleep mode, or similar switches.

The user may create any normal Home Assistant automation/helper/entity and then select that entity in one or more EC controllers.

Example:

```text
automation / script / user
        ↓
input_boolean.navsteva_block
        ↓
EC Obývačka rule
EC Kuchyňa rule
```

The same external entity may be assigned to any number of controllers.

Examples of valid external rule inputs:

```text
input_boolean.navsteva_block
input_boolean.izba_block
switch.house_guest_mode
binary_sensor.some_condition
```

Entity Controller only observes the configured entity/state and applies the selected EC semantics. It does not own that helper, rename it, duplicate it, globally register it, or infer why it is ON/OFF.

A helper can therefore be controlled by any independent Home Assistant automation and then act as an override/interlock input for selected EC rules. That composition is intentional.

### 6.1 Rule semantics

At minimum v10 preserves the existing **override** concept and supports external block/interlock-style inputs where needed by the migrated configuration/dashboard model.

The UI uses normal entity selectors. Custom ON/OFF state mappings remain available in Advanced configuration for non-boolean entities.

External inputs are configured per controller. There is no global hardcoded assignment layer.

---

## 7. Trigger, control, and state entities

### 7.1 Trigger sensors

A controller supports one or more trigger entities.

Example:

```text
Vchod
├── motion sensor
└── door sensor
```

Trigger inputs remain their real source entities; EC does not create copies.

Sensor modes retain v9 concepts:

- event sensor;
- duration sensor.

Custom ON/OFF mappings remain available.

### 7.2 Control entities

One or more entities controlled by EC. Simple behavior uses normal Home Assistant turn-on/turn-off semantics where supported.

### 7.3 State entities

State entities default to control entities when not explicitly set, preserving v9 behavior. Their changes are used for manual-control blocking and reconciliation.

### 7.4 Ignored attributes and contexts

`state_attributes_ignore` remains supported.

Context handling is modernized so EC can distinguish and ignore its own actions without relying only on the old `ec_` context-id prefix convention.

---

## 8. Blocking

Blocking stays first-class.

Possible block sources include:

- manual/external state change of a state/control entity;
- an existing control/state entity already ON when event logic requires blocking;
- a configured external interlock/helper condition;
- legacy/manual `enable_block` action where retained.

Runtime records block source and reason.

An externally held interlock and an automatic/latched block are not identical internally even if both can surface as `state=blocked`.

`block_timeout` applies only to block classes where timeout is logically valid. An externally held helper remains effective as long as its configured condition is true.

---

## 9. Override

Override remains separate from blocking.

Features retained:

- one or more override entities;
- OR semantics across override inputs;
- custom override ON/OFF state mappings;
- immediate re-evaluation when override configuration changes;
- after override clears, reconcile against current sensor/state reality instead of blindly turning devices off.

`overridden_by` is exposed in state/diagnostics.

---

## 10. Constraints and schedules

Free-form runtime string parsing is replaced as the primary model by structured configuration.

A schedule point can use:

- fixed local time;
- sunrise;
- sunset;

plus a positive/negative duration offset.

Cross-midnight windows remain supported.

Legacy strings such as `sunset - 00:30:00` are parsed only during migration into the structured representation.

Debug-only forms such as `now +/- seconds` do not become normal UI features.

---

## 11. Day/night profile

Constraint and profile remain separate concepts:

- constraint = whether the controller may operate;
- profile = how it behaves during a period.

Night mode can have its own timeout and action/service data. Missing night values inherit normal/day values.

---

## 12. Timer and backoff

`threading.Timer` is removed. Timers use current Home Assistant async time helpers and cancellable callback handles.

Backoff keeps v9 intent:

- count starts at zero on activation;
- timer reset increments count;
- effective delay uses factor and maximum;
- effective delay is visible in diagnostics/state attributes.

### 12.1 Live timer reconfiguration

Changing delay while active recalculates expiry from the original last-trigger timestamp.

Example:

```text
last_triggered_at = 14:00:00
old delay = 180 s
new delay = 60 s
new expiry = 14:01:00
```

If the new expiry is already past, normal expiry evaluation runs immediately.

Equivalent logic applies to block timeout/profile delay changes.

---

## 13. Hot reconfiguration

Editing a controller uses Config Subentry reconfigure flow and update semantics that do not reload the whole integration.

A controller update diff changes only that runtime controller.

Examples:

- delay changed -> reschedule timer;
- sensors changed -> replace relevant listeners and reconcile;
- override/interlock inputs changed -> replace listeners and evaluate immediately;
- constraint changed -> reschedule boundaries and evaluate current time immediately;
- block timeout changed -> recalculate from `blocked_at`;
- stay behavior changed -> reconcile active state;
- control/state entities changed -> replace subscriptions without blindly firing activation/deactivation actions.

No unrelated controller is reloaded.

---

## 14. Transition behaviors and custom actions

Retained concepts:

- `on_enter_idle`
- `on_exit_idle`
- `on_enter_active`
- `on_exit_active`
- `on_enter_overridden`
- `on_exit_overridden`
- `on_enter_constrained`
- `on_exit_constrained`
- `on_enter_blocked`
- `on_exit_blocked`

Default intent remains:

```text
enter idle   -> OFF
enter active -> ON
others       -> IGNORE
```

UI choices:

```text
Turn off
Turn on
Do nothing
Custom action
```

`Custom action` uses native Home Assistant action configuration instead of a new EC-specific DSL.

---

## 15. Actions/services compatibility

Keep existing action names where meaningful:

- `activate`
- `clear_block`
- `enable_block`
- `enable_stay_mode`
- `disable_stay_mode`
- `set_night_mode`

Native entities become preferred for Enabled/Stay/Activate. Legacy service metadata and implementation names are synchronized.

---

## 16. Legacy `entity_controller.*` compatibility

Imported v9 controllers may already be referenced by dashboards, history graphs, templates, and automations such as:

```text
entity_controller.ec01_izba_pohyb
```

v10 therefore preserves a transitional compatibility state entity/mirror for migrated controllers so references do not disappear during upgrade.

The new native state sensor is preferred for new dashboards. New controllers do not require the legacy mirror by default.

Removal of the compatibility mirror, if ever done, requires a later major-version migration and documentation.

---

## 17. Migration from v9 YAML to v10

Migration is a required v10 feature.

### 17.1 Legacy input

Typical installation:

```yaml
entity_controller: !include ec.yaml
```

or equivalent inline YAML.

Home Assistant parses included YAML before passing domain configuration to the integration. v10 imports the parsed legacy configuration into the root Config Entry and controller Config Subentries.

### 17.2 One-time import

On first v10 startup with legacy YAML:

1. detect legacy `entity_controller` configuration;
2. create/find the single root Config Entry;
3. convert each v9 controller into one `controller` Config Subentry;
4. convert old schedules to structured schedule data;
5. preserve all configured external entity references such as override/helpers;
6. snapshot any unambiguous controller-owned helper state needed for migration;
7. create runtimes in reconcile mode, not normal enter-transition mode;
8. verify imported controller count/configuration;
9. create migration report and Repair guidance;
10. use Config Entry/Subentry data as the new source of truth.

Import is idempotent. Leaving the old YAML temporarily in place must not duplicate controllers after restart.

### 17.3 Legacy field mapping

Migration covers the known v9 configuration surface, including:

- `sensor` / `sensors`;
- `entity` / `entities`;
- `state_entities`;
- `override` / `overrides`;
- `delay`;
- `sensor_type`;
- `sensor_resets_timer`;
- `block_timeout`;
- `disable_block`;
- night mode;
- stay mode;
- backoff settings;
- `service_data` / `service_data_off`;
- transition `behaviours`;
- control/sensor/state/override ON/OFF mappings;
- global state mappings where applicable;
- ignored event/context patterns;
- `state_attributes_ignore`;
- activation/deactivation trigger entities;
- legacy constraint forms.

Unknown values never silently disappear; migration reports the controller and field.

### 17.4 External Helpers/override entities are preserved, not converted

If old EC configuration references an arbitrary entity such as:

```text
input_boolean.navsteva_block
input_boolean.izba_block
switch.some_mode
```

that entity remains an external Home Assistant entity and the new controller keeps the same reference.

v10 does **not** guess that such a helper should be converted into an EC-owned switch.

The automation/helper relationship therefore continues to work immediately after migration.

### 17.5 Controller-owned dashboard helpers

The current dashboard uses per-controller patterns such as:

```text
input_boolean.ec01_izba_pohyb_enabled
binary_sensor.ec01_izba_pohyb_blokovanie
```

These represent controller runtime controls/status rather than arbitrary business logic.

Migration may detect exact, unambiguous controller-specific helper candidates and offer/map them to:

```text
input_boolean.ec01_izba_pohyb_enabled
    -> switch.ec01_izba_pohyb_enabled

binary_sensor.ec01_izba_pohyb_blokovanie
    -> binary_sensor.ec01_izba_pohyb_blocked
```

Current Enabled state is carried over. Automatic blocked state is reconstructed from the controller/runtime reality where possible rather than trusting a stale template helper.

If a candidate is ambiguous, v10 reports it instead of converting it silently.

### 17.6 No automatic deletion

Entity Controller never blindly deletes generic Helpers or edits user YAML.

Reasons:

- Helpers can be used elsewhere;
- YAML-defined helpers cannot safely be rewritten by the integration;
- another integration owns helper Config Entries.

After successful migration EC produces a cleanup report/Repair showing:

- old `ec.yaml` include that can be removed;
- old per-controller `*_enabled` helpers replaced by native EC switches;
- old `*_blokovanie` templates replaced by native blocked sensors;
- arbitrary Helpers that remain intentionally referenced by EC rules and therefore must **not** be removed unless the user chooses to redesign that logic.

### 17.7 Migration has no control side effects

Importing v9 YAML must never execute `on_enter_idle = off` merely because controller objects were reconstructed.

Imported controllers start through restore/reconcile. Existing lights/switches remain untouched unless a genuine post-setup event later requires a transition.

---

## 18. Dashboard-derived requirements

The existing `EC Mini` dashboard is a practical requirements source.

Observed requirements:

- ten controllers shown together;
- per-controller Enabled control;
- per-controller Blocked indication;
- one or more trigger sensors beside each controller;
- controlled/manual lights shown conditionally;
- state history per controller;
- visible distinction between disabled, blocked, active, constrained, physical motion, and manually-on controlled lights;
- multiple trigger entities on one controller;
- arbitrary external Helpers can affect one or many selected controllers.

v10.0.0 does not require a custom Lovelace card. Native entities should make the dashboard much simpler to rebuild with standard Tile/Mushroom/etc. cards.

---

## 19. Persistence

Controller-owned runtime controls that survive restart:

- Enabled state;
- Stay mode state.

External Helpers preserve themselves through their own Home Assistant integration and are never persisted a second time by EC.

Timer/runtime restoration is conservative. Persisted timestamps may be restored when valid; otherwise reconcile from live entity reality. Restart must not replay old transition actions twice.

---

## 20. Configuration UI

Each controller is one virtual EC device.

The reconfigure flow is divided into understandable sections:

1. Identity — name/icon.
2. Triggers — entities and sensor mode.
3. Controlled entities — control and optional state entities.
4. Timer — delay and sensor-reset semantics.
5. Manual control/blocking — automatic block behavior and timeout.
6. Override / external rule inputs.
7. Constraints.
8. Day/night profile.
9. Stay mode.
10. Actions/transition behavior.
11. Advanced state/context mappings.

Simple motion-light setup needs only the basic fields. Advanced settings stay secondary/collapsed.

English and Slovak translations are part of v10.

---

## 21. Diagnostics and Repairs

### Diagnostics

Expose:

- controller state;
- enabled/stay states;
- trigger/control/state entities;
- configured external rule-input entity IDs and their evaluated state;
- effective profile/delay;
- timer expiry;
- last transition/cause;
- last trigger;
- block reason/source/time;
- override source;
- constraint state;
- listener/subscription summary;
- migration source/version.

### Repairs

Use Repairs for actionable conditions such as:

- legacy YAML still present after successful import;
- unsupported legacy value;
- partially completed migration;
- configured entity no longer exists;
- old controller-owned helper cleanup recommendation.

Do not flag arbitrary external Helpers as redundant merely because EC references them.

---

## 22. Error handling

One broken controller must not unload all controllers.

Rules:

- root-invalidating setup failures fail clearly;
- controller-specific errors stay attached to that controller/subentry;
- unavailable source entities remain subscribed and recover where practical;
- failed custom actions log controller and transition context;
- listener/timer handles are cleaned on controller removal/unload;
- no stale runtime access after failed setup.

---

## 23. Testing strategy

Minimum test groups:

### FSM compatibility

- idle -> active timer;
- repeated event resets timer;
- duration ON/OFF behavior;
- stay mode;
- manual state-change block;
- block timeout;
- override enter/leave;
- external helper interlock enter/leave;
- constrained enter/leave;
- cross-midnight constraint;
- night profile;
- backoff;
- ignored context/attributes.

### Runtime reconfiguration

- active delay change;
- blocked timeout change;
- add/remove sensors;
- override/interlock config changed while active;
- constraint change while currently inside/outside window;
- no unintended ON/OFF during reconfigure.

### Migration

- import multiple v9 controllers;
- idempotent repeated import;
- legacy schedule conversion;
- full key mapping;
- preserve arbitrary external override/helper references;
- carry over unambiguous Enabled helper state;
- replace old block-status helper/template with native sensor mapping;
- ambiguous helper candidate produces report rather than silent conversion;
- unsupported field report;
- no migration control side effects;
- cleanup Repair lifecycle.

### Entity/device model

- correct root entry/subentry/device ownership;
- stable unique IDs;
- registry survives rename/reconfigure;
- disabled-by-default diagnostics optional;
- legacy compatibility state entity for migrated controllers.

---

## 24. Intended source layout

```text
custom_components/entity_controller/
├── __init__.py
├── manifest.json
├── const.py
├── config_flow.py
├── strings.json
├── translations/
│   ├── en.json
│   └── sk.json
├── manager.py
├── controller.py
├── model.py
├── schedule.py
├── context.py
├── migration.py
├── sensor.py
├── binary_sensor.py
├── switch.py
├── button.py
├── diagnostics.py
├── repairs.py
├── services.yaml
└── actions.py
```

Responsibilities remain separated; the old very large `__init__.py` design is not carried forward.

---

## 25. Repository modernization

v10 also refreshes tooling required for a current HACS integration:

- pytest;
- Ruff formatting/linting;
- Home Assistant/Hassfest validation where applicable;
- HACS validation;
- current GitHub Actions;
- removal of obsolete Node 12 release workflow;
- current manifest fields and minimum HA version;
- modern release automation.

---

## 26. Versioning and documentation policy

Development uses semantic prereleases, for example:

```text
10.0.0-alpha.1
10.0.0-alpha.2
10.0.0-beta.1
10.0.0-rc.1
10.0.0
```

Every development version must include:

- manifest/package version update;
- `CHANGELOG.md` entry;
- documentation update for user-visible changes;
- migration note when storage/config schema changes;
- tests for changed behavior;
- meaningful Git commit.

Documentation maintained throughout development:

- README/installation;
- configuration UI guide;
- entity reference;
- state-machine reference;
- migration from v9 / `ec.yaml`;
- controller-owned helper replacement table;
- external rule-input/helper behavior;
- actions/services;
- troubleshooting/Repairs;
- changelog.

---

## 27. Initial migration inventory from the current dashboard

Controllers:

```text
entity_controller.ec01_izba_pohyb
entity_controller.ec02_chodba_pohyb
entity_controller.ec03_chalupka_pohyb
entity_controller.ec04_vchod_pohyb
entity_controller.ec05_kupelna_nocny_pohyb
entity_controller.ec06_obyvacka_nocny_pohyb
entity_controller.ec07_kuchyna_nocny_pohyb
entity_controller.ec08_wc_pohyb
entity_controller.ec09_technicka
entity_controller.ec10_sprcha
```

Controller-owned Enabled helper candidates:

```text
input_boolean.ec01_izba_pohyb_enabled
input_boolean.ec02_chodba_pohyb_enabled
input_boolean.ec03_chalupka_pohyb_enabled
input_boolean.ec04_vchod_pohyb_enabled
input_boolean.ec05_kupelna_nocny_pohyb_enabled
input_boolean.ec06_obyvacka_nocny_pohyb_enabled
input_boolean.ec07_kuchyna_nocny_pohyb_enabled
input_boolean.ec08_wc_pohyb_enabled
input_boolean.ec09_technicka_enabled
input_boolean.ec10_sprcha_enabled
```

Block-status helper/template candidates to replace with native EC blocked sensors:

```text
binary_sensor.ec01_izba_pohyb_blokovanie
binary_sensor.ec02_chodba_pohyb_blokovanie
binary_sensor.ec03_chalupka_pohyb_blokovanie
binary_sensor.ec04_vchod_pohyb_blokovanie
binary_sensor.ec05_kupelna_nocny_pohyb_blokovanie
binary_sensor.ec06_obyvacka_nocny_pohyb_blokovanie
binary_sensor.ec07_kuchyna_nocny_pohyb_blokovanie
binary_sensor.ec08_wc_pohyb_blokovanie
binary_sensor.ec09_technicka_blokovanie
binary_sensor.ec10_sprcha_blokovanie
```

Examples that remain ordinary external Helpers when selected in EC rules:

```text
input_boolean.izba_block
input_boolean.navsteva_block
```

The migration implementation must not rely only on exact names above; this inventory is a concrete migration fixture, not a hardcoded product rule.

---

## 28. Explicit non-goals for v10.0.0

- custom Lovelace card;
- custom frontend panel;
- automatic editing/deletion of user YAML;
- automatic deletion/conversion of arbitrary Home Assistant Helpers;
- global hardcoded EC interlock/helper registry;
- Entity Controller/domain rename;
- compatibility with very old Home Assistant versions;
- reproducing known legacy bugs.

---

## 29. Acceptance criteria

v10 is successful when:

1. A new user can create a basic motion-light controller entirely in the HA UI.
2. Multiple controllers appear under one Entity Controller integration with independent device pages.
3. Editing one controller applies immediately without restart or unrelated-controller reload.
4. Restart/reconfigure causes no unintended controlled-entity ON/OFF action.
5. Intended v9 FSM behavior is covered by tests and preserved except documented changes.
6. Existing `ec.yaml` imports into Config Subentries without duplication.
7. Existing configured override/helper entity references survive migration unchanged.
8. Per-controller Enabled and Blocked dashboard helper use cases have native EC entities.
9. Arbitrary Helpers can be created/controlled elsewhere and assigned to any selected EC rules without EC owning them.
10. Migration clearly identifies old controller-owned helper mappings and what can be removed.
11. Old YAML can be removed after verified migration without losing EC functionality.
12. Migrated `entity_controller.*` references have a compatibility path.
13. Every prerelease/stable version updates version, changelog, documentation, migration notes when needed, and tests.
14. The implementation uses current Home Assistant APIs and avoids APIs already deprecated for the target version.

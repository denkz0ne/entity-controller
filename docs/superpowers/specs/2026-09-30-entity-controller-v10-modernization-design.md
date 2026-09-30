# Entity Controller v10 — modernization design

**Status:** design approved in chat; written specification awaiting final review  
**Date:** 2026-09-30  
**Target Home Assistant:** 2026.9+  
**Product version:** 10.0.0 development line  
**Repository:** `denkz0ne/entity-controller`  
**Domain:** `entity_controller`

## 1. Purpose

Entity Controller v10 is a modernization of the existing `danobot/entity-controller` integration rather than a new automation helper with similar behavior.

The goal is to preserve the useful Entity Controller behavior while replacing the old YAML-first implementation and old Home Assistant integration patterns with current Home Assistant APIs and a native UI.

The v10 design has five primary goals:

1. **Native configuration.** Controllers are created and edited in Home Assistant using Config Entries and Config Subentries instead of maintaining the controller configuration in `ec.yaml`.
2. **Immediate reconfiguration.** Editing one controller takes effect at runtime without restarting Home Assistant and without reloading unrelated controllers.
3. **Native runtime controls and status.** Per-controller booleans currently implemented as generic helpers become integration-owned switch/binary-sensor/button entities.
4. **Safe migration.** Existing v9 YAML configuration and the current helper-based operational setup can be migrated without losing controller behavior or current enabled/blocked intent.
5. **Modern runtime implementation.** Remove legacy startup delay, `threading.Timer`, `asyncio.run_coroutine_threadsafe`, and the `transitions` dependency. Use Home Assistant async lifecycle and event helpers directly.

The name **Entity Controller** and domain `entity_controller` remain unchanged for v10. Renaming is explicitly out of scope for this modernization.

---

## 2. Source of truth

The behavior baseline is the current upstream v9.7.6 source code, not only its older documentation.

The existing v9 behavior already documented in `denkz0ne/hassos-stuff` remains the compatibility reference. v10 should preserve intended behavior unless this specification explicitly changes it.

Known old implementation quirks or defects are not automatically compatibility requirements. Examples include the 70-second startup delay, duplicate state-list extension, stale service names in `services.yaml`, duplicate constraint callbacks, and thread-based timers.

---

## 3. Home Assistant architecture

### 3.1 Selected model: one root Config Entry + controller Config Subentries

Entity Controller creates a single root Config Entry. Each configured controller is a Config Subentry of type `controller`.

```text
Entity Controller
├── EC01 Izba pohyb
├── EC02 Chodba pohyb
├── EC03 Chalúpka pohyb
├── EC04 Vchod pohyb
└── ...
```

Each controller subentry owns one runtime controller and one Home Assistant device.

The runtime structure is:

```text
ConfigEntry[EntityControllerManager]
└── EntityControllerManager
    ├── ControllerRuntime(subentry A)
    ├── ControllerRuntime(subentry B)
    ├── ControllerRuntime(subentry C)
    └── SharedInterlockRuntime(...)
```

The manager is stored in `entry.runtime_data`.

A controller maps cleanly to the current Home Assistant registry model:

```text
root ConfigEntry
    └── controller ConfigSubentry
          └── controller Device
                ├── state/status entities
                ├── control entities
                └── diagnostics
```

Devices use current single-config-entry / single-subentry ownership APIs (`config_entry_id` and `config_subentry_id`). Deprecated multi-entry device registry fields are not used.

### 3.2 Alternatives considered

#### A. One root entry + Config Subentries — selected

Advantages:

- one clean integration card;
- independent controller lifecycle and reconfiguration;
- natural controller -> subentry -> device relationship;
- shared migration, actions, diagnostics, and future integration-level features;
- avoids one integration card per room/controller.

#### B. One Config Entry per controller — rejected

Simpler internally, but clutters the Integrations page and makes shared functionality less coherent.

#### C. One Config Entry containing an array of all controllers — rejected

Easy to serialize, but gives poor independent lifecycle, update, diagnostics, and entity ownership. It would recreate a large YAML-like monolith inside one UI form.

---

## 4. Controller state machine

The internal state machine remains the core of Entity Controller.

### 4.1 Runtime states

v10 runtime states:

- `idle`
- `active_timer`
- `active_stay_on`
- `blocked`
- `overridden`
- `constrained`
- `disabled`

The old `pending` state is removed. Startup is lifecycle, not a user-visible state.

The old hierarchical parent state `active` remains a conceptual grouping only and does not need to be stored as a runtime state.

### 4.2 No external state-machine library

The `transitions` package is removed.

Transitions are implemented explicitly through a typed enum and one central async transition path, conceptually:

```python
await controller.async_transition(
    ControllerState.BLOCKED,
    cause=TransitionCause.MANUAL_CONTROL,
)
```

The transition method is responsible for:

- validating the transition;
- exit behavior;
- state update;
- enter behavior;
- timer/listener consequences;
- context tracking;
- event/logbook data;
- entity state update;
- diagnostics metadata.

This gives one auditable and testable place for state changes.

### 4.3 Reconcile is not a transition

Startup, restore, migration, and reconfiguration use **reconcile** rather than simulating normal FSM entry events.

Reconcile observes current Home Assistant reality:

- constraint state;
- override inputs;
- manual/shared interlocks;
- control/state entities;
- duration sensor state;
- persisted runtime state when relevant.

It computes the correct controller state **without automatically executing transition ON/OFF actions simply because Home Assistant restarted or settings were edited**.

This prevents startup/reconfigure from turning devices on or off unexpectedly.

---

## 5. Controller entities

Configuration values remain configuration. Only values that are useful to observe or control at runtime become Home Assistant entities.

Each controller device exposes the following entities.

### 5.1 Primary/default entities

#### State sensor

Example:

```text
sensor.ec01_izba_pohyb_state
```

Enum-like states:

```text
idle
active_timer
active_stay_on
blocked
overridden
constrained
disabled
```

Localized display strings are provided in `strings.json` / translations; raw states remain stable English values.

Useful state attributes include:

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
active_interlocks: []
```

No once-per-second countdown attribute is generated. `expires_at` is sufficient and avoids unnecessary recorder writes.

#### Enabled switch

Example:

```text
switch.ec01_izba_pohyb_enabled
```

Semantics:

- OFF stops Entity Controller decision-making for that controller.
- OFF does **not** automatically turn controlled entities off.
- ON performs reconcile against current reality.
- state is persistent across Home Assistant restart.

This replaces the current per-controller `input_boolean.<controller>_enabled` helper pattern.

#### Stay mode switch

Example:

```text
switch.ec01_izba_pohyb_stay_mode
```

This replaces the need to call only `enable_stay_mode` / `disable_stay_mode` actions for normal dashboard use.

State persists across restart.

#### Manual block switch

Example:

```text
switch.ec01_izba_pohyb_manual_block
```

This is an integration-owned persistent interlock for a single controller.

It replaces controller-local generic helpers such as the current `input_boolean.izba_block` use case.

Semantics:

- ON places the controller under a persistent manual block/interlock.
- It does not pretend to be a momentary automatic block caused by a manual light state change.
- While ON, automatic activation is inhibited.
- The controller state is `blocked` and `block_reason=manual_interlock` when this is the active reason.
- OFF triggers reconcile and resumes the appropriate state.
- The default block transition behavior still decides whether entering/leaving blocked performs any entity action.

#### Blocked binary sensor

Example:

```text
binary_sensor.ec01_izba_pohyb_blocked
```

This is intentionally exposed even though the state sensor can also be `blocked`.

Reason: the current operational dashboard uses blocking independently for conditional chips, visibility, color, and status logic. A native binary sensor makes those uses simpler and removes the need for template binary-sensor helpers.

Attributes:

```yaml
reason: manual_control
blocked_by: light.pracovna_stol
blocked_at: 2026-09-30T14:21:00+02:00
block_expires_at: 2026-09-30T14:51:00+02:00
active_interlocks:
  - guest_mode
```

This replaces current helper/template patterns such as `binary_sensor.<controller>_blokovanie`.

#### Activate button

Example:

```text
button.ec01_izba_pohyb_activate
```

Equivalent to the existing `activate` service/action semantics.

### 5.2 Diagnostic entities disabled by default

Useful but not required in every dashboard:

- timestamp sensor: timer expiry;
- timestamp sensor: last trigger;
- timestamp sensor: last state transition;
- text/enum sensor: last transition cause, if it proves useful beyond attributes.

These are disabled by default to avoid entity clutter.

### 5.3 Clear block button

A `Clear block` button is available, disabled by default for new installations unless user feedback shows it deserves default exposure.

It clears an **automatic/latched block** where clearing is meaningful.

It cannot clear an active persistent manual block switch or active shared interlock. In those cases the button is unavailable or reports the still-active blocking source rather than lying about the result.

### 5.4 No force-block button as the primary design

The persistent `manual_block` switch is more useful than a momentary `force_block` button for the dashboard use case. Existing legacy `enable_block` action compatibility is retained separately.

---

## 6. Shared EC interlocks

The current dashboard includes shared helper concepts, for example one `navsteva_block` affecting multiple controllers. This is useful functionality and should not require a generic Home Assistant Helper.

v10 therefore supports a second Config Subentry type:

```text
shared_interlock
```

Example device/entity:

```text
Entity Controller / Návšteva
switch.entity_controller_navsteva
```

A shared interlock:

- is created inside Entity Controller;
- is integration-owned, not a generic Helper;
- may be assigned to any number of controllers;
- has persistent state;
- appears as a normal switch for dashboards and automations;
- causes assigned controllers to reconcile immediately when toggled;
- contributes a distinct `block_reason=shared_interlock` and source identifier.

This makes a current pattern such as one `navsteva_block` shared by Obývačka and Kuchyňa native to the integration.

External Home Assistant entities can still be configured as interlock/override inputs when desired. Native EC interlocks are an option, not a restriction.

---

## 7. Inputs and controlled entities

### 7.1 Trigger sensors

A controller supports one or more trigger entities.

Example current use case:

```text
Vchod
├── motion sensor
└── door sensor
```

Trigger inputs are not copied into new EC entities. They remain their real source entities and are displayed/referenced by the controller device/configuration.

Sensor modes remain compatible with v9 concepts:

- event sensor;
- duration sensor.

Custom ON/OFF mappings remain available in Advanced configuration.

### 7.2 Control entities

One or more entities controlled by the controller.

Simple default behavior continues to use normal Home Assistant turn-on/turn-off semantics where supported.

### 7.3 State entities

State entities default to control entities when not explicitly configured, preserving current Entity Controller behavior.

State changes determine manual-control blocking and reconciliation.

### 7.4 Ignored attributes and contexts

`state_attributes_ignore` behavior remains supported.

Context filtering is modernized so Entity Controller can reliably ignore its own actions and track controller-generated contexts without relying only on a string prefix convention.

The compatibility requirement remains: EC must not fight itself or misclassify its own service calls as manual user intervention.

---

## 8. Blocking semantics

Blocking is preserved as a first-class feature, with clearer source tracking.

Possible block sources include:

- manual/external state change of a state/control entity;
- existing control entity already ON when an event occurs and block behavior requires blocking;
- local `manual_block` switch;
- shared EC interlock;
- external configured interlock;
- legacy/manual `enable_block` action.

The runtime records the source and reason.

A persistent interlock and an automatic block are not treated as identical internally, even if both surface as `state=blocked`.

Block timeout applies only to block classes where timeout is logically valid. A persistent user-held interlock does not expire just because `block_timeout` elapsed unless the user explicitly configures timeout behavior for that interlock.

---

## 9. Override

Override remains a separate priority state rather than being collapsed into blocking.

Features retained:

- one or more override entities;
- OR semantics across override inputs;
- custom override ON/OFF state mappings;
- immediate reconcile when override configuration changes;
- after override clears, determine the correct state from sensors/state entities rather than blindly turning entities off.

`overridden_by` is exposed in runtime diagnostics/state attributes.

---

## 10. Constraints and schedules

v10 replaces free-form runtime string parsing as the primary configuration model with structured configuration.

Each schedule point has a source such as:

- fixed local time;
- sunrise;
- sunset;

plus an optional positive or negative duration offset.

Example conceptual model:

```python
SchedulePoint(
    source=SUNSET,
    offset=-timedelta(minutes=30),
)
```

Cross-midnight windows remain supported.

Legacy YAML values such as `sunset - 00:30:00` are parsed during import/migration and converted to the structured v10 representation.

Debug-only legacy forms such as `now +/- seconds` do not become normal UI configuration features.

---

## 11. Day/night profiles

Constraint and profile are separate concepts:

- constraint = whether the controller is allowed to operate;
- profile = how the controller behaves during a period.

Night mode remains supported and may have its own:

- timeout;
- activation action data;
- deactivation action data;
- future profile-specific actions.

Where a night setting is omitted, it inherits the normal/day profile value.

---

## 12. Timer and backoff

`threading.Timer` is removed.

Timers use current Home Assistant async time helpers and cancellable unsubscribe/callback handles.

Backoff behavior remains compatible with v9 intent:

- backoff counter starts at zero on activation;
- timer reset increments the count;
- effective delay is recalculated using factor and maximum;
- effective delay is visible in state/diagnostics.

### 12.1 Immediate timer reconfiguration

Changing delay while a timer is active does not restart the controller from scratch.

Example:

```text
last_triggered_at = 14:00:00
old delay = 180 s
new delay = 60 s
```

New expiry becomes:

```text
14:01:00
```

If that time is already in the past, normal timer-expiry evaluation runs immediately.

Equivalent recalculation rules apply to block timeout and profile delay changes.

---

## 13. Runtime hot reconfiguration

Editing a controller uses Config Subentry reconfigure flow and `async_update_and_abort` style update semantics rather than a config-flow helper that reloads the integration.

A controller update listener computes a configuration diff and updates only that runtime controller.

Examples:

- delay changed -> reschedule current timer;
- sensors changed -> unsubscribe removed listeners, subscribe new listeners, reconcile;
- override inputs changed -> rebuild listeners, evaluate override immediately;
- constraint changed -> reschedule boundaries and evaluate current period immediately;
- block timeout changed -> recalculate from `blocked_at`;
- shared interlock assignment changed -> subscribe/unsubscribe and reconcile;
- stay mode behavior changed -> reconcile active state;
- controlled entities changed -> update subscriptions safely without blindly firing an activation/deactivation transition.

No Home Assistant restart is required.

No unrelated controller is reloaded.

The parent Config Entry is not double-reloaded by mixing update listeners with reload helpers.

---

## 14. Transition behaviors and custom actions

The following v9 transition behavior concepts remain available:

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

Default behavior remains compatible with v9 intent:

```text
enter idle   -> OFF
enter active -> ON
others       -> IGNORE
```

The UI offers simple choices:

```text
Turn off
Turn on
Do nothing
Custom action
```

`Custom action` uses native Home Assistant action configuration rather than a new Entity Controller-specific DSL.

Simple control entities remain easy to configure without requiring the action editor.

---

## 15. Actions/services compatibility

v10 keeps the existing action names where meaningful:

- `activate`
- `clear_block`
- `enable_block`
- `enable_stay_mode`
- `disable_stay_mode`
- `set_night_mode`

Native entities become the preferred day-to-day UI mechanism for enabled/stay/manual block/activate.

Legacy service definitions are cleaned up so `services.yaml` and implementation names cannot diverge.

Targeting is modernized around controller entities/devices/config subentries while preserving a compatibility path for existing automations where practical.

---

## 16. Legacy state entity compatibility

Existing installations may have dashboards and automations referencing entities such as:

```text
entity_controller.ec01_izba_pohyb
```

v10 migration must not casually destroy those references.

The migration implementation will therefore preserve a **legacy compatibility state entity** for imported v9 controllers during the v10 compatibility window.

The new native state sensor is the preferred entity, but the old `entity_controller.<object_id>` state mirror remains available for migrated controllers so existing history graphs, templates, and automations continue to work while the user migrates dashboards.

New controllers do not need the legacy mirror by default.

The compatibility entity is documented as transitional and may be removed in a later major release, not silently during v10 migration.

---

## 17. Migration from v9 YAML to v10

Migration is a required v10 feature, not a later enhancement.

### 17.1 Input format

A legacy installation may contain:

```yaml
entity_controller: !include ec.yaml
```

or equivalent inline YAML.

Home Assistant already parses included YAML before passing the domain configuration to the integration. v10 uses an import path to convert that parsed configuration into the root Config Entry and controller Config Subentries.

### 17.2 One-time import behavior

On first v10 startup with legacy YAML present:

1. detect legacy `entity_controller` YAML configuration;
2. create or locate the single Entity Controller root Config Entry;
3. convert each legacy controller to one `controller` Config Subentry;
4. convert legacy string schedules to structured schedule data;
5. snapshot compatible runtime/helper state before setup;
6. create runtime controllers in reconcile mode, not normal enter-transition mode;
7. verify the imported controller set;
8. create a migration report and Repair issue explaining cleanup;
9. continue using Config Entry/Subentry data as the v10 source of truth.

Import is idempotent. Restarting Home Assistant with the same legacy YAML still present must not duplicate controllers.

### 17.3 Legacy configuration key mapping

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
- night mode configuration;
- stay mode;
- backoff settings;
- `service_data` and `service_data_off`;
- transition `behaviours`;
- control/sensor/state/override ON/OFF mappings;
- globally appended state mappings where applicable;
- ignored event/context source patterns;
- `state_attributes_ignore`;
- activation/deactivation trigger entities;
- legacy constraint forms.

Unknown or unsupported legacy values do not silently disappear. They create a migration warning/report entry identifying the controller and field.

### 17.4 Migration of current helper-backed controller controls

The current operational dashboard shows ten controllers with per-controller helper patterns such as:

```text
input_boolean.ec01_izba_pohyb_enabled
binary_sensor.ec01_izba_pohyb_blokovanie
...
input_boolean.ec10_sprcha_enabled
binary_sensor.ec10_sprcha_blokovanie
```

For migration, Entity Controller checks for conventional matching helper/entity IDs derived from the controller object id.

When found:

- old `*_enabled` state initializes the new native Enabled switch;
- old `*_blokovanie` is treated as a migration/status source only, not as permanent configuration;
- current automatic block state is reconstructed from real controller state where possible;
- the migration report records the old -> new entity mapping.

Example report mapping:

```text
input_boolean.ec01_izba_pohyb_enabled
    -> switch.ec01_izba_pohyb_enabled

binary_sensor.ec01_izba_pohyb_blokovanie
    -> binary_sensor.ec01_izba_pohyb_blocked
```

### 17.5 Controller-local manual block helpers

A controller-local helper such as:

```text
input_boolean.izba_block
```

can be migrated to the controller's native Manual block switch when it is explicitly mapped during migration or confidently matched by migration metadata/rules.

Its current ON/OFF value initializes the native EC switch.

The old helper is not automatically deleted by Entity Controller because it may be YAML-defined or referenced by unrelated automations. The migration report marks it as redundant after references are moved.

### 17.6 Shared helper/interlock migration

A helper such as:

```text
input_boolean.navsteva_block
```

currently affects more than one controller.

It can be migrated to a native Entity Controller shared interlock subentry and assigned to the same controllers.

Its current state is preserved.

The migration report maps the old helper to the new EC-owned switch and lists all assigned controllers.

### 17.7 Safe cleanup of old helpers

Entity Controller does **not** blindly delete generic Home Assistant helpers or edit the user's YAML files.

Reasons:

- a helper can be defined in YAML where an integration cannot safely rewrite the file;
- a helper can be referenced outside Entity Controller;
- deleting another integration's config entry is unsafe ownership behavior.

Instead v10 produces a precise cleanup report and persistent Repair issue after successful migration.

The user can then remove:

- the old `entity_controller:` YAML / `ec.yaml` include;
- per-controller `*_enabled` helpers after dashboard/automation references are moved;
- old `*_blokovanie` template helpers after references are moved;
- local/shared block helpers that were replaced by native EC entities.

The Repair issue is removed only when legacy YAML is gone and migration cleanup is complete or explicitly acknowledged.

### 17.8 Migration must not cause control side effects

Importing v9 YAML must never run `on_enter_idle = off` merely because the controller object was reconstructed.

All imported controllers start through restore/reconcile.

Current lights/switches remain untouched unless the observed state plus actual current EC logic requires a genuine transition after setup.

---

## 18. Dashboard-derived requirements

The existing `EC Mini` dashboard is treated as a practical requirements source.

Observed current requirements include:

- ten Entity Controller instances shown together;
- per-controller enabled control;
- per-controller blocked indication;
- one or more physical trigger sensors displayed next to each controller;
- controlled/manual lights displayed conditionally;
- state history per controller;
- visual distinction between disabled, blocked, active, constrained, physical motion, and manually-on controlled lights;
- a controller can have multiple trigger sensors (for example motion + door);
- a local manual block may affect one controller;
- a shared block/interlock may affect multiple controllers.

v10 does not require a custom Lovelace card for the first stable release. Native entities must make the current dashboard substantially simpler to rebuild using standard Tile/Mushroom/etc. cards.

A custom Entity Controller card or panel is a later enhancement only if native entities and device pages prove insufficient.

---

## 19. Persistence

The following controller-owned runtime controls must survive Home Assistant restart:

- Enabled state;
- Stay mode state;
- Manual block state;
- shared EC interlock state.

Timer/runtime state restoration must be conservative.

Where a persisted timestamp is meaningful and still valid, it can be restored. Otherwise the controller reconciles from current sensor/entity reality rather than replaying stale actions.

Persistent state must never make restart execute an old transition action twice.

---

## 20. Device page and native UI

Each controller appears as one virtual Entity Controller device with its runtime entities.

Configuration flow is organized into understandable sections rather than one large form:

1. Identity — name/icon.
2. Triggers — sensors and sensor mode.
3. Controlled entities — control and optional state entities.
4. Timer — delay and sensor reset semantics.
5. Manual control / blocking — block behavior and timeout.
6. Override.
7. Constraints.
8. Day/night profile.
9. Stay mode.
10. Actions/transition behavior.
11. Advanced state/context mappings.
12. Shared interlocks.

Simple motion-light setup should require only the basic fields. Advanced sections stay collapsed/secondary in normal use.

English and Slovak translations are part of v10.

---

## 21. Diagnostics and Repairs

### 21.1 Diagnostics

Integration and controller diagnostics expose useful runtime data, including:

- controller state;
- enabled/stay/manual block states;
- configured trigger/control/state entities;
- effective profile and delay;
- active timer expiry;
- last transition/cause;
- last trigger;
- block reason/source/time;
- override source;
- active constraints;
- active shared interlocks;
- listener/subscription summary;
- migration source/version when applicable.

Sensitive data is redacted where appropriate.

### 21.2 Repairs

Repairs are used for actionable problems, including:

- legacy YAML still present after successful import;
- unsupported legacy configuration value;
- migration partially completed;
- referenced configured entity no longer exists;
- legacy helper cleanup recommendations where references must be updated by the user.

---

## 22. Error handling

Controller failures are isolated where possible.

One malformed or unavailable entity must not unload every controller.

Rules:

- setup failures that invalidate the root integration fail clearly;
- controller-specific configuration errors surface against that controller/subentry;
- unavailable source entities remain subscribed and recover when available where practical;
- failed custom action execution is logged with controller and transition context;
- timer/listener unsubscribe handles are always cleaned up on controller removal or integration unload;
- no stale runtime access after failed Config Entry setup.

---

## 23. Testing strategy

v10 requires tests for behavior, not only import success.

Minimum test groups:

### FSM compatibility

- idle -> active timer;
- repeated event resets timer;
- duration sensor ON/OFF behavior;
- stay mode;
- block from manual state change;
- block timeout;
- override enter/leave;
- constrained enter/leave;
- cross-midnight constraint;
- night profile;
- backoff;
- ignored context and state attributes.

### Runtime reconfiguration

- changing delay while active;
- changing block timeout while blocked;
- adding/removing sensors;
- changing override while override currently active;
- changing constraints while currently inside/outside window;
- toggling shared interlock assignment;
- no unintended ON/OFF during reconfigure.

### Migration

- import multiple controllers from legacy YAML;
- idempotent repeated import;
- legacy schedule conversion;
- v9 configuration key mapping;
- enabled helper state carry-over;
- local manual block migration;
- shared interlock migration;
- unsupported legacy field report;
- migration creates no control side effects;
- cleanup Repair creation/removal.

### Entity/device model

- controller device bound to correct root entry and config subentry;
- unique IDs stable;
- entity registry survives rename/reconfigure;
- disabled-by-default diagnostics remain optional;
- compatibility state entity for migrated controllers.

---

## 24. Source layout

Exact boundaries can evolve during implementation, but the intended responsibilities are:

```text
custom_components/entity_controller/
├── __init__.py              # Config Entry lifecycle
├── manifest.json
├── const.py
├── config_flow.py           # root + subentry flows/reconfigure/import
├── strings.json
├── translations/
│   ├── en.json
│   └── sk.json
├── manager.py               # root runtime manager
├── controller.py            # FSM/runtime controller
├── model.py                 # typed config/state models/enums
├── schedule.py              # constraints/night schedule calculations
├── context.py               # EC action context tracking/filtering
├── migration.py             # v9 YAML/helper migration
├── sensor.py
├── binary_sensor.py
├── switch.py
├── button.py
├── diagnostics.py
├── repairs.py
├── services.yaml
└── actions.py               # service/action dispatch + custom HA actions
```

Files should remain focused; the old single very large `__init__.py` architecture is not carried forward.

---

## 25. Repository modernization

v10 development also refreshes repository tooling necessary for a current HACS integration:

- current Python project/test tooling;
- pytest;
- Ruff formatting/linting;
- Home Assistant/Hassfest validation where applicable;
- HACS validation;
- modern GitHub Actions versions;
- removal of obsolete Node 12 release workflow;
- current manifest fields and minimum Home Assistant version;
- release automation that does not depend on deprecated GitHub Actions behavior.

No unrelated refactor is included merely for aesthetics.

---

## 26. Versioning and documentation policy

Every development version must be traceable in GitHub.

### 26.1 Product versions

Development uses semantic prereleases, for example:

```text
10.0.0-alpha.1
10.0.0-alpha.2
10.0.0-beta.1
10.0.0-rc.1
10.0.0
```

The exact milestone cut points are defined in the implementation plan.

### 26.2 Every version update must include

- manifest/package version update;
- `CHANGELOG.md` entry;
- documentation update for any user-visible behavior/config/entity change;
- migration note when storage/config schema changes;
- tests for behavior changed in that version;
- Git commit with a meaningful message.

### 26.3 Documentation to maintain

At minimum:

- README / installation;
- configuration UI guide;
- entity reference;
- state-machine/behavior reference;
- migration from v9 / `ec.yaml`;
- legacy helper replacement table;
- actions/services reference;
- troubleshooting/Repairs;
- changelog.

The repository documentation is considered part of the feature, not post-release cleanup.

---

## 27. Initial migration mapping from the current dashboard

The current dashboard provides an initial concrete migration inventory.

### Controllers

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

### Per-controller Enabled helpers to replace

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

### Per-controller block-status helpers/templates to replace

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

### Additional current block helpers

```text
input_boolean.izba_block       # controller-local candidate -> native Manual block
input_boolean.navsteva_block   # shared candidate -> native EC shared interlock
```

The migration code must not rely only on these exact names; they are a concrete test fixture and first migration target.

---

## 28. Explicit non-goals for v10.0.0

To keep the rewrite focused, the first stable v10 does not require:

- a custom Lovelace card;
- a custom frontend panel;
- automatic editing/deletion of the user's YAML files;
- automatic deletion of generic Helper config entries;
- renaming Entity Controller/domain;
- compatibility with very old Home Assistant versions;
- reproducing known legacy bugs merely because they existed in v9.

Native entities, device pages, config/subentry flows, diagnostics, Repairs, and migration are the UI foundation for v10.

---

## 29. Acceptance criteria

v10 design is successful when all of the following are true:

1. A new user can create a basic motion-light controller entirely from the Home Assistant UI.
2. Multiple controllers appear under one Entity Controller integration and have independent device pages.
3. Editing a controller applies immediately without Home Assistant restart and without restarting unrelated controllers.
4. Restart/reconfigure does not cause unintended controlled-entity ON/OFF actions.
5. Existing v9 FSM behavior is covered by tests and preserved except where this specification explicitly modernizes it.
6. Existing `ec.yaml` configuration imports into v10 controller subentries without duplication.
7. Current per-controller Enabled and Block helper use cases are replaced by native EC entities.
8. Controller-local and shared manual block use cases can be represented natively by Entity Controller.
9. Migration produces a clear old -> new entity/helper cleanup report.
10. The old YAML and redundant helpers can be removed after migration without losing EC functionality.
11. Existing migrated `entity_controller.*` state references have a compatibility path during v10.
12. Every prerelease/stable version updates code version, changelog, documentation, migration notes when needed, and tests.
13. The integration uses current Home Assistant APIs and avoids APIs already deprecated in the 2026.9 development documentation.

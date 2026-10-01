# Entity Controller v10 native entities

> Current behavior: `v10-modernization`, `10.0.0-rc.7`. Each native entity has a stable unique ID, a translated function name, a function-specific icon, and a canonical suggested entity ID for first registration.

Each controller config subentry owns one virtual Home Assistant device and currently exposes five native entities.

## Native entities

| Domain / key | Purpose | Enabled by default |
| --- | --- | --- |
| `sensor` / `state` | Exact controller FSM state. | yes |
| `switch` / `enabled` | Enables/disables EC decision-making without forcing controlled loads OFF. | yes |
| `switch` / `stay_mode` | Toggles persistent Stay Mode. | yes |
| `binary_sensor` / `blocked` | Convenience boolean for the `blocked` state. | yes |
| `button` / `activate` | Requests controller activation using the same runtime action as the compatibility service. | yes |

The controller itself is represented by a device named after the configured controller. The current model string is `Entity Controller v10`.

## State sensor

The state sensor reports one of:

- `idle`
- `active_timer`
- `active_stay_on`
- `blocked`
- `overridden`
- `constrained`
- `disabled`

The State sensor exposes low-churn runtime context:

- `last_transition_at`, `last_transition_cause`, `last_transition_source`
- `last_reconcile_reason` (kept separate from real FSM transitions)
- `last_triggered_by`
- `last_triggered_at`
- `blocked_by`, `blocked_at`, `block_reason`, `block_expires_at`
- `overridden_by`, `active_overrides`, `active_interlocks`
- `active_triggers`, `active_state_entities`
- `enabled`, `stay_mode`, `override_active`, `interlock_active`, `sensor_active`, `state_entities_on`
- `effective_delay`
- `backoff_count`, `timer_expired_pending_sensor`
- `profile` (`day` / `night`)
- `expires_at`

The earlier `last_transition` and `transition_cause` attribute names remain as aliases for existing automations. Attributes update on runtime events; there is no per-second countdown. A reconcile updates `last_reconcile_reason` and active source lists without pretending that an FSM transition happened.

## Blocked binary sensor

The Blocked binary sensor exposes:

- `block_reason` (and compatibility alias `reason`);
- `blocked_by`;
- `blocked_at`;
- `block_expires_at`.
- `active_interlocks`.

When reconcile resolves the controller as blocked by an active interlock, `blocked_by` names the first currently active configured interlock. The Blocked boolean and diagnostics also include the full active interlock list.

## Diagnostics download

The config-entry diagnostics export includes per-controller runtime provenance, active source lists, timer/backoff values, relevant configuration, and controller errors. Sensitive keys are redacted recursively before export.

## Entity-id convention

New native entities should be created using the controller slug and an explicit EC prefix:

```text
<domain>.ec_<controller_slug>_<function>
```

Example for controller **Obývačka**:

```text
sensor.ec_obyvacka_state
switch.ec_obyvacka_enabled
switch.ec_obyvacka_stay_mode
binary_sensor.ec_obyvacka_blocked
button.ec_obyvacka_activate
```

The stable `unique_id` must remain based on root config-entry ID + controller subentry ID + entity function key. Renaming a controller must not change the unique ID.

The suggestion is used only for the first registration. Home Assistant retains an existing registry entity ID by its stable unique ID, so controller renames and user-customized IDs are preserved.

## Visible names and localization

New integrations should use Home Assistant native entity naming: `has_entity_name = True` plus `translation_key`, rather than hard-coded natural-language names in Python.

The controller device supplies the device name; the entity supplies only its translated function name. The frontend can therefore render names equivalent to:

- `Obývačka - EC Stav`
- `Obývačka - EC Zapnutý`
- `Obývačka - EC Trvalý režim`
- `Obývačka - EC Blokovaný`
- `Obývačka - EC Aktivovať`

Recommended Slovak function labels:

| Key | Slovak | English |
| --- | --- | --- |
| `state` | `EC Stav` | `EC State` |
| `enabled` | `EC Zapnutý` | `EC Enabled` |
| `stay_mode` | `EC Trvalý režim` | `EC Stay mode` |
| `blocked` | `EC Blokovaný` | `EC Blocked` |
| `activate` | `EC Aktivovať` | `EC Activate` |

The exact separator/combined friendly-name rendering is controlled by Home Assistant's device/entity naming model; do not hard-code the controller name into the entity translation itself.

## Entity icons

The controller may still have its own optional user-selected icon, but native entities should have function-specific defaults so they remain instantly recognizable.

| Entity | Recommended icon | Why |
| --- | --- | --- |
| State | `mdi:state-machine` | Represents the controller FSM rather than the controlled load. |
| Enabled | `mdi:toggle-switch` | Direct enable/disable control. |
| Stay Mode | `mdi:pin` | Conveys holding/pinning the active state. |
| Blocked | `mdi:shield-lock` | Protection/gating rather than an error. |
| Activate | `mdi:play-circle` | Explicit one-shot activation action. |

Optional state-specific icons for the state sensor, if implemented through entity state translations/icons:

| FSM state | Suggested icon |
| --- | --- |
| `idle` | `mdi:motion-sensor-off` or `mdi:pause-circle-outline` |
| `active_timer` | `mdi:timer-play` |
| `active_stay_on` | `mdi:pin` |
| `blocked` | `mdi:shield-lock` |
| `overridden` | `mdi:gesture-tap-button` |
| `constrained` | `mdi:clock-lock-outline` |
| `disabled` | `mdi:power-off` |

Use only Material Design icons available in the Home Assistant target version; the implementation task should verify exact icon availability before committing.

## Attribute policy

The state sensor should remain the primary diagnostics surface because these values explain its current state. Prefer attributes for low-churn explanatory metadata:

- transition/reconcile reason;
- source entity;
- who/what blocked or overrode;
- relevant timestamps;
- timer expiry;
- effective delay/profile/backoff count;
- current active override/interlock sources.

Do **not** create a per-second countdown attribute. `expires_at` is enough and avoids unnecessary Recorder churn.

Create a separate diagnostic entity only when the value has independent historical/automation value and would otherwise cause frequent changes to a large attribute payload. Such additional diagnostic entities should be disabled by default.

## Native controls versus external Helpers

Entity Controller owns only controller runtime controls such as Enabled and Stay Mode. It does not create a persistent manual-block/guest-mode/holiday-mode switch.

A user-created Helper remains a normal Home Assistant entity and can be selected as an override or interlock input in one or more controllers.

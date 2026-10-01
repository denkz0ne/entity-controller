# Entity Controller v10 native entities

> Source baseline: `v10-modernization`, `10.0.0-rc.3` (`86893e7`). The first section describes current RC.3 behavior. The naming/icon section defines the approved RC polish target and is intentionally marked as planned where it is not implemented yet.

Each controller config subentry owns one virtual Home Assistant device and currently exposes five native entities.

## Current RC.3 entities

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

RC.3 already exposes these attributes on the state sensor:

- `last_transition`
- `transition_cause`
- `last_triggered_by`
- `last_triggered_at`
- `effective_delay`
- `profile` (`day` / `night`)
- `expires_at`
- `block_expires_at`
- `blocked_by`
- `overridden_by`

Useful runtime data that exists in Python but is not yet exposed includes `last_reconcile_reason`, `blocked_at`, `backoff_count`, `timer_expired_pending_sensor`, the current `interlock_active`/`override_active` flags, and the generic source of the most recent state change.

## Blocked binary sensor

RC.3 exposes:

- `reason` — currently the controller's last transition cause;
- `blocked_by`;
- `block_expires_at`.

Because interlock blocking currently happens through reconcile rather than a transition, those attributes are not yet sufficient to explain every blocked state. The diagnostics polish issue covers this.

## Planned entity-id convention

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

For existing registered entities, the implementation must not casually overwrite a user-customized entity ID. A migration may rename only entries that can be proven to still use an integration-generated/default ID; otherwise preserve the user's ID and only update the translated visible name.

## Planned visible names and localization

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

## Recommended entity icons

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
